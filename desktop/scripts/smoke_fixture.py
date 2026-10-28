"""桌面人工验收用隔离服务器和假模型，不连接业务数据库或供应商。"""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1] / 'build/smoke'
root.mkdir(parents=True, exist_ok=True)
cli = root / 'opencode'
cli.write_text(f'''#!{sys.executable}
import json, sys, time
if '--version' in sys.argv:
    print('opencode v2.1.3')
else:
    sys.stdin.read()
    time.sleep(1)
    print(json.dumps({{'type':'text','part':{{'text':json.dumps({{'title':'桌面验收','content':'','summary':'','questions':[]}})}}}}))
''')
cli.chmod(0o700)
claimed = False
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        global claimed
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        response = None
        if self.path.endswith('/status/'):
            response = {'schema_versions':[1],'capabilities':['design_polish']}
        elif self.path.endswith('/claim/') and not claimed:
            claimed = True
            response = {'id':'smoke-request','attempt_id':'smoke-attempt','schema_version':1,'kind':'design_polish','input':{},
                        'lease_expires_at':(datetime.now(timezone.utc)+timedelta(seconds=180)).isoformat()}
        elif self.path.endswith('/result/'):
            (root/'result.json').write_text(json.dumps(data,ensure_ascii=False))
            response = {'status':'succeeded'}
            print('已收到桌面假模型结果', flush=True)
        self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
        self.wfile.write(json.dumps(response).encode())
server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
config = root/'config.json'
config.write_text(json.dumps({'server':f'http://127.0.0.1:{server.server_port}', 'device_token':'mc_agent_smoke_only', 'model':'test/model', 'opencode':str(cli), 'ca_file':''}))
config.chmod(0o600)
print(f'隔离配置：{config}', flush=True)
try: server.serve_forever()
except KeyboardInterrupt: pass
finally: server.server_close()
