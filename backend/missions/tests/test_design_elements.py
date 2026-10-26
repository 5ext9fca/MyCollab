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
        self.asset = services.create_design_element(actor=self.owner, title='森林守卫', kind='Asset')

    def update(self, element, **changes):
        result = services.update_design_element(actor=self.owner, element_id=element.id, expected_version=element.version, changes=changes)
        element.refresh_from_db()
        return result

    def test_tree_cycle_archive_restore_and_versions(self):
        child = services.create_design_element(actor=self.owner, title='子设计', parent=self.root.pk)
        with self.assertRaises(ConflictError):
            self.update(self.root, parent=child.pk)
        with self.assertRaises(ConflictError):
            self.update(self.root, archived=True)
        self.update(child, archived=True)
        self.update(self.root, archived=True)
        with self.assertRaises(ConflictError):
            self.update(child, archived=False)
        with self.assertRaises(ConflictError):
            self.update(self.root, title='归档内容')
        self.update(self.root, archived=False)
        self.update(child, archived=False)
        with self.assertRaises(ConflictError):
            services.update_design_element(actor=self.owner, element_id=child.pk, expected_version=1, changes={'title': '过期'})
        self.assertTrue(child.events.filter(action='restored').exists())

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
        mission = services.create_mission(actor=self.owner, title='建模', design_element_id=self.root.pk, asset_ids=[self.asset.pk])
        child = services.create_mission(actor=self.owner, title='子任务', parent_id=mission.pk)
        self.assertIsNone(child.design_element_id)
        self.update(self.asset, archived=True)
        self.update(self.root, archived=True)
        mission = services.update_mission(actor=self.owner, mission_id=mission.pk, expected_version=mission.version, changes={'title': '修改标题'})
        self.assertEqual(mission.design_element_id, self.root.pk)
        with self.assertRaises(ConflictError):
            services.create_mission(actor=self.owner, title='新任务', design_element_id=self.root.pk, asset_ids=[self.asset.pk])
        self.assertTrue(self.client.get(f'/api/missions/{mission.pk}/').data['design_element']['archived'])
        mission = services.update_mission(actor=self.owner, mission_id=mission.pk, expected_version=mission.version, changes={'design_element_id': None})
        self.assertIsNone(mission.design_element_id)
        services.cancel_mission(actor=self.owner, mission_id=mission.pk, expected_version=mission.version)
        mission.refresh_from_db()
        with self.assertRaises(ConflictError):
            services.update_mission(actor=self.owner, mission_id=mission.pk, expected_version=mission.version, changes={'design_element_id': self.root.pk})

    def test_api_filter_progress_and_ancestor_path(self):
        response = self.client.post('/api/missions/', {'title': '原画', 'design_element_id': str(self.root.pk), 'asset_ids': [str(self.asset.pk)]}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        first = response.data['id']
        old = services.create_mission(actor=self.owner, title='旧任务')
        detail = self.client.get(f'/api/design-elements/{self.asset.pk}/').data
        self.assertEqual(detail['ancestors'], [])
        self.assertEqual(detail['progress']['effective_total'], 1)
        self.assertEqual(self.client.get(f'/api/design-elements/{self.root.pk}/').data['progress']['effective_total'], 1)
        for endpoint in ['/api/missions/', '/api/workspace/graph/']:
            response = self.client.get(endpoint, {'design_element': str(self.asset.pk), 'context': 'false'})
            self.assertEqual(response.status_code, 200)
            rows = response.data.get('results', response.data.get('nodes'))
            self.assertEqual([str(row['id']) for row in rows], [first])
        response = self.client.get('/api/missions/', {'design_element': 'none'})
        self.assertEqual(response.data['results'][0]['id'], str(old.pk))
        self.assertEqual(self.client.get('/api/workspace/overview/', {'design_element': str(self.asset.pk)}).status_code, 200)
        self.assertEqual(self.client.get('/api/design-elements/', {'parent': str(self.root.pk)}).data['count'], 0)
        self.assertEqual(self.client.patch(f'/api/design-elements/{self.root.pk}/', {'title': '缺版本'}, format='json').status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/design-elements/').status_code, 403)

    def test_existing_cross_kind_links_convert_to_independent_references(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        from types import SimpleNamespace
        DesignElement.objects.filter(pk=self.asset.pk).update(parent=self.root)
        mission = Mission.objects.create(title='旧资产任务', creator=self.owner, design_element=self.asset)
        migrate = import_module('missions.migrations.0009_designelement_assets_mission_assets_and_more').separate_references
        migrate(apps, SimpleNamespace(connection=connection))
        self.asset.refresh_from_db(); mission.refresh_from_db()
        self.assertIsNone(self.asset.parent_id)
        self.assertIsNone(mission.design_element_id)
        self.assertEqual(list(self.root.assets.all()), [self.asset])
        self.assertEqual(list(mission.assets.all()), [self.asset])

    def test_designs_share_assets_and_reverse_references(self):
        other_design = services.create_design_element(actor=self.owner, title='另一设计', asset_ids=[self.asset.pk])
        second = services.create_design_element(actor=self.owner, title='音效', kind='Asset')
        response = self.client.patch(f'/api/design-elements/{self.root.pk}/', {
            'expected_version': 1, 'asset_ids': [str(self.asset.pk), str(second.pk)]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual({a['id'] for a in response.data['assets']}, {str(self.asset.pk), str(second.pk)})
        detail = self.client.get(f'/api/design-elements/{self.asset.pk}/').data
        self.assertEqual({d['id'] for d in detail['referencing_designs']}, {str(self.root.pk), str(other_design.pk)})
        self.assertIsNone(detail['parent'])
        self.root.refresh_from_db()
        self.update(self.asset, archived=True)
        self.update(self.root, asset_ids=[self.asset.pk])
        with self.assertRaises(ConflictError):
            services.create_design_element(actor=self.owner, title='新设计', asset_ids=[self.asset.pk])
        self.update(self.root, asset_ids=[])
        self.assertFalse(self.root.assets.exists())

    def test_invalid_reference_types_and_cross_kind_parents_roll_back(self):
        for kind, parent in [('Design', self.asset), ('Asset', self.root)]:
            with self.assertRaises(ValidationFailure):
                services.create_design_element(actor=self.owner, title='非法父级', kind=kind, parent=parent.pk)
        with self.assertRaises(ValidationFailure):
            self.update(self.asset, parent=self.root.pk)
        with self.assertRaises(ValidationFailure):
            self.update(self.asset, asset_ids=[self.asset.pk])
        for fields in [{'design_element_id': self.asset.pk}, {'asset_ids': [self.root.pk]}, {'asset_ids': ['invalid']}]:
            with self.assertRaises(ValidationFailure):
                services.create_mission(actor=self.owner, title='非法关联', **fields)
        self.assertFalse(Mission.objects.exists())
        self.assertEqual(self.asset.version, 1)

    def test_task_assets_permissions_freeze_versions_and_audit(self):
        response = self.client.post('/api/missions/', {'title': '集成', 'design_element_id': str(self.root.pk),
            'asset_ids': [str(self.asset.pk)]}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        mission = Mission.objects.get(pk=response.data['id'])
        self.assertEqual(response.data['assets'][0]['id'], str(self.asset.pk))
        with self.assertRaises(PermissionDenied):
            services.update_mission(actor=self.other, mission_id=mission.pk, expected_version=1, changes={'asset_ids': []})
        with self.assertRaises(ConflictError):
            services.update_mission(actor=self.owner, mission_id=mission.pk, expected_version=99, changes={'asset_ids': []})
        self.update(self.asset, archived=True)
        mission = services.update_mission(actor=self.owner, mission_id=mission.pk, expected_version=1, changes={'asset_ids': [self.asset.pk], 'title': '保留归档引用'})
        self.assertTrue(mission.assets.exists())
        mission = services.update_mission(actor=self.owner, mission_id=mission.pk, expected_version=mission.version, changes={'asset_ids': []})
        self.assertTrue(mission.events.filter(action='assets_changed').exists())
        self.assertEqual(mission.design_element_id, self.root.pk)
        with self.assertRaises(ConflictError):
            services.update_mission(actor=self.owner, mission_id=mission.pk, expected_version=mission.version, changes={'asset_ids': [self.asset.pk]})
        services.claim_mission(actor=self.owner, mission_id=mission.pk, expected_version=mission.version)
        mission.refresh_from_db()
        from . import utils
        utils.submit(self.owner, mission)
        mission.refresh_from_db()
        with self.assertRaises(ConflictError):
            services.update_mission(actor=self.owner, mission_id=mission.pk, expected_version=mission.version, changes={'asset_ids': []})



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
            lambda: services.create_mission(actor=owner, title='任务', asset_ids=[asset.pk]),
        )
        self.assertEqual(results['a'], 'ok')
        if results['b'] != 'ok':
            self.assertIsInstance(results['b'], ConflictError)
            self.assertEqual(Mission.objects.count(), 0)
