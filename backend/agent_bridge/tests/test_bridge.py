import copy
import uuid
from datetime import timedelta

from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from django.core.management import call_command
from rest_framework.test import APIClient

from accounts.models import User
from common.exceptions import ConflictError, PermissionDenied, ValidationFailure
from missions import services as business
from missions.models import Comment, Mission
from missions.tests.test_concurrency_features import run_concurrently
from missions.tests import utils
from agent_bridge import protocol, services
from agent_bridge.models import AgentDevice, AssistanceRequest


DRAFT = {"title": "森林守卫", "content": "保留轮廓", "kind": "Asset"}
RESULT = {"title": "森林守卫", "content": "保留清晰轮廓", "summary": "明确表述", "questions": []}


class BridgeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("author", password="password")
        self.other = User.objects.create_user("other")
        self.device, self.token = services.create_device(self.user, name="本机", capabilities=list(protocol.KINDS))
        self.browser = APIClient()
        self.browser.force_login(self.user)
        self.runner = APIClient()
        self.runner.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    def request(self, **changes):
        args = dict(device_id=self.device.pk, kind="design_polish", idempotency_key=uuid.uuid4(), draft=DRAFT)
        args.update(changes)
        return services.create_request(self.user, **args)

    def test_token_only_hash_and_auth_boundaries(self):
        self.assertNotIn(self.token, self.device.token_digest)
        self.assertEqual(len(self.device.token_digest), 64)
        self.assertEqual(self.runner.get("/api/missions/").status_code, 403)
        self.assertEqual(self.browser.post("/api/agent-runner/claim/").status_code, 401)
        self.assertEqual(self.runner.get("/api/agent-devices/").status_code, 403)
        data = self.browser.get("/api/agent-devices/").json()
        self.assertNotIn("token_digest", data["results"][0])
        csrf = APIClient(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        self.assertEqual(csrf.post("/api/agent-devices/", {"name": "x"}).status_code, 403)

    def test_isolation_revoke_expiry_and_deactivation(self):
        item = self.request()
        self.browser.force_login(self.other)
        self.assertEqual(self.browser.get(f"/api/assistance-requests/{item.pk}/").status_code, 404)
        self.assertEqual(self.browser.post(f"/api/agent-devices/{self.device.pk}/revoke/").status_code, 404)
        AgentDevice.objects.filter(pk=self.device.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.runner.post("/api/agent-runner/claim/").status_code, 401)
        AgentDevice.objects.filter(pk=self.device.pk).update(expires_at=timezone.now() + timedelta(days=1))
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.runner.post("/api/agent-runner/claim/").status_code, 401)
        self.user.is_active = True
        self.user.save()
        services.revoke_device(self.user, self.device.pk)
        self.assertEqual(self.runner.post("/api/agent-runner/claim/").status_code, 401)
        item.refresh_from_db()
        self.assertEqual(item.status, "cancelled")

    def test_idempotency_quota_and_device_single_running(self):
        key = uuid.uuid4()
        item = self.request(idempotency_key=key)
        self.assertEqual(self.request(idempotency_key=key).pk, item.pk)
        with self.assertRaises(ConflictError):
            self.request(idempotency_key=key, instructions="不同输入")
        self.request()
        self.request()
        with self.assertRaises(ConflictError):
            self.request()
        self.assertIsNotNone(services.claim(self.device.pk))
        self.assertIsNone(services.claim(self.device.pk))

    def test_output_only_candidate_and_idempotent_terminal(self):
        asset = business.create_design_element(actor=self.user, title="原始", kind="Asset")
        self.request(object_id=asset.pk, base_version=asset.version)
        item = services.claim(self.device.pk)
        services.finish(self.device.pk, item.pk, item.attempt_id, result=RESULT)
        services.finish(self.device.pk, item.pk, item.attempt_id, result=RESULT)
        with self.assertRaises(ConflictError):
            services.finish(self.device.pk, item.pk, item.attempt_id, result={**RESULT, "title": "不同"})
        asset.refresh_from_db()
        self.assertEqual(asset.title, "原始")
        self.assertEqual(asset.version, 1)
        self.assertFalse(Mission.objects.exists())

    def test_permissions_and_stale_before_claim(self):
        asset = business.create_design_element(actor=self.other, title="其他人")
        with self.assertRaises(PermissionDenied):
            self.request(object_id=asset.pk, base_version=1)
        asset = business.create_design_element(actor=self.user, title="自己的")
        item = self.request(object_id=asset.pk, base_version=1)
        business.update_design_element(actor=self.user, element_id=asset.pk, expected_version=1, changes={"title": "新版"})
        self.assertIsNone(services.claim(self.device.pk))
        item.refresh_from_db()
        self.assertEqual(item.status, "failed")

    def test_cancel_late_result_and_stop_acknowledgement(self):
        self.request()
        item = services.claim(self.device.pk)
        services.cancel(self.user, item.pk)
        with self.assertRaises(ConflictError):
            services.finish(self.device.pk, item.pk, item.attempt_id, result=RESULT)
        heartbeat = services.heartbeat(self.device.pk, item.pk, item.attempt_id)
        self.assertEqual(heartbeat.status, "cancelled")
        self.assertIsNone(heartbeat.stopped_at)
        services.heartbeat(self.device.pk, item.pk, item.attempt_id, stopped=True)
        item.refresh_from_db()
        self.assertIsNotNone(item.stopped_at)

    def test_lease_expiry_never_redispatches(self):
        self.request()
        item = services.claim(self.device.pk)
        AssistanceRequest.objects.filter(pk=item.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(services.claim(self.device.pk))
        item.refresh_from_db()
        self.assertEqual(item.status, "expired")
        with self.assertRaises(ConflictError):
            services.finish(self.device.pk, item.pk, item.attempt_id, result=RESULT)
        retry = self.request(retry_of=item.pk)
        self.assertEqual(retry.retry_of_id, item.pk)

    def test_late_result_persists_expiry_without_prior_poll(self):
        self.request()
        item = services.claim(self.device.pk)
        AssistanceRequest.objects.filter(pk=item.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(ConflictError):
            services.finish(self.device.pk, item.pk, item.attempt_id, result=RESULT)
        item.refresh_from_db()
        self.assertEqual(item.status, "expired")

    def test_payload_bounds_unknown_fields_and_unsafe_links(self):
        with self.assertRaises(ValidationFailure):
            self.request(draft={**DRAFT, "assignee_id": self.other.pk})
        with self.assertRaises(ValidationFailure):
            self.request(instructions="x" * 10001)
        self.request()
        item = services.claim(self.device.pk)
        for output in ({**RESULT, "parent_id": str(uuid.uuid4())}, {**RESULT, "content": "[x](javascript:alert)"}):
            with self.assertRaises(ValidationFailure):
                services.finish(self.device.pk, item.pk, item.attempt_id, result=output)

    def test_runner_api_validates_and_only_returns_assigned_request(self):
        self.request()
        response = self.runner.post("/api/agent-runner/claim/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        item = response.json()
        response = self.runner.post(f"/api/agent-runner/requests/{item['id']}/result/",
            {"attempt_id": item["attempt_id"], "result": RESULT}, format="json")
        self.assertEqual(response.status_code, 200)
        response = self.browser.get(f"/api/assistance-requests/{item['id']}/")
        self.assertEqual(response.json()["result"], RESULT)

    def test_review_uses_current_immutable_round_and_rejects_stale_adoption(self):
        mission = business.create_mission(actor=self.user, title="文档", acceptance_criteria="说明事实")
        mission = utils.claim(self.user, mission)
        mission = utils.submit(self.user, mission, description="材料文本")
        item = self.request(kind="review_assist", draft={}, object_id=mission.pk,
            base_version=mission.version, submission_id=mission.current_submission_id)
        self.assertEqual(item.input["draft"]["description"], "材料文本")
        item = services.claim(self.device.pk)
        result = {"criteria": [{"criterion": "事实", "assessment": "insufficient", "evidence": [], "unverified": []}],
            "missing_materials": [], "checks": ["人工核对"], "comment": "人工核对材料"}
        services.finish(self.device.pk, item.pk, item.attempt_id, result=result)
        mission.refresh_from_db()
        self.assertEqual(mission.status, "Submitted")
        utils.review(self.user, mission, decision="reject")
        item.refresh_from_db()
        self.assertTrue(services.stale_reason(item))
        self.assertEqual(mission.submissions.count(), 1)

    def test_template_private_links_and_extra_step_fields_rejected(self):
        step = {"key": "a", "title": "步骤", "content": "", "acceptance_criteria": "标准", "type": "Task", "priority": "P2", "tags": [], "prerequisite_keys": []}
        self.request(kind="template_generate", draft={"name": "", "description": "", "steps": []})
        item = services.claim(self.device.pk)
        for change in ({"assignee": self.user.pk}, {"content": f"[素材](/api/library/files/{uuid.uuid4()}/)"}, {"prerequisite_keys": ["missing"]}):
            with self.assertRaises(ValidationFailure):
                services.finish(self.device.pk, item.pk, item.attempt_id,
                    result={"name": "模板", "description": "", "steps": [{**step, **change}]})

    def test_attempt_and_device_isolation(self):
        self.request()
        item = services.claim(self.device.pk)
        with self.assertRaises(ConflictError):
            services.heartbeat(self.device.pk, item.pk, uuid.uuid4())
        device, token = services.create_device(self.other, name="其他设备", capabilities=list(protocol.KINDS))
        self.assertIsNone(services.claim(device.pk))
        self.runner.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.runner.post(f"/api/agent-runner/requests/{item.pk}/result/", {"attempt_id": str(item.attempt_id), "result": RESULT}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_comments_are_explicit_scoped_and_expire_when_changed(self):
        mission = business.create_mission(actor=self.user, title="验收")
        mission = utils.submit(self.user, utils.claim(self.user, mission))
        other = business.create_mission(actor=self.user, title="另一任务")
        comment = Comment.objects.create(mission=mission, author=self.user, content="只读意见")
        foreign = Comment.objects.create(mission=other, author=self.user, content="不应自动发送")
        params = dict(kind="review_assist", draft={}, object_id=mission.pk, base_version=mission.version,
            submission_id=mission.current_submission_id)
        with self.assertRaises(ValidationFailure):
            self.request(**params, comment_ids=[foreign.pk])
        item = self.request(**params, comment_ids=[comment.pk])
        self.assertEqual(len(item.input["comments"]), 1)
        self.assertEqual(item.input["comments"][0]["content"], "只读意见")
        comment.content = "修改后的意见"
        comment.save()
        self.assertTrue(services.stale_reason(item))

    def test_history_is_bounded_summary_and_cleanup_removes_old_inputs(self):
        item = self.request()
        data = self.browser.get("/api/assistance-requests/").json()
        self.assertNotIn("input", data["results"][0])
        self.assertNotIn("result", data["results"][0])
        AssistanceRequest.objects.filter(pk=item.pk).update(created_at=timezone.now() - timedelta(days=31))
        call_command("cleanup_assistance", verbosity=0)
        self.assertFalse(AssistanceRequest.objects.filter(pk=item.pk).exists())


class ProtocolTests(TestCase):
    def test_review_evidence_must_locate_actual_input_quote(self):
        result = {"criteria": [{"criterion": "颜色", "assessment": "supported", "evidence": [{"path": "/draft/description", "quote": "绿色"}], "unverified": []}], "missing_materials": [], "checks": [], "comment": "核对"}
        protocol.validate_result("review_assist", result)
        protocol.validate_evidence("review_assist", result, {"draft": {"description": "绿色披风"}})
        with self.assertRaises(protocol.ProtocolError):
            protocol.validate_evidence("review_assist", result, {"draft": {"description": "蓝色披风"}})
        with self.assertRaises(protocol.ProtocolError):
            protocol.validate_evidence("review_assist", result, {"draft": {}})

    def test_all_output_schemas_and_template_cycle(self):
        mission = {"title": "制作", "content": "", "acceptance_criteria": "轮廓一致", "type": "Task", "priority": "P2", "tags": []}
        step = {**mission, "key": "a", "prerequisite_keys": []}
        template = {"name": "角色", "description": "", "steps": [step]}
        review = {"criteria": [{"criterion": "轮廓", "assessment": "insufficient", "evidence": [], "unverified": ["未读取产物"]}],
            "missing_materials": [], "checks": ["人工检查"], "comment": "需要核对"}
        for kind, result in zip(protocol.KINDS, (RESULT, template, {**mission, "questions": []}, review)):
            self.assertEqual(protocol.validate_result(kind, result), result)
        cycle = copy.deepcopy(template)
        cycle["steps"][0]["prerequisite_keys"] = ["a"]
        with self.assertRaises(protocol.ProtocolError):
            protocol.validate_result("template_generate", cycle)
        with self.assertRaises(protocol.ProtocolError):
            protocol.validate_result("review_assist", {**review, "decision": "accept"})


class ClaimConcurrencyTests(TransactionTestCase):
    def test_two_claims_one_attempt(self):
        user = User.objects.create_user("concurrent")
        device, _ = services.create_device(user, name="本机", capabilities=list(protocol.KINDS))
        for _ in range(2):
            services.create_request(user, device_id=device.pk, kind="design_polish", idempotency_key=uuid.uuid4(), draft=DRAFT)
        outcomes = run_concurrently(lambda: services.claim(device.pk), lambda: services.claim(device.pk))
        self.assertEqual(list(outcomes.values()), ["ok", "ok"])
        self.assertEqual(AssistanceRequest.objects.filter(status="running").count(), 1)
        self.assertEqual(AssistanceRequest.objects.filter(status="queued").count(), 1)
