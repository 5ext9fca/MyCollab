import hashlib
import json
import tempfile
import uuid
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from agent_bridge import services as bridge
from agent_bridge.models import AssistanceRequest
from common.exceptions import ConflictError, PermissionDenied, ValidationFailure, NotFound
from library.models import LibraryFile
from library.services import delete_library_file
from missions import services
from missions.models import CodeExecution
from missions.tests import utils
from missions.tests.test_concurrency_features import run_concurrently

PATCH = b'diff --git a/rules.py b/rules.py\n--- a/rules.py\n+++ b/rules.py\n@@ -1 +1 @@\n-old\n+new\n'
REPORT = {'schema_version': 1, 'base_commit': 'a' * 40, 'summary': '实现规则', 'source': 'local_runner',
    'changed_files': [{'path': 'rules.py', 'change': 'modified'}],
    'verification': [{'id': 'unit', 'label': '单元测试', 'status': 'passed', 'exit_code': 0, 'duration_ms': 10}]}
REPORT_BYTES = json.dumps(REPORT, ensure_ascii=False).encode()
MANIFEST = {'base_commit': 'a' * 40, 'patch_sha256': hashlib.sha256(PATCH).hexdigest(), 'patch_size': len(PATCH),
    'report_sha256': hashlib.sha256(REPORT_BYTES).hexdigest(), 'report_size': len(REPORT_BYTES)}


