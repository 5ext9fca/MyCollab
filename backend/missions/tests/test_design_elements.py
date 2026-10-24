"""设计上下文、权限、归档与关联的端到端约束。"""
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient
from accounts.models import User
from library.models import LibraryFile
from missions import services
from missions.exceptions import ConflictError, PermissionDenied, ValidationFailure
from missions.models import DesignElement, Mission
from .test_concurrency_features import run_concurrently


class DesignElementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner')
        self.other = User.objects.create_user('other')
        self.admin = User.objects.create_user('admin', is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.root = services.create_design_element(actor=self.owner, title='敌人系统')
        self.asset = services.create_design_element(actor=self.owner, title='森林守卫', kind='Asset', parent=self.root.pk)

    def update(self, element, **changes):
        result = services.update_design_element(actor=self.owner, element_id=element.id, expected_version=element.version, changes=changes)
        element.refresh_from_db()
        return result

    def test_tree_cycle_archive_restore_and_versions(self):
        with self.assertRaises(ConflictError):
            self.update(self.root, parent=self.asset.pk)
        with self.assertRaises(ConflictError):
            self.update(self.root, archived=True)
        self.update(self.asset, archived=True)
        self.update(self.root, archived=True)
        with self.assertRaises(ConflictError):
            self.update(self.asset, archived=False)
        with self.assertRaises(ConflictError):
            self.update(self.root, title='归档内容')
        self.update(self.root, archived=False)
        self.update(self.asset, archived=False)
        with self.assertRaises(ConflictError):
            services.update_design_element(actor=self.owner, element_id=self.asset.pk, expected_version=1, changes={'title': '过期'})
        self.assertTrue(self.asset.events.filter(action='restored').exists())

    def test_permissions_immutable_kind_and_markdown_owner(self):
        with self.assertRaises(PermissionDenied):
            services.update_design_element(actor=self.other, element_id=self.asset.pk, expected_version=1, changes={'title': '越权'})
        file = LibraryFile.objects.create(owner=self.admin, file='library/admin/test.png', original_name='test.png', content_type='image/png', size=1)
        for content in [f'![图](/api/library/files/{file.pk}/)', '[链接](javascript:alert(1))', '<img src="/media/secret.png">']:
            with self.assertRaises(ValidationFailure):
                services.update_design_element(actor=self.admin, element_id=self.asset.pk, expected_version=1, changes={'content': content})
        services.update_design_element(actor=self.admin, element_id=self.asset.pk, expected_version=1, changes={'content': '[说明](https://example.org)'})
        response = self.client.patch(f'/api/design-elements/{self.asset.pk}/', {'expected_version': 2, 'kind': 'Design'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.delete(f'/api/design-elements/{self.asset.pk}/').status_code, 405)

    def test_mission_link_archive_retention_freeze_and_no_inheritance(self):
        mission = services.create_mission(actor=self.owner, title='建模', design_element_id=self.asset.pk)
        child = services.create_mission(actor=self.owner, title='子任务', parent_id=mission.pk)
        self.assertIsNone(child.design_element_id)
        self.update(self.asset, archived=True)
        mission = services.update_mission(actor=self.owner, mission_id=mission.pk, expected_version=mission.version, changes={'title': '修改标题'})
        self.assertEqual(mission.design_element_id, self.asset.pk)
        with self.assertRaises(ConflictError):
            services.create_mission(actor=self.owner, title='新任务', design_element_id=self.asset.pk)
        self.assertTrue(self.client.get(f'/api/missions/{mission.pk}/').data['design_element']['archived'])
        mission = services.update_mission(actor=self.owner, mission_id=mission.pk, expected_version=mission.version, changes={'design_element_id': None})
        self.assertIsNone(mission.design_element_id)
        services.cancel_mission(actor=self.owner, mission_id=mission.pk, expected_version=mission.version)
        mission.refresh_from_db()
        with self.assertRaises(ConflictError):
            services.update_mission(actor=self.owner, mission_id=mission.pk, expected_version=mission.version, changes={'design_element_id': self.root.pk})

    def test_api_filter_progress_and_ancestor_path(self):
        response = self.client.post('/api/missions/', {'title': '原画', 'design_element_id': str(self.asset.pk)}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        first = response.data['id']
        old = services.create_mission(actor=self.owner, title='旧任务')
        detail = self.client.get(f'/api/design-elements/{self.asset.pk}/').data
        self.assertEqual(detail['ancestors'][0]['id'], str(self.root.pk))
        self.assertEqual(detail['progress']['effective_total'], 1)
        self.assertIsNone(self.client.get(f'/api/design-elements/{self.root.pk}/').data['progress']['progress'])
        for endpoint in ['/api/missions/', '/api/workspace/graph/']:
            response = self.client.get(endpoint, {'design_element': str(self.asset.pk), 'context': 'false'})
            self.assertEqual(response.status_code, 200)
            rows = response.data.get('results', response.data.get('nodes'))
            self.assertEqual([str(row['id']) for row in rows], [first])
        response = self.client.get('/api/missions/', {'design_element': 'none'})
        self.assertEqual(response.data['results'][0]['id'], str(old.pk))
        self.assertEqual(self.client.get('/api/workspace/overview/', {'design_element': str(self.asset.pk)}).status_code, 200)
        self.assertEqual(self.client.get('/api/design-elements/', {'parent': str(self.root.pk)}).data['count'], 1)
        self.assertEqual(self.client.patch(f'/api/design-elements/{self.root.pk}/', {'title': '缺版本'}, format='json').status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/design-elements/').status_code, 403)


class DesignConcurrencyTests(TransactionTestCase):
    def test_concurrent_edits_require_current_version(self):
        owner = User.objects.create_user('owner')
        element = services.create_design_element(actor=owner, title='初始设计')
        results = run_concurrently(
            lambda: services.update_design_element(actor=owner, element_id=element.pk, expected_version=1, changes={'title': '方案甲'}),
            lambda: services.update_design_element(actor=owner, element_id=element.pk, expected_version=1, changes={'title': '方案乙'}),
        )
        self.assertEqual(list(results.values()).count('ok'), 1, results)
        errors = [value for value in results.values() if value != 'ok']
        self.assertEqual(errors[0].code, 'version_conflict')
        element.refresh_from_db()
        self.assertEqual(element.version, 2)
        self.assertEqual(element.events.filter(action='updated').count(), 1)

    def test_opposite_moves_cannot_create_cycle(self):
        owner = User.objects.create_user('owner')
        a = services.create_design_element(actor=owner, title='甲')
        b = services.create_design_element(actor=owner, title='乙')
        results = run_concurrently(
            lambda: services.update_design_element(actor=owner, element_id=a.pk, expected_version=1, changes={'parent': b.pk}),
            lambda: services.update_design_element(actor=owner, element_id=b.pk, expected_version=1, changes={'parent': a.pk}),
        )
        self.assertEqual(list(results.values()).count('ok'), 1, results)
        self.assertEqual(DesignElement.objects.filter(parent__isnull=False).count(), 1)

    def test_archive_and_link_are_serialized(self):
        owner = User.objects.create_user('owner')
        asset = services.create_design_element(actor=owner, title='资产', kind='Asset')
        results = run_concurrently(
            lambda: services.update_design_element(actor=owner, element_id=asset.pk, expected_version=1, changes={'archived': True}),
            lambda: services.create_mission(actor=owner, title='任务', design_element_id=asset.pk),
        )
        self.assertEqual(results['a'], 'ok')
        if results['b'] != 'ok':
            self.assertIsInstance(results['b'], ConflictError)
            self.assertEqual(Mission.objects.count(), 0)
