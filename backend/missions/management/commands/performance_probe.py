"""在指定用户权限下测量只读 API；不执行模型或修改业务数据。"""
import json
import math
from statistics import median
import time
from contextlib import ExitStack

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.test import Client, override_settings


class Command(BaseCommand):
    help = "测量任务列表、详情与工作台的本进程服务端耗时及 SQL（不含公网延迟）"

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--iterations", type=int, default=10)
        parser.add_argument("--mission-id")

    def handle(self, *args, **options):
        count = options["iterations"]
        if not 1 <= count <= 100:
            raise CommandError("iterations 必须在 1–100 之间。")
        user = get_user_model().objects.filter(username=options["username"], is_active=True).first()
        if user is None:
            raise CommandError("用户不存在或已停用。")
        from missions.models import Mission
        mission = options["mission_id"] or Mission.objects.order_by("id").values_list("id", flat=True).first()
        paths = ["/api/missions/", "/api/workspace/overview/", "/api/workspace/graph/"]
        if mission:
            from uuid import UUID
            try:
                mission = UUID(str(mission))
            except ValueError as exc:
                raise CommandError("mission-id 必须为 UUID。") from exc
            paths.append(f"/api/missions/{mission}/")
        client = Client()
        report = {"scope": "本进程 GET；不含浏览器渲染、网络和模型；含一次预热", "iterations": count, "endpoints": []}
        # 临时 Cookie 会话写入与清理不计入业务测量。
        with override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False, PERFORMANCE_SAMPLE_RATE=0):
            client.force_login(user)
            try:
                for path in paths:
                    durations, counts, sql_durations = [], [], []
                    for index in range(count + 1):
                        stats = [0, 0.0]
                        def measure(execute, sql, params, many, context):
                            begin = time.perf_counter()
                            try:
                                return execute(sql, params, many, context)
                            finally:
                                stats[0] += 1
                                stats[1] += (time.perf_counter() - begin) * 1000
                        with ExitStack() as stack:
                            for connection in connections.all():
                                stack.enter_context(connection.execute_wrapper(measure))
                            begin = time.perf_counter()
                            response = client.get(path)
                            elapsed = (time.perf_counter() - begin) * 1000
                        if response.status_code != 200:
                            raise CommandError(f"只读测量请求失败：HTTP {response.status_code}")
                        if index:
                            durations.append(elapsed); counts.append(stats[0]); sql_durations.append(stats[1])
                    report["endpoints"].append({"route": response.resolver_match.route,
                        "p50_ms": round(median(durations), 3), "p95_ms": round(sorted(durations)[math.ceil(count * .95) - 1], 3),
                        "sql_count_max": max(counts), "sql_ms_p50": round(median(sql_durations), 3)})
            finally:
                client.logout()
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
