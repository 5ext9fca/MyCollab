"""只运行用户本地配置的 argv，日志留在本地，不让模型选择命令。"""
import os
import queue
import subprocess
import threading
import time

from .opencode import Cancelled, terminate

LOG_LIMIT = 1024 * 1024


def run_checks(checks, directory, logs, *, heartbeat=lambda: True, budget=480):
    deadline, last_heartbeat = time.monotonic() + budget, time.monotonic()
    results = []
    # 不继承设备/供应商令牌环境；本机工具链与用户配置的命令仍有本机权限。
    env = {key: value for key, value in os.environ.items() if key in ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT')}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    logs.mkdir(mode=0o700, exist_ok=True)
    for check in checks:
        result = {'id': check['id'], 'label': check['label'], 'status': 'not_run', 'exit_code': None, 'duration_ms': 0}
        results.append(result)
        if time.monotonic() >= deadline:
            continue
        if not heartbeat():
            raise Cancelled()
        started = time.monotonic()
        log_path = logs / (check['id'] + '.log')
        try:
            process = subprocess.Popen(check['argv'], cwd=directory, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=os.name == 'posix')
        except OSError:
            continue
        events = queue.Queue(maxsize=64)
        def reader():
            try:
                while block := process.stdout.read(16384):
                    events.put(block, timeout=2)
            except (OSError, queue.Full):
                pass
            finally:
                try:
                    events.put(None, timeout=2)
                except queue.Full:
                    pass
        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        written = 0
        try:
            with log_path.open('wb') as log:
                log_path.chmod(0o600)
                while True:
                    now = time.monotonic()
                    if now >= deadline or now - started >= check.get('timeout', 120):
                        result['status'] = 'timeout'
                        break
                    if now - last_heartbeat >= 30:
                        if not heartbeat():
                            raise Cancelled()
                        last_heartbeat = now
                    try:
                        block = events.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    if block is None:
                        code = process.wait(timeout=5)
                        result.update(status='passed' if code == 0 else 'failed', exit_code=code)
                        break
                    if written < LOG_LIMIT:
                        remaining = block[:LOG_LIMIT - written]
                        log.write(remaining)
                        written += len(remaining)
        finally:
            terminate(process)
            process.stdout.close()
            thread.join(timeout=3)
            result['duration_ms'] = int((time.monotonic() - started) * 1000)
    return results
