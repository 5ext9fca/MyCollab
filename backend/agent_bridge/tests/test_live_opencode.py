"""显式启用的真实接入验收；普通测试不访问模型或供应商凭据。"""
import os
from pathlib import Path
import sys
import unittest
import uuid
import socket
from unittest.mock import patch

from django.test import LiveServerTestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from agent_bridge.models import AssistanceRequest
from agent_bridge import protocol, services
from missions import services as business
from missions.models import Mission, ProductionBatch
from missions.tests import utils


@unittest.skipUnless(os.environ.get("MYCOLLAB_LIVE_MODEL"), "仅在显式指定本机模型时运行真实接入")
@override_settings(ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"])
class OpenCodeAcceptanceTests(LiveServerTestCase):
    def test_four_real_round_trips_then_explicit_business_save(self):
        original_connect = socket.socket.connect
        def local_only(connection, address):
            if isinstance(address, tuple) and address[0] not in ("localhost", "127.0.0.1", "::1"):
                raise OSError("验收服务器禁止外部网络；模型必须由独立本地进程通信。")
            return original_connect(connection, address)
        network_guard = patch.object(socket.socket, "connect", local_only)
        network_guard.start()
        self.addCleanup(network_guard.stop)
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from local_runner.__main__ import BridgeClient, execute
        actor = User.objects.create_user("local-acceptance")
        device, token = services.create_device(actor, name="真实接入测试", capabilities=list(protocol.KINDS))
        runner = BridgeClient(self.live_server_url, token)
        browser = APIClient()
        browser.force_login(actor)

        def candidate(kind, draft, **extra):
            response = browser.post("/api/assistance-requests/", {"device_id": str(device.pk), "kind": kind,
                "idempotency_key": str(uuid.uuid4()), "draft": draft, "instructions": "简洁中文，保留事实，输出严格 JSON。", **extra}, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            claimed = runner.post("claim/", {})
            self.assertEqual(claimed["id"], response.data["id"])
            execute(runner, claimed, os.environ["MYCOLLAB_LIVE_MODEL"], "opencode")
            result = browser.get(f"/api/assistance-requests/{claimed['id']}/").json()
            self.assertEqual(result["status"], "succeeded", result.get("error"))
            return result["result"]

        result = candidate("design_polish", {"title": "森林守卫", "content": "绿色披风，保持轮廓清楚。", "kind": "Asset"})
        response = browser.post("/api/design-elements/", {"title": result["title"], "content": result["content"], "kind": "Asset"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        result = candidate("template_generate", {"name": "文档生产", "description": "只需编写和核对两个文档步骤，不涉及文件生成。", "steps": []})
        response = browser.post("/api/production-templates/", result, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(ProductionBatch.objects.exists())
        self.assertFalse(Mission.objects.exists())
        result = candidate("mission_write", {"title": "角色文档", "content": "说明绿色披风，不增加武器。", "acceptance_criteria": "明确披风颜色", "type": "Task", "priority": "P2", "tags": []})
        response = browser.post("/api/missions/", {key: value for key, value in result.items() if key != "questions"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        mission = Mission.objects.get(pk=response.data["id"])
        self.assertEqual(mission.status, "Open")
        self.assertIsNone(mission.assignee_id)
        mission = utils.claim(actor, mission)
        mission = utils.submit(actor, mission, description="角色穿绿色披风，没有武器。", verification_description="文本人工核对")
        result = candidate("review_assist", {}, object_id=str(mission.pk), base_version=mission.version, submission_id=str(mission.current_submission_id))
        mission.refresh_from_db()
        self.assertEqual(mission.status, "Submitted")
        response = browser.post(f"/api/missions/{mission.pk}/review/", {"expected_version": mission.version,
            "submission_id": str(mission.current_submission_id), "decision": "accept", "comment": result["comment"],
            "verified_build_reference_id": None}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        mission.refresh_from_db()
        self.assertEqual(mission.status, "Done")
        self.assertEqual(AssistanceRequest.objects.filter(status="succeeded").count(), 4)
