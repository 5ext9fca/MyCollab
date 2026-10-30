"""读取指定时间窗内的 Agent 交接指标，不读取或输出输入与结果。"""
from datetime import timedelta
import json
import math
from statistics import median

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.utils import timezone
from agent_bridge.models import AssistanceRequest


def distribution(values):
    if not values:
        return {"samples": 0, "p50_ms": None, "p95_ms": None}
    values.sort()
    return {"samples": len(values), "p50_ms": round(median(values), 3),
            "p95_ms": round(values[math.ceil(len(values) * .95) - 1], 3)}


class Command(BaseCommand):
    help = "输出最近 N 小时的状态分布、排队和完成耗时（不触发过期清理）"

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, *args, **options):
        if not 1 <= options["hours"] <= 720:
            raise CommandError("hours 必须在 1–720 之间。")
        end = timezone.now()
        start = end - timedelta(hours=options["hours"])
        qs = AssistanceRequest.objects.filter(created_at__gte=start, created_at__lte=end)
        counts = dict(qs.order_by().values_list("status").annotate(count=Count("id")))
        queued, execution = [], []
        # 使用明确时间戳；旧数据缺少领取时间时不伪造样本。
        for created, claimed, stopped, status in qs.values_list("created_at", "claimed_at", "stopped_at", "status").iterator():
            if claimed:
                queued.append((claimed - created).total_seconds() * 1000)
                if stopped and status in ("succeeded", "failed"):
                    execution.append((stopped - claimed).total_seconds() * 1000)
        self.stdout.write(json.dumps({"from": start.isoformat(), "to": end.isoformat(), "statuses": counts,
            "queue_wait": distribution(queued), "execution_and_delivery": distribution(execution),
            "overdue_active": qs.filter(status__in=("queued", "running"), expires_at__lte=end).count(),
            "note": "状态为数据库快照；执行耗时包含模型及回传。旧记录缺少 claimed_at 时不计耗时。"}, ensure_ascii=False, indent=2))
