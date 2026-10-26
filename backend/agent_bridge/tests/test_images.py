import hashlib
import struct
import tempfile
import uuid
import zlib
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from agent_bridge import services as bridge
from agent_bridge.image_protocol import inspect_png, validate_manifest
from agent_bridge.models import AssistanceRequest
from common.exceptions import ConflictError, NotFound, PermissionDenied, ValidationFailure
from library.models import LibraryFile
from library.services import save_library_file, delete_library_file
from missions import services
from missions.models import MissionExecution, SubmissionExecutionArtifact
from missions.tests import utils
from missions.tests.test_concurrency_features import run_concurrently


def png(red=0):
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(bytes([0, red, 180, 0]))) + chunk(b'IEND', b'')


def manifest():
    return {'candidates': [dict(key=f'v{i}', name=f'leaf-{i}.png', **inspect_png(png(i))) for i in range(2)]}


class ImageExecutionTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        setting = override_settings(MEDIA_ROOT=self.directory.name)
        setting.enable()
        self.addCleanup(setting.disable)
        self.actor = User.objects.create_user('image-owner')
        self.other = User.objects.create_user('other')
        self.device, self.token = bridge.create_device(self.actor, name='图像本机', capabilities=['image_generate', 'image_edit'])
        self.asset = services.create_design_element(actor=self.actor, title='树叶', kind='Asset')
        self.mission = services.create_mission(actor=self.actor, title='图标', asset_ids=[self.asset.pk])
        self.mission = utils.claim(self.actor, self.mission)
        self.client = APIClient()
        self.client.force_login(self.actor)

    def create(self, **changes):
        args = dict(actor=self.actor, mission_id=self.mission.pk, asset_id=self.asset.pk, device_id=self.device.pk,
            kind='image_generate', expected_version=self.mission.version, asset_version=self.asset.version,
            instructions='生成树叶', reference_ids=[], idempotency_key=uuid.uuid4())
        args.update(changes)
        return services.create_execution(**args)

    def ready(self):
        execution = self.create()
        request = bridge.claim(self.device.pk)
        services.publish_execution_candidates(device_id=self.device.pk, request_id=request.pk, attempt_id=request.attempt_id, manifest=manifest())
        return execution, dict(device_id=self.device.pk, request_id=request.pk, attempt_id=request.attempt_id)

    def test_candidates_stay_local_until_explicit_choice_then_manual_submission(self):
        execution, args = self.ready()
        self.assertFalse(LibraryFile.objects.exists())
        self.mission.refresh_from_db()
        self.assertEqual(self.mission.status, 'InProgress')
        with self.assertRaises(PermissionDenied):
            services.upload_execution_candidate(**args, key='v0', upload=SimpleUploadedFile('leaf.png', png()))
        services.select_execution_candidates(**args, keys=['v0'])
        candidate = services.upload_execution_candidate(**args, key='v0', upload=SimpleUploadedFile('leaf.png', png()))
        duplicate = services.upload_execution_candidate(**args, key='v0', upload=SimpleUploadedFile('leaf.png', png()))
        self.assertEqual(candidate.file_id, duplicate.file_id)
        self.assertEqual(LibraryFile.objects.count(), 1)
        self.assertEqual(candidate.file.owner_id, self.actor.pk)
        services.complete_execution(**args)
        self.mission.refresh_from_db()
        self.assertEqual(self.mission.status, 'InProgress')
        mission = utils.submit(self.actor, self.mission, execution_candidate_ids=[candidate.pk])
        self.assertEqual(SubmissionExecutionArtifact.objects.count(), 1)
        with self.assertRaises(ConflictError):
            services.cancel_execution(actor=self.actor, execution_id=execution.pk)
        with self.assertRaises(ConflictError):
            delete_library_file(actor=self.actor, file_id=candidate.file_id)
        mission = utils.review(self.actor, mission)
        self.assertEqual(mission.status, 'Done')

    def test_owner_status_version_asset_and_edit_reference(self):
        other_device, _ = bridge.create_device(self.other, name='另一台设备', capabilities=['image_generate'])
        with self.assertRaises(PermissionDenied):
            self.create(actor=self.other, device_id=other_device.pk)
        with self.assertRaises(ConflictError):
            self.create(expected_version=1)
        with self.assertRaises(ValidationFailure):
            self.create(kind='image_edit')
        foreign = save_library_file(actor=self.other, upload=SimpleUploadedFile('ref.png', png()))
        with self.assertRaises(ValidationFailure):
            self.create(reference_ids=[foreign.pk])
        mine = save_library_file(actor=self.actor, upload=SimpleUploadedFile('ref.png', png()))
        execution = self.create(kind='image_edit', reference_ids=[mine.pk])
        request = bridge.claim(self.device.pk)
        args = dict(device_id=self.device.pk, request_id=request.pk, attempt_id=request.attempt_id)
        self.assertEqual(services.execution_reference(**args, file_id=mine.pk).pk, mine.pk)
        with self.assertRaises(NotFound):
            services.execution_reference(**args, file_id=foreign.pk)
        services.update_design_element(actor=self.actor, element_id=self.asset.pk, expected_version=self.asset.version, changes={'title': '新资产版本'})
        with self.assertRaises(ConflictError):
            services.publish_execution_candidates(**args, manifest=manifest())
        request.refresh_from_db()
        self.assertEqual(request.status, 'expired')

    def test_idempotency_manifest_selection_and_invalid_upload(self):
        key = uuid.uuid4()
        execution = self.create(idempotency_key=key)
        self.assertEqual(self.create(idempotency_key=key).pk, execution.pk)
        with self.assertRaises(ConflictError):
            self.create(idempotency_key=key, instructions='另一要求')
        request = bridge.claim(self.device.pk)
        args = dict(device_id=self.device.pk, request_id=request.pk, attempt_id=request.attempt_id)
        services.publish_execution_candidates(**args, manifest=manifest())
        services.publish_execution_candidates(**args, manifest=manifest())
        self.assertEqual(execution.candidates.count(), 2)
        services.select_execution_candidates(**args, keys=['v1'])
        with self.assertRaises(ConflictError):
            services.select_execution_candidates(**args, keys=['v0'])
        with self.assertRaises(ValidationFailure):
            services.upload_execution_candidate(**args, key='v1', upload=SimpleUploadedFile('bad.png', png()))
        with self.assertRaises(ValidationFailure):
            services.upload_execution_candidate(**args, key='v1', upload=SimpleUploadedFile('bad.png', b'<html>bad</html>'))
        with self.assertRaises(ConflictError):
            services.complete_execution(**args)
        self.assertFalse(LibraryFile.objects.exists())

    def test_cancellation_and_waiting_expiry_reject_late_uploads(self):
        execution, args = self.ready()
        services.select_execution_candidates(**args, keys=['v0'])
        services.cancel_execution(actor=self.actor, execution_id=execution.pk)
        with self.assertRaises(ConflictError):
            services.upload_execution_candidate(**args, key='v0', upload=SimpleUploadedFile('leaf.png', png()))
        second, args = self.ready()
        AssistanceRequest.objects.filter(pk=second.request_id).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(ConflictError):
            services.select_execution_candidates(**args, keys=['v0'])
        self.assertFalse(LibraryFile.objects.exists())

    def test_runner_auth_and_multipart_upload(self):
        execution, args = self.ready()
        runner = APIClient()
        runner.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        base = f'/api/agent-runner/requests/{execution.request_id}/'
        response = runner.post(base + 'selection/', {'attempt_id': str(args['attempt_id']), 'keys': ['v0']}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        response = runner.post(base + 'candidates/v0/upload/', {'attempt_id': str(args['attempt_id']), 'file': SimpleUploadedFile('leaf.png', png())}, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(runner.post(base + 'complete/', {'attempt_id': str(args['attempt_id'])}, format='json').status_code, 200)
        self.assertEqual(runner.get('/api/library/files/').status_code, 403)
        response = self.client.get('/api/mission-executions/', {'mission': str(self.mission.pk)})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['results']), 1)

    def test_revocation_inactive_owner_and_foreign_attempt_reject_writes(self):
        execution, args = self.ready()
        foreign_device, _ = bridge.create_device(self.other, name='其他设备', capabilities=['image_generate'])
        with self.assertRaises(NotFound):
            services.select_execution_candidates(**{**args, 'device_id': foreign_device.pk}, keys=['v0'])
        with self.assertRaises(ConflictError):
            services.select_execution_candidates(**{**args, 'attempt_id': uuid.uuid4()}, keys=['v0'])
        bridge.revoke_device(self.actor, self.device.pk)
        with self.assertRaises(PermissionDenied):
            services.select_execution_candidates(**args, keys=['v0'])
        execution.request.refresh_from_db()
        self.assertEqual(execution.request.status, 'cancelled')
        self.device, _ = bridge.create_device(self.actor, name='新设备', capabilities=['image_generate'])
        execution, args = self.ready()
        self.actor.is_active = False
        self.actor.save(update_fields=['is_active'])
        with self.assertRaises(PermissionDenied):
            services.select_execution_candidates(**args, keys=['v0'])
        self.assertFalse(LibraryFile.objects.exists())

    def test_partial_upload_is_not_complete_and_stale_mission_blocks_remaining_upload(self):
        execution, args = self.ready()
        services.select_execution_candidates(**args, keys=['v0', 'v1'])
        candidate = services.upload_execution_candidate(**args, key='v0', upload=SimpleUploadedFile('a.png', png()))
        with self.assertRaises(ConflictError):
            services.complete_execution(**args)
        with self.assertRaises(ValidationFailure):
            utils.submit(self.actor, self.mission, execution_candidate_ids=[candidate.pk])
        services.update_mission(actor=self.actor, mission_id=self.mission.pk, expected_version=self.mission.version, changes={'title': '新目标'})
        with self.assertRaises(ConflictError):
            services.upload_execution_candidate(**args, key='v1', upload=SimpleUploadedFile('b.png', png(1)))
        self.assertEqual(LibraryFile.objects.count(), 1)
        execution.request.refresh_from_db()
        self.assertEqual(execution.request.status, 'expired')

    def test_cleanup_preserves_artifacts_and_retry_version(self):
        from django.core.management import call_command
        from io import StringIO
        execution, args = self.ready()
        services.select_execution_candidates(**args, keys=['v0'])
        services.upload_execution_candidate(**args, key='v0', upload=SimpleUploadedFile('a.png', png()))
        services.complete_execution(**args)
        later = self.create(previous_id=execution.pk)
        self.assertEqual(later.version, 2)
        self.assertEqual(later.previous_id, execution.pk)
        AssistanceRequest.objects.filter(pk=execution.request_id).update(created_at=timezone.now() - timedelta(days=31))
        call_command('cleanup_assistance', stdout=StringIO())
        execution.request.refresh_from_db()
        self.assertEqual(execution.request.input, {})
        self.assertEqual(execution.candidates.filter(file__isnull=False).count(), 1)
        self.assertEqual(LibraryFile.objects.count(), 1)

    def test_png_invalid_compressed_stream_and_manifest_path_are_rejected(self):
        from agent_bridge.protocol import ProtocolError
        broken = png().replace(zlib.compress(bytes([0, 0, 180, 0])), zlib.compress(bytes([0, 0, 180, 1])))
        with self.assertRaises(ProtocolError):
            inspect_png(broken)
        value = manifest()
        value['candidates'][0]['name'] = '../outside.png'
        with self.assertRaises(ProtocolError):
            validate_manifest(value)
        value = manifest()
        value['candidates'][0]['size'] = 21 * 1024 * 1024
        with self.assertRaises(ProtocolError):
            validate_manifest(value)


    def test_running_lease_loss_never_requeues_and_asset_change_blocks_submission(self):
        execution = self.create()
        request = bridge.claim(self.device.pk)
        AssistanceRequest.objects.filter(pk=request.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(bridge.claim(self.device.pk))
        request.refresh_from_db()
        self.assertEqual(request.status, 'expired')
        with self.assertRaises(ConflictError):
            services.publish_execution_candidates(device_id=self.device.pk, request_id=request.pk, attempt_id=request.attempt_id, manifest=manifest())
        execution, args = self.ready()
        services.select_execution_candidates(**args, keys=['v0'])
        candidate = services.upload_execution_candidate(**args, key='v0', upload=SimpleUploadedFile('a.png', png()))
        services.complete_execution(**args)
        services.update_design_element(actor=self.actor, element_id=self.asset.pk, expected_version=self.asset.version, changes={'title': '新资产'})
        with self.assertRaises(ValidationFailure):
            utils.submit(self.actor, self.mission, execution_candidate_ids=[candidate.pk])


class ImageClaimConcurrencyTests(TransactionTestCase):
    def test_text_and_image_share_one_device_slot(self):
        actor = User.objects.create_user('concurrent-images')
        device, _ = bridge.create_device(actor, name='本机', capabilities=['design_polish', 'image_generate'])
        asset = services.create_design_element(actor=actor, title='资产', kind='Asset')
        mission = utils.claim(actor, services.create_mission(actor=actor, title='任务', asset_ids=[asset.pk]))
        services.create_execution(actor=actor, mission_id=mission.pk, asset_id=asset.pk, device_id=device.pk,
            kind='image_generate', expected_version=mission.version, asset_version=asset.version,
            instructions='图像', reference_ids=[], idempotency_key=uuid.uuid4())
        bridge.create_request(actor, device_id=device.pk, kind='design_polish', idempotency_key=uuid.uuid4(), draft={'title': 'x', 'content': '', 'kind': 'Design'})
        outcomes = run_concurrently(lambda: bridge.claim(device.pk), lambda: bridge.claim(device.pk))
        self.assertEqual(list(outcomes.values()), ['ok', 'ok'])
        self.assertEqual(AssistanceRequest.objects.filter(status='running').count(), 1)

    def test_concurrent_versions_are_distinct(self):
        actor = User.objects.create_user('version-owner')
        device, _ = bridge.create_device(actor, name='本机', capabilities=['image_generate'])
        asset = services.create_design_element(actor=actor, title='资产', kind='Asset')
        mission = utils.claim(actor, services.create_mission(actor=actor, title='任务', asset_ids=[asset.pk]))
        def create():
            return services.create_execution(actor=actor, mission_id=mission.pk, asset_id=asset.pk, device_id=device.pk,
                kind='image_generate', expected_version=mission.version, asset_version=asset.version,
                instructions='图像', reference_ids=[], idempotency_key=uuid.uuid4())
        outcomes = run_concurrently(create, create)
        self.assertEqual(list(outcomes.values()), ['ok', 'ok'])
        self.assertEqual(list(MissionExecution.objects.filter(mission=mission).order_by('version').values_list('version', flat=True)), [1, 2])
