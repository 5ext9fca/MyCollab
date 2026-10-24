"""模板校验、事务生成与生产任务继续使用原生命周期。"""
from unittest.mock import patch
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient
from accounts.models import User
from missions import services
from missions.exceptions import ConflictError, PermissionDenied, ValidationFailure
from missions.models import Mission, MissionDependency, ProductionBatch, ProductionBatchItem, ProductionTemplate
from .test_concurrency_features import run_concurrently
from . import utils


def sample_steps():
    return [
        {'key': 'concept', 'title': '原画'},
        {'key': 'model', 'title': '建模', 'prerequisite_keys': ['concept']},
        {'key': 'animation', 'title': '动画', 'prerequisite_keys': ['model']},
        {'key': 'audio', 'title': '音效', 'prerequisite_keys': ['model']},
        {'key': 'integration', 'title': '引擎接入', 'prerequisite_keys': ['animation', 'audio']},
        {'key': 'qa', 'title': '验收测试', 'prerequisite_keys': ['integration']},
    ]


class ProductionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner')
        self.other = User.objects.create_user('other')
        self.asset = services.create_design_element(actor=self.owner, title='森林守卫', kind='Asset')
        self.template = services.create_production_template(actor=self.other, name='角色', steps=sample_steps())
        self.client = APIClient(); self.client.force_authenticate(self.owner)

    def generate(self, **kwargs):
        params = dict(actor=self.owner, element_id=self.asset.pk, expected_version=self.asset.version, template_id=self.template.pk, template_version=self.template.version)
        params.update(kwargs)
        return services.instantiate_production(**params)

    def test_branch_generation_snapshot_and_claim_model(self):
        batch = self.generate()
        self.assertEqual(Mission.objects.count(), 6)
        self.assertEqual(MissionDependency.objects.count(), 6)
        self.assertEqual(ProductionBatchItem.objects.count(), 6)
        for mission in Mission.objects.all():
            self.assertEqual(mission.status, 'Open')
            self.assertIsNone(mission.assignee_id)
            self.assertIsNone(mission.parent_id)
            self.assertEqual(mission.creator_id, self.owner.pk)
            self.assertEqual(mission.reviewer_id, self.owner.pk)
            self.assertEqual(mission.design_element_id, self.asset.pk)
        self.assertEqual(batch.template_snapshot['steps'][4]['prerequisite_keys'], ['animation', 'audio'])
        services.update_production_template(actor=self.other, template_id=self.template.pk, expected_version=1, changes={'steps': [{'key': 'new', 'title': '新流程'}]})
        batch.refresh_from_db()
        self.assertEqual(len(batch.template_snapshot['steps']), 6)
        integration = batch.items.get(step_key='integration').mission
        integration = utils.claim(self.other, integration)
        with self.assertRaises(ConflictError):
            utils.submit(self.other, integration)
        with self.assertRaises(ConflictError) as caught:
            services.update_mission(actor=self.owner, mission_id=integration.pk, expected_version=integration.version, changes={'design_element_id': None})
        self.assertEqual(caught.exception.code, 'production_asset_locked')
        response = self.client.get(f'/api/design-elements/{self.asset.pk}/production/')
        self.assertEqual([i['step_key'] for i in response.data['items']], [s['key'] for s in sample_steps()])
        extra = services.create_mission(actor=self.owner, title='额外工作', design_element_id=self.asset.pk)
        response = self.client.get('/api/missions/', {'design_element': str(self.asset.pk), 'production_batch': 'none'})
        self.assertEqual([m['id'] for m in response.data['results']], [str(extra.pk)])

    def test_full_pipeline_manual_review_and_reopen(self):
        milestone = services.create_milestone(actor=self.owner, name='交付')
        milestone = services.transition_milestone(actor=self.owner, milestone_id=milestone.pk, expected_version=1, status='Active')
        batch = self.generate(milestone_id=milestone.pk)
        by_key = {item.step_key: item.mission for item in batch.items.all()}
        for step in sample_steps():
            mission = by_key[step['key']]
            utils.claim(self.other, mission)
            utils.submit(self.other, mission)
            utils.review(self.owner, mission)
        milestone.refresh_from_db()
        self.assertEqual(milestone.status, 'Active')
        detail = self.client.get(f'/api/design-elements/{self.asset.pk}/').data
        self.assertEqual(detail['progress']['progress'], 1)
        model = by_key['model']
        services.reopen_mission(actor=self.owner, mission_id=model.pk, expected_version=utils.version_of(model), reason='设计调整')
        self.assertTrue(services.derived_state(utils.fresh(by_key['animation']))['needs_dependency_review'])
        self.assertEqual(utils.fresh(by_key['animation']).status, 'Done')

    def test_cancelled_step_does_not_unblock_downstream(self):
        batch = self.generate()
        concept = batch.items.get(step_key='concept').mission
        model = batch.items.get(step_key='model').mission
        utils.cancel(self.owner, concept, reason='方案取消')
        self.assertTrue(services.derived_state(model)['is_blocked'])
        utils.claim(self.other, model)
        with self.assertRaises(ConflictError):
            utils.submit(self.other, model)

    def test_template_validation(self):
        invalid = [[], [{'key': f'k{i}', 'title': '步骤'} for i in range(31)],
            [{'key': 'a', 'title': '一', 'unknown': True}],
            [{'key': 'a', 'title': '一', 'prerequisite_keys': ['missing']}],
            [{'key': 'a', 'title': '一', 'prerequisite_keys': ['a']}],
            [{'key': 'a', 'title': '一'}, {'key': 'a', 'title': '二'}],
            [{'key': 'a', 'title': '一', 'prerequisite_keys': ['b', 'b']}, {'key': 'b', 'title': '二'}],
            [{'key': 'a', 'title': '一', 'prerequisite_keys': ['b']}, {'key': 'b', 'title': '二', 'prerequisite_keys': ['a']}],
            [{'key': 'a', 'title': ''}], [{'key': 'a', 'title': '一', 'type': 'Asset'}]]
        for content in ['![图](/api/library/files/123/)', '<img src="https://example.org/api/library/files/123/">', '[引用](data:text/plain,a)', '<img src="/media/a.png">']:
            invalid.append([{'key': 'a', 'title': '一', 'content': content}])
        for steps in invalid:
            with self.subTest(steps=steps), self.assertRaises(ValidationFailure):
                services.create_production_template(actor=self.owner, name='非法', steps=steps)
        self.assertEqual(ProductionTemplate.objects.count(), 1)
        steps = [{'key': 'a', 'title': '一', 'content': '[引用](https://example.org)\n`![示例](/media/code)`'}]
        services.create_production_template(actor=self.owner, name='允许代码示例', steps=steps)

    def test_failures_are_atomic_and_no_partial_batch(self):
        with self.assertRaises(ConflictError):
            self.generate(template_version=99)
        with self.assertRaises(PermissionDenied):
            self.generate(actor=self.other)
        self.assertEqual(Mission.objects.count(), 0)
        original = services.add_dependency
        calls = 0
        def fail_second(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValidationFailure('模拟中途失败')
            return original(**kwargs)
        with patch('missions.services.add_dependency', side_effect=fail_second), self.assertRaises(ValidationFailure):
            self.generate()
        self.assertEqual(Mission.objects.count(), 0)
        self.assertEqual(ProductionBatch.objects.count(), 0)
        self.assertEqual(MissionDependency.objects.count(), 0)
        self.asset.refresh_from_db(); self.assertEqual(self.asset.version, 1)
        self.generate()
        with self.assertRaises(ConflictError) as caught:
            self.generate()
        self.assertEqual(caught.exception.code, 'production_already_generated')

    def test_archived_and_closed_milestone_and_overlong_titles(self):
        milestone = services.create_milestone(actor=self.owner, name='里程碑')
        services.transition_milestone(actor=self.owner, milestone_id=milestone.pk, expected_version=1, status='Cancelled')
        with self.assertRaises(ConflictError):
            self.generate(milestone_id=milestone.pk)
        self.asset = services.update_design_element(actor=self.owner, element_id=self.asset.pk, expected_version=1, changes={'title': '长' * 200})
        with self.assertRaises(ValidationFailure):
            self.generate()
        self.template = services.update_production_template(actor=self.other, template_id=self.template.pk, expected_version=1, changes={'archived': True})
        with self.assertRaises(ConflictError):
            self.generate()
        self.assertEqual(ProductionBatch.objects.count(), 0)

    def test_api_contract_permission_and_preview_is_read_only(self):
        url = f'/api/design-elements/{self.asset.pk}/instantiate/'
        self.assertEqual(self.client.get(f'/api/design-elements/{self.asset.pk}/production/').data, {'batch': None, 'items': []})
        self.assertEqual(self.client.get('/api/production-templates/').status_code, 200)
        self.assertEqual(Mission.objects.count(), 0)
        self.assertEqual(self.client.patch(f'/api/production-templates/{self.template.pk}/', {'expected_version': 1, 'name': '越权'}, format='json').status_code, 403)
        self.assertEqual(self.client.post(url, {'template_id': str(self.template.pk)}, format='json').status_code, 400)
        response = self.client.post(url, {'template_id': str(self.template.pk), 'template_version': 1, 'expected_version': 1}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['asset_version'], 2)
        self.assertEqual(len(response.data['items']), 6)
        self.assertEqual(self.client.delete(f'/api/production-templates/{self.template.pk}/').status_code, 405)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/production-templates/').status_code, 403)


class ProductionConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner')
        self.asset = services.create_design_element(actor=self.owner, title='资产', kind='Asset')
        self.template = services.create_production_template(actor=self.owner, name='模板', steps=sample_steps())

    def generate(self):
        return services.instantiate_production(actor=self.owner, element_id=self.asset.pk, expected_version=1, template_id=self.template.pk, template_version=1)

    def test_duplicate_generation_creates_one_batch(self):
        results = run_concurrently(self.generate, self.generate)
        self.assertEqual(list(results.values()).count('ok'), 1, results)
        self.assertEqual(ProductionBatch.objects.count(), 1)
        self.assertEqual(Mission.objects.count(), 6)

    def test_archive_and_generation_use_same_lock(self):
        results = run_concurrently(self.generate, lambda: services.update_production_template(actor=self.owner, template_id=self.template.pk, expected_version=1, changes={'archived': True}))
        self.assertEqual(results['b'], 'ok', results)
        if results['a'] == 'ok':
            self.assertEqual(ProductionBatch.objects.get().template_version, 1)
        else:
            self.assertIsInstance(results['a'], ConflictError)
            self.assertEqual(ProductionBatch.objects.count(), 0)

    def test_milestone_completion_and_generation_are_serialized(self):
        milestone = services.create_milestone(actor=self.owner, name='交付')
        milestone = services.transition_milestone(actor=self.owner, milestone_id=milestone.pk, expected_version=1, status='Active')
        done = services.create_mission(actor=self.owner, title='已有成果', milestone_id=milestone.pk)
        utils.claim(self.owner, done); utils.submit(self.owner, done); utils.review(self.owner, done)
        results = run_concurrently(
            lambda: services.instantiate_production(actor=self.owner, element_id=self.asset.pk, expected_version=1, template_id=self.template.pk, template_version=1, milestone_id=milestone.pk),
            lambda: services.transition_milestone(actor=self.owner, milestone_id=milestone.pk, expected_version=milestone.version, status='Completed'),
        )
        self.assertEqual(list(results.values()).count('ok'), 1, results)
        milestone.refresh_from_db()
        if milestone.status == 'Completed':
            self.assertFalse(ProductionBatch.objects.exists())
        else:
            self.assertEqual(ProductionBatch.objects.count(), 1)
            self.assertEqual(milestone.missions.count(), 7)
