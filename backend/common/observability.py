"""有界、无业务正文的性能记录；默认关闭，可用于生产采样或本地基准。"""
from contextlib import ExitStack
from contextvars import ContextVar
import json
import logging
import random
import time
from uuid import uuid4

from django.conf import settings
from django.db import connections

logger = logging.getLogger("mycollab.performance")
current = ContextVar("performance_measurement", default=None)


def add_lock_wait(seconds):
    measurement = current.get()
    if measurement is not None:
        measurement["team_lock_ms"] += seconds * 1000


class PerformanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rate = settings.PERFORMANCE_SAMPLE_RATE
        if not request.path.startswith("/api/") or rate <= 0 or random.random() >= rate:
            return self.get_response(request)
        measurement = {"event": "api_request", "request_id": uuid4().hex,
                       "sql_count": 0, "sql_ms": 0.0, "team_lock_ms": 0.0}
        token = current.set(measurement)
        started = time.perf_counter()
        status = 500

        def measure(execute, sql, params, many, context):
            begin = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                measurement["sql_count"] += 1
                measurement["sql_ms"] += (time.perf_counter() - begin) * 1000

        try:
            with ExitStack() as stack:
                for connection in connections.all():
                    stack.enter_context(connection.execute_wrapper(measure))
                response = self.get_response(request)
                status = response.status_code
                response["X-Request-ID"] = measurement["request_id"]
                return response
        finally:
            current.reset(token)
            match = getattr(request, "resolver_match", None)
            # 只记录路由模板，不记录查询参数、对象 ID、用户或 SQL 文本。
            measurement.update(route=getattr(match, "route", None) or "unresolved",
                               method=request.method, status=status,
                               duration_ms=round((time.perf_counter() - started) * 1000, 3))
            for key in ("sql_ms", "team_lock_ms"):
                measurement[key] = round(measurement[key], 3)
            logger.info(json.dumps(measurement, ensure_ascii=False))
