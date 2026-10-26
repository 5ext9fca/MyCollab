"""设计/资产各自维护组成树和无环依赖，跨类型只保留设计引用资产。"""
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from accounts.models import User
from missions import services
from missions.exceptions import ConflictError, PermissionDenied, ValidationFailure
from missions.models import DesignElementDependency, MissionDependency
from .test_concurrency_features import run_concurrently


class DesignDependencyTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner')
        self.other = User.objects.create_user('other')
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def create(self, title, kind='Design', **kwargs):
        return services.create_design_element(actor=self.owner, title=title, kind=kind, **kwargs)

    def update(self, element, **changes):
        result = services.update_design_element(actor=self.owner, element_id=element.pk, expected_version=element.version, changes=changes)
        element.refresh_from_db()
        return result

    def test_each_kind_has_independent_tree_and_dependency_graph(self):
        for kind in ['Design', 'Asset']:
            with self.subTest(kind=kind):
                root = self.create('根', kind)
                a = self.create('前置', kind, parent=root.pk)
                b = self.create('后置', kind, parent=root.pk, prerequisite_ids=[a.pk])
                data = self.client.get(f'/api/design-elements/{b.pk}/').data
                self.assertEqual(data['parent']['id'], str(root.pk))
                self.assertEqual([p['id'] for p in data['prerequisites']], [str(a.pk)])
                self.assertEqual(self.client.get(f'/api/design-elements/{a.pk}/').data['dependents'][0]['id'], str(b.pk))
                # 组成树和依赖不互相推导，也不会生成 Mission 依赖。
                self.assertFalse(root.prerequisites.exists())
                self.assertFalse(MissionDependency.objects.exists())
                self.update(b, parent=None)
                self.assertEqual(list(b.prerequisites.all()), [a])
                self.assertEqual(self.client.get('/api/design-elements/', {'kind': kind, 'parent': str(root.pk)}).data['count'], 1)
                response = self.client.patch(f'/api/design-elements/{b.pk}/', {'expected_version': b.version, 'prerequisite_ids': []}, format='json')
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data['prerequisites'], [])
                self.assertTrue(b.events.filter(action='dependencies_changed').exists())

    def test_cross_kind_relations_are_only_design_to_asset_references(self):
        asset = self.create('模型', 'Asset')
        design = self.create('角色', asset_ids=[asset.pk])
        for source, target in [(design, asset), (asset, design)]:
            with self.assertRaises(ValidationFailure):
                self.update(source, prerequisite_ids=[target.pk])
            with self.assertRaises(ValidationFailure):
                self.update(source, parent=target.pk)
        with self.assertRaises(ValidationFailure):
            self.update(asset, asset_ids=[design.pk])
        response = self.client.patch(f'/api/design-elements/{asset.pk}/', {'expected_version': 1, 'referencing_designs': [str(design.pk)]}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(design.assets.all()), [asset])
        self.assertFalse(asset.assets.exists())
        self.assertFalse(DesignElementDependency.objects.exists())

    def test_self_and_indirect_cycles_reject_and_roll_back_all_changes(self):
        for kind in ['Design', 'Asset']:
            a = self.create('甲', kind)
            b = self.create('乙', kind, prerequisite_ids=[a.pk])
            c = self.create('丙', kind, prerequisite_ids=[b.pk])
            for target in [a, c]:
                with self.assertRaises(ConflictError) as caught:
                    self.update(a, title='不应保存', prerequisite_ids=[target.pk])
                self.assertEqual(caught.exception.code, 'design_dependency_cycle')
            a.refresh_from_db()
            self.assertEqual(a.title, '甲')
            self.assertEqual(a.version, 1)
            self.assertFalse(a.prerequisites.exists())
            self.assertEqual(a.events.count(), 1)

    def test_permissions_version_archive_and_invalid_ids(self):
        a = self.create('前置')
        b = self.create('后置', prerequisite_ids=[a.pk])
        with self.assertRaises(PermissionDenied):
            services.update_design_element(actor=self.other, element_id=b.pk, expected_version=1, changes={'prerequisite_ids': []})
        with self.assertRaises(ConflictError):
            services.update_design_element(actor=self.owner, element_id=b.pk, expected_version=99, changes={'prerequisite_ids': []})
        for value in [['invalid'], ['00000000-0000-0000-0000-000000000000'], None]:
            with self.assertRaises(ValidationFailure):
                self.update(b, prerequisite_ids=value)
        self.update(a, archived=True)
        self.update(b, prerequisite_ids=[a.pk])
        self.assertTrue(b.prerequisites.get().archived)
        with self.assertRaises(ConflictError):
            self.create('新后置', prerequisite_ids=[a.pk])
        self.update(b, prerequisite_ids=[])
        with self.assertRaises(ConflictError):
            self.update(b, prerequisite_ids=[a.pk])
        self.update(b, archived=True)
        with self.assertRaises(ConflictError):
            self.update(b, prerequisite_ids=[])

    def test_database_rejects_self_and_duplicate_edges(self):
        a = self.create('甲')
        b = self.create('乙', prerequisite_ids=[a.pk])
        for source, target in [(a, a), (b, a)]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                DesignElementDependency.objects.create(element=source, prerequisite=target)


class DesignDependencyConcurrencyTests(TransactionTestCase):
    def test_opposite_dependencies_cannot_create_cycle(self):
        owner = User.objects.create_user('owner')
        for kind in ['Design', 'Asset']:
            a = services.create_design_element(actor=owner, title='甲', kind=kind)
            b = services.create_design_element(actor=owner, title='乙', kind=kind)
            results = run_concurrently(
                lambda: services.update_design_element(actor=owner, element_id=a.pk, expected_version=1, changes={'prerequisite_ids': [b.pk]}),
                lambda: services.update_design_element(actor=owner, element_id=b.pk, expected_version=1, changes={'prerequisite_ids': [a.pk]}),
            )
            self.assertEqual(list(results.values()).count('ok'), 1, results)
            error = next(value for value in results.values() if value != 'ok')
            self.assertEqual(error.code, 'design_dependency_cycle')
