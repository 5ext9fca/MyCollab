from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import User
from missions import services
from notifications.models import Notification


class ListControlsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('列表成员')
        self.other = User.objects.create_user('其他成员')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_notification_order_filter_and_pagination_preserve_recipient_scope(self):
        mission = services.create_mission(actor=self.user, title='通知任务')
        for i in range(3):
            row = Notification.objects.create(recipient=self.user, mission=mission, kind='test', source_key=str(i), payload={})
            Notification.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(days=3-i))
        Notification.objects.create(recipient=self.other, mission=mission, kind='test', source_key='other')
        first = self.client.get('/api/notifications/', {'ordering': 'created_at', 'page_size': 1}).data
        last = self.client.get('/api/notifications/', {'ordering': '-created_at', 'page_size': 1}).data
        self.assertEqual(first['count'], 3)
        self.assertEqual(len(first['results']), 1)
        self.assertNotEqual(first['results'][0]['id'], last['results'][0]['id'])
        self.client.post('/api/notifications/read/', {'ids': [first['results'][0]['id']]}, format='json')
        self.assertEqual(self.client.get('/api/notifications/', {'read': 'unread'}).data['count'], 2)
        self.assertEqual(self.client.get('/api/notifications/', {'ordering': 'recipient'}).status_code, 400)

    def test_work_filters_sort_before_pagination_and_keep_personal_category(self):
        for title in ['匹配 B', '匹配 A', '不符合']:
            services.create_mission(actor=self.user, title=title, planned_end_date=timezone.localdate())
        services.create_mission(actor=self.other, title='匹配 0', planned_end_date=timezone.localdate())
        data = self.client.get('/api/my-work/missions/', {'category': 'due_soon', 'q': '匹配', 'ordering': 'title', 'page_size': 1}).data
        self.assertEqual(data['count'], 2)
        self.assertEqual(data['results'][0]['title'], '匹配 A')

    def test_milestone_sort_before_pagination(self):
        for name in ['B', 'A', 'C']:
            services.create_milestone(actor=self.user, name=name)
        data = self.client.get('/api/milestones/', {'status': 'Planned', 'ordering': 'name', 'page_size': 1, 'page': 2}).data
        self.assertEqual(data['count'], 3)
        self.assertEqual(data['results'][0]['name'], 'B')
        self.assertEqual(self.client.get('/api/milestones/', {'ordering': 'invalid'}).status_code, 400)