class CodeExecutionTests(TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        setting = override_settings(MEDIA_ROOT=temp.name)
        setting.enable(); self.addCleanup(setting.disable)
        self.actor = User.objects.create_user('code-owner')
        self.other = User.objects.create_user('other-code-owner')
        self.device, self.token = bridge.create_device(self.actor, name='OpenCode', capabilities=['code_implement'])
        self.mission = utils.claim(self.actor, services.create_mission(actor=self.actor, title='规则实现'))
        self.browser = APIClient(); self.browser.force_login(self.actor)
        self.runner = APIClient(); self.runner.credentials(HTTP_AUTHORIZATION='Bearer ' + self.token)

    def create(self, **changes):
        args = dict(actor=self.actor, mission_id=self.mission.pk, device_id=self.device.pk,
            repository_key_value='demo', expected_version=self.mission.version, instructions='实现规则', idempotency_key=uuid.uuid4())
        args.update(changes)
        return services.create_code_execution(**args)

    def ready(self):
        execution = self.create()
        request = bridge.claim(self.device.pk)
        args = dict(device_id=self.device.pk, request_id=request.pk, attempt_id=request.attempt_id)
        services.stage_code_execution(**args, manifest=MANIFEST)
        return execution, args

    def publish(self, args, patch=PATCH, report=REPORT_BYTES):
        return services.publish_code_execution(**args, patch_upload=SimpleUploadedFile('patch.txt', patch), report_upload=SimpleUploadedFile('report.txt', report))

    def test_stage_no_files_publish_idempotent_and_manual_submission(self):
        execution, args = self.ready()
        self.assertFalse(LibraryFile.objects.exists())
        result = self.publish(args)
        again = self.publish(args)
        self.assertEqual(result.patch_id, again.patch_id)
        self.assertEqual(LibraryFile.objects.count(), 1)
        self.mission.refresh_from_db(); self.assertEqual(self.mission.status, 'InProgress')
        mission = utils.submit(self.actor, self.mission, code_execution_ids=[result.pk])
        self.assertEqual(mission.current_submission.code_artifacts.count(), 1)
        response = self.browser.get(f'/api/missions/{mission.pk}/submissions/')
        self.assertEqual(response.data['results'][0]['code_artifacts'][0]['report'], REPORT)
        with self.assertRaises(ConflictError):
            services.cancel_code_execution(actor=self.actor, execution_id=execution.pk)
        with self.assertRaises(ConflictError):
            delete_library_file(actor=self.actor, file_id=result.patch_id)
        self.assertEqual(utils.review(self.actor, mission).status, 'Done')

    def test_creation_scope_idempotency_and_shared_quota(self):
        key = uuid.uuid4()
        old = self.create(idempotency_key=key)
        self.assertEqual(self.create(idempotency_key=key).pk, old.pk)
        with self.assertRaises(ConflictError): self.create(idempotency_key=key, instructions='不同要求')
        with self.assertRaises(ValidationFailure): self.create(repository_key_value='/tmp/repo')
        with self.assertRaises(ConflictError): self.create(expected_version=1)
        device, _ = bridge.create_device(self.other, name='其他设备', capabilities=['code_implement'])
        with self.assertRaises(PermissionDenied): self.create(actor=self.other, device_id=device.pk)
        self.create(); self.create()
        with self.assertRaises(ConflictError): self.create()

    def test_attempt_owner_cancel_revoke_and_late_upload(self):
        execution, args = self.ready()
        with self.assertRaises(ConflictError): self.publish({**args, 'attempt_id': uuid.uuid4()})
        device, _ = bridge.create_device(self.other, name='其他', capabilities=['code_implement'])
        with self.assertRaises(NotFound): self.publish({**args, 'device_id': device.pk})
        bridge.cancel(self.actor, execution.request_id)
        with self.assertRaises(ConflictError): self.publish(args)
        second, args = self.ready()
        bridge.revoke_device(self.actor, self.device.pk)
        with self.assertRaises(PermissionDenied): self.publish(args)
        second.request.refresh_from_db(); self.assertEqual(second.request.status, 'cancelled')
        self.assertFalse(LibraryFile.objects.exists())

    def test_version_expiry_hash_mismatch_and_unpublished_submit(self):
        execution, args = self.ready()
        with self.assertRaises(ValidationFailure): self.publish(args, patch=PATCH + b'changed')
        with self.assertRaises(ValidationFailure): utils.submit(self.actor, self.mission, code_execution_ids=[execution.pk])
        services.update_mission(actor=self.actor, mission_id=self.mission.pk, expected_version=self.mission.version, changes={'title': '新目标'})
        with self.assertRaises(ConflictError): self.publish(args)
        execution.request.refresh_from_db(); self.assertEqual(execution.request.status, 'expired')
        self.assertFalse(LibraryFile.objects.exists())

    def test_waiting_expiry_and_cleanup_keep_published_history(self):
        from io import StringIO
        execution, args = self.ready()
        result = self.publish(args)
        second = self.create(previous_id=execution.pk)
        self.assertEqual(second.version, 2)
        request = bridge.claim(self.device.pk)
        second_args = dict(device_id=self.device.pk, request_id=request.pk, attempt_id=request.attempt_id)
        services.stage_code_execution(**second_args, manifest=MANIFEST)
        AssistanceRequest.objects.filter(pk=request.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(ConflictError): self.publish(second_args)
        AssistanceRequest.objects.filter(pk=execution.request_id).update(created_at=timezone.now() - timedelta(days=31))
        call_command('cleanup_assistance', stdout=StringIO())
        result.refresh_from_db(); self.assertIsNotNone(result.patch_id); self.assertEqual(result.report, REPORT)
        result.request.refresh_from_db(); self.assertEqual(result.request.input, {})

    def test_browser_api_and_runner_multipart_are_scoped(self):
        response = self.browser.post('/api/code-executions/', {'mission_id': str(self.mission.pk), 'device_id': str(self.device.pk), 'repository_key': 'demo', 'expected_version': self.mission.version, 'instructions': '实现规则', 'idempotency_key': str(uuid.uuid4())}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        request = bridge.claim(self.device.pk)
        base = f'/api/agent-runner/requests/{request.pk}/'
        response = self.runner.post(base + 'code-manifest/', {'attempt_id': str(request.attempt_id), 'manifest': MANIFEST}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        response = self.runner.post(base + 'code-publish/', {'attempt_id': str(request.attempt_id), 'patch': SimpleUploadedFile('patch.txt', PATCH), 'report': SimpleUploadedFile('report.txt', REPORT_BYTES)}, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['report'], REPORT)
        self.assertEqual(self.runner.get('/api/library/files/').status_code, 403)
        self.assertEqual(self.browser.get('/api/code-executions/', {'mission': str(self.mission.pk)}).data['count'], 1)

    def test_stale_queued_claim_and_running_heartbeat(self):
        execution = self.create()
        self.mission = services.update_mission(actor=self.actor, mission_id=self.mission.pk, expected_version=self.mission.version, changes={'title': '变更目标'})
        self.assertIsNone(bridge.claim(self.device.pk))
        execution.request.refresh_from_db()
        self.assertEqual(execution.request.status, 'failed')
        execution = self.create()
        request = bridge.claim(self.device.pk)
        self.mission = services.update_mission(actor=self.actor, mission_id=self.mission.pk, expected_version=self.mission.version, changes={'title': '再次变更'})
        response = bridge.heartbeat(self.device.pk, request.pk, request.attempt_id)
        self.assertEqual(response.status, 'expired')

    def test_report_extra_fields_and_patch_paths_are_rejected(self):
        execution, args = self.ready()
        changed = dict(REPORT, changed_files=[{'path': 'other.py', 'change': 'modified'}])
        data = json.dumps(changed).encode()
        execution.manifest = {**MANIFEST, 'report_sha256': hashlib.sha256(data).hexdigest(), 'report_size': len(data)}
        execution.save(update_fields=['manifest'])
        with self.assertRaises(ValidationFailure): self.publish(args, report=data)
        self.assertFalse(LibraryFile.objects.exists())

    def test_no_change_error_is_preserved_without_artifact(self):
        execution = self.create()
        request = bridge.claim(self.device.pk)
        result = bridge.finish(self.device.pk, request.pk, request.attempt_id, error='no_changes')
        self.assertEqual(result.status, 'failed')
        self.assertEqual(result.error, 'no_changes')
        self.assertFalse(LibraryFile.objects.exists())


class CodeConcurrencyTests(TransactionTestCase):
    def test_concurrent_versions_and_shared_device_slot(self):
        actor = User.objects.create_user('concurrent-code')
        device, _ = bridge.create_device(actor, name='本机', capabilities=['code_implement', 'design_polish'])
        mission = utils.claim(actor, services.create_mission(actor=actor, title='代码'))
        def create():
            services.create_code_execution(actor=actor, mission_id=mission.pk, device_id=device.pk, repository_key_value='demo', expected_version=mission.version, instructions='实现', idempotency_key=uuid.uuid4())
        self.assertEqual(list(run_concurrently(create, create).values()), ['ok', 'ok'])
        self.assertEqual(list(CodeExecution.objects.order_by('version').values_list('version', flat=True)), [1, 2])
        bridge.create_request(actor, device_id=device.pk, kind='design_polish', draft={'title': 'x', 'content': '', 'kind': 'Design'}, idempotency_key=uuid.uuid4())
        self.assertEqual(list(run_concurrently(lambda: bridge.claim(device.pk), lambda: bridge.claim(device.pk)).values()), ['ok', 'ok'])
        self.assertEqual(AssistanceRequest.objects.filter(status='running').count(), 1)
