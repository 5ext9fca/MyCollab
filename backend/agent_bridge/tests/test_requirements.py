import uuid
from django.test import TestCase
from rest_framework.test import APIClient
from accounts.models import User
from missions import services as business
from agent_bridge import protocol, services
from agent_bridge.models import AssistanceRequest

MARKDOWN = '\n\n'.join(['# Agent 需求文档', '## 目标\n保持绿色披风', '## 范围与约束\n不得增加武器', '## 实施要求\n整理角色说明', '## 交付物\n角色说明', '## 验收标准\n明确颜色', '## 待澄清事项\n尺寸未提供', '## 来源\n任务与关联资产'])


class RequirementsTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user('exporter')
        self.author = User.objects.create_user('author')
        self.asset = business.create_design_element(actor=self.author, kind='Asset', title='披风', content='绿色')
        self.mission = business.create_mission(actor=self.author, title='角色文档', content='不得增加武器', acceptance_criteria='明确披风颜色', asset_ids=[self.asset.pk])
        self.device, self.token = services.create_device(self.actor, name='文档设备', capabilities=['agent_requirements'])
        self.browser = APIClient(); self.browser.force_login(self.actor)
        self.runner = APIClient(); self.runner.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')

    def create(self, **extra):
        payload = dict(device_id=str(self.device.pk), kind='agent_requirements', idempotency_key=str(uuid.uuid4()), draft={}, object_id=str(self.mission.pk), base_version=self.mission.version)
        payload.update(extra)
        return self.browser.post('/api/assistance-requests/', payload, format='json')

    def test_read_only_export_roundtrip_and_owner_isolation(self):
        key = str(uuid.uuid4())
        response = self.create(idempotency_key=key)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.create(idempotency_key=key).data['id'], response.data['id'])
        claimed = self.runner.post('/api/agent-runner/claim/').json()
        self.assertEqual(claimed['input']['mission']['content'], '不得增加武器')
        self.assertEqual(claimed['input']['contexts'][0]['content'], '绿色')
        result = self.runner.post(f"/api/agent-runner/requests/{claimed['id']}/result/", {'attempt_id': claimed['attempt_id'], 'result': {'markdown': MARKDOWN}}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        detail = self.browser.get(f"/api/assistance-requests/{claimed['id']}/").json()
        self.assertEqual(detail['result']['markdown'], MARKDOWN)
        self.assertEqual(detail['stale_reason'], '')
        self.mission.refresh_from_db()
        self.assertEqual(self.mission.status, 'Open')
        self.assertEqual(self.mission.version, 1)
        self.browser.force_login(self.author)
        self.assertEqual(self.browser.get(f"/api/assistance-requests/{claimed['id']}/").status_code, 404)

    def test_context_change_prevents_stale_result(self):
        self.assertEqual(self.create().status_code, 201)
        claimed = services.claim(self.device.pk)
        self.asset.content = '蓝色'; self.asset.version += 1; self.asset.save()
        self.assertTrue(services.stale_reason(claimed))
        result = self.runner.post(f'/api/agent-runner/requests/{claimed.pk}/result/', {'attempt_id': str(claimed.attempt_id), 'result': {'markdown': MARKDOWN}}, format='json')
        self.assertEqual(result.status_code, 409)
        self.assertIsNone(AssistanceRequest.objects.get(pk=claimed.pk).result)

    def test_client_cannot_supply_unreviewed_sources_or_missing_mission(self):
        self.assertEqual(self.create(draft={'content': '伪造内容'}).status_code, 400)
        self.assertEqual(self.create(object_id=None).status_code, 400)
        self.assertEqual(self.create(base_version=99).status_code, 409)
        self.assertEqual(self.create(instructions='运行代码').status_code, 400)
        self.assertEqual(self.create(context_ids=[str(self.asset.pk)]).status_code, 400)

    def test_markdown_shape_and_old_delegation_are_rejected(self):
        for value in ({'markdown': ''}, {'markdown': '# 随意文本'}, {'markdown': MARKDOWN, 'command': 'run'}):
            with self.assertRaises(protocol.ProtocolError):
                protocol.validate_result('agent_requirements', value)
        for kind in ['image_generate', 'image_edit', 'code_implement']:
            self.assertEqual(self.create(kind=kind).status_code, 400)
        self.assertEqual(self.browser.post('/api/mission-executions/', {}, format='json').status_code, 404)
        self.assertEqual(self.browser.post('/api/code-executions/', {}, format='json').status_code, 404)
