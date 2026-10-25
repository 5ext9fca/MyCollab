from datetime import date
from unittest.mock import patch
from django.test import TestCase
from rest_framework.test import APIClient
from accounts.models import User
from missions import services
from missions.models import SavedMissionView


class SavedViewTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user('a')
        self.b = User.objects.create_user('b')
        self.admin = User.objects.create_user('admin', is_staff=True)
        self.client = APIClient(); self.client.force_authenticate(self.a)
        self.definition = {'filters': {'assignee': 'me', 'tag': ['甲', '乙', '甲']}, 'ordering': '-priority', 'date_window': {'mode': 'relative', 'preset': 'this_week'}, 'zoom': None}

    def create(self, **extra):
        return self.client.post('/api/saved-views/', {'name': '我的视图', 'target': 'List', 'definition': self.definition, **extra}, format='json')

    def test_private_admin_isolation_team_permissions_version_and_owner(self):
        row = self.create().data
        url = f"/api/saved-views/{row['id']}/"
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_authenticate(self.a)
        self.assertEqual(self.client.patch(url, {'visibility': 'Team', 'expected_version': 1}, format='json').status_code, 200)
        self.client.force_authenticate(self.b)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.patch(url, {'name': '更名', 'expected_version': 2}, format='json').status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(url, {'name': '更名', 'expected_version': 1}, format='json').status_code, 409)
        self.assertEqual(self.client.patch(url, {'owner': self.admin.pk, 'expected_version': 2}, format='json').status_code, 400)
        self.assertEqual(self.client.delete(url + '?expected_version=2').status_code, 204)

    @patch('django.utils.timezone.localdate', return_value=date(2026, 10, 25))
    def test_relative_me_and_tags(self, _):
        row = self.create(visibility='Team').data
        self.assertEqual(row['definition']['filters']['tag'], ['甲', '乙'])
        self.client.force_authenticate(self.b)
        url = f"/api/saved-views/{row['id']}/resolve/"
        query = self.client.get(url).data['query']
        self.assertEqual(query['assignee'], self.b.pk)
        self.assertEqual(query['date_from'], '2026-10-19'); self.assertEqual(query['date_to'], '2026-10-25')
        with patch('django.utils.timezone.localdate', return_value=date(2026, 10, 26)):
            self.assertEqual(self.client.get(url).data['query']['date_from'], '2026-10-26')
        m = services.create_mission(actor=self.a, title='匹配', tags=['甲', '乙'])
        services.create_mission(actor=self.a, title='不匹配', tags=['甲'])
        from missions.tests import utils
        utils.claim(self.b, m)
        self.assertEqual(self.client.get('/api/missions/', query).data['count'], 1)

    def test_invalid_definitions_and_name_uniqueness(self):
        for filters in [{'unknown': 1}, {'assignee': str(self.a.pk)}, {'blocked': 'false'}, {'status': 'fake'}, {'tag': ['']}, {'parent': 'none'}, {'q': {'sql': 'all'}}]:
            with self.subTest(filters=filters):
                self.definition['filters'] = filters
                self.assertEqual(self.create().status_code, 400)
        self.definition['filters'] = {'creator': self.a.pk}
        self.assertEqual(self.create().status_code, 201)
        self.assertEqual(self.create().status_code, 400)
        self.assertEqual(self.create(name=' ').status_code, 400)
        self.assertEqual(self.client.post('/api/saved-views/', ['bad'], format='json').status_code, 400)

    def test_missing_reference_warns_and_resolve_does_not_broaden(self):
        milestone = services.create_milestone(actor=self.a, name='发布')
        self.definition['filters'] = {'milestone': str(milestone.pk)}
        row = self.create().data
        milestone.delete()
        url = f"/api/saved-views/{row['id']}/"
        self.assertTrue(self.client.get(url).data['warnings'])
        self.assertEqual(self.client.get(url + 'resolve/').status_code, 400)
        self.assertEqual(SavedMissionView.objects.get(pk=row['id']).definition['filters']['milestone'], str(milestone.pk) if milestone.pk else row['definition']['filters']['milestone'])

    def test_integer_role_filter_regression(self):
        services.create_mission(actor=self.a, title='我的')
        services.create_mission(actor=self.b, title='别人的')
        self.assertEqual(self.client.get('/api/missions/', {'creator': self.a.pk}).data['count'], 1)
        self.assertEqual(self.client.get('/api/missions/', {'creator': 'not-a-user'}).status_code, 400)

    def test_strict_window_and_zoom(self):
        for window in [{'mode': 'absolute', 'date_from': '20261025', 'date_to': '2026-10-26'}, {'mode': 'relative', 'preset': 'yesterday'}, {'mode': 'absolute', 'date_from': '2025-01-01', 'date_to': '2026-10-25'}]:
            self.definition['date_window'] = window
            self.assertEqual(self.create().status_code, 400)
        self.definition['date_window'] = None; self.definition['zoom'] = 'week'
        self.assertEqual(self.create().status_code, 400)
        self.assertEqual(self.create(target='Gantt').status_code, 201)
