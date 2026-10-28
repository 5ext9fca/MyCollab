import io
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from accounts.models import User
from common.observability import PerformanceMiddleware, add_lock_wait, current
from missions import services


class PerformanceTests(TestCase):
    @override_settings(PERFORMANCE_SAMPLE_RATE=1)
    def test_request_counts_sql_and_lock_without_logging_secrets(self):
        request = RequestFactory().get('/api/missions/private-id/?secret=hidden', HTTP_AUTHORIZATION='Bearer private')
        request.resolver_match = SimpleNamespace(route='api/missions/<uuid:pk>/')
        def view(request):
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            add_lock_wait(.025)
            return HttpResponse('private body')
        with patch('common.observability.logger.info') as log:
            response = PerformanceMiddleware(view)(request)
        data = json.loads(log.call_args.args[0])
        self.assertEqual(data['sql_count'], 1)
        self.assertEqual(data['team_lock_ms'], 25)
        self.assertEqual(data['route'], 'api/missions/<uuid:pk>/')
        self.assertEqual(response['X-Request-ID'], data['request_id'])
        self.assertNotIn('private', log.call_args.args[0])
        self.assertNotIn('hidden', log.call_args.args[0])
        self.assertIsNone(current.get())

    @override_settings(PERFORMANCE_SAMPLE_RATE=0)
    def test_disabled_has_no_logging(self):
        with patch('common.observability.logger.info') as log:
            PerformanceMiddleware(lambda r: HttpResponse())(RequestFactory().get('/api/missions/'))
        log.assert_not_called()

    @override_settings(PERFORMANCE_SAMPLE_RATE=1)
    def test_exception_restores_context(self):
        with patch('common.observability.logger.info') as log:
            def fail(request):
                raise RuntimeError('secret')
            with self.assertRaises(RuntimeError):
                PerformanceMiddleware(fail)(RequestFactory().get('/api/missions/'))
        self.assertEqual(json.loads(log.call_args.args[0])['status'], 500)
        self.assertIsNone(current.get())

    def test_readonly_probe_covers_real_endpoints(self):
        user = User.objects.create_user('probe')
        mission = services.create_mission(actor=user, title='探针任务')
        before = (mission.version, mission.events.count())
        out = io.StringIO()
        call_command('performance_probe', username='probe', iterations=2, stdout=out)
        report = json.loads(out.getvalue())
        self.assertEqual(len(report['endpoints']), 4)
        self.assertTrue(all(row['sql_count_max'] > 0 for row in report['endpoints']))
        mission.refresh_from_db()
        self.assertEqual((mission.version, mission.events.count()), before)
