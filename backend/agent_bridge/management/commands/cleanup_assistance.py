from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from agent_bridge.models import AssistanceRequest
from agent_bridge.services import expire_requests


class Command(BaseCommand):
    help = "清理超过 30 天的辅助输入与结果，并标记超时请求。"

    def handle(self, *args, **options):
        expire_requests(AssistanceRequest.objects.all())
        old = AssistanceRequest.objects.filter(created_at__lt=timezone.now() - timedelta(days=30))
        # 委派成果及提交关联长期保留，只清除到期的原始输入/结果快照。
        old.filter(execution__isnull=False).exclude(status__in=("queued", "running", "awaiting_selection")).update(input={}, result=None)
        count, _ = old.filter(execution__isnull=True).delete()
        self.stdout.write(f"已删除 {count} 条历史记录。")
