"""测试专用模型 CLI；只响应版本和固定 JSON，不接入供应商。"""
import json
import os
from pathlib import Path
import signal
import sys
import time

if '--version' in sys.argv:
    print('opencode v2.1.3')
    raise SystemExit(0)
settings = json.loads(Path(sys.argv[sys.argv.index('--model') + 1]).read_text(encoding='utf-8'))
sys.stdin.read()
if settings['mode'] == 'complete':
    counter = Path(settings['counter'])
    counter.write_text(counter.read_text() + '1' if counter.exists() else '1')
    result = {'title': '候选', 'content': '', 'summary': '', 'questions': []}
    print(json.dumps({'type': 'text', 'part': {'text': json.dumps(result)}}))
else:
    Path(settings['started']).write_text(str(os.getpid()))

    def stop(*_args):
        Path(settings['stopped']).touch()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    while True:
        time.sleep(0.05)
