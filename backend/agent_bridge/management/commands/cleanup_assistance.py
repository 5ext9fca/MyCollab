from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from agent_bridge.models import AssistanceRequest
from agent_bridge.services import expire_requests


class Command(BaseCommand):
    help = "清理超过 30 天的辅助输入与结果，并标记超时请求。"

    def handle(self, *args, **options):
        expire_requests(AssistanceRequest.objects.all())
        count, _ = AssistanceRequest.objects.filter(created_at__lt=timezone.now() - timedelta(days=30)).delete()
        self.stdout.write(f"已删除 {count} 条历史记录。")
