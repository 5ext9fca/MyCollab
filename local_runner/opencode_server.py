"""仅本机可达的 OpenCode V2 私有服务；随机认证不传给 MyCollab。"""
import base64
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import threading
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from .opencode import LocalFailure, terminate


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PrivateServer:
    def __init__(self, directory, configuration, executable='opencode'):
        self.directory = Path(directory).resolve()
        self.configuration = configuration
        self.executable = executable
        self.process = None
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def __enter__(self):
        version = subprocess.run([self.executable, '--version'], capture_output=True, text=True, timeout=15)
        if version.returncode or version.stdout.strip() != 'opencode v2.1.3':
            raise LocalFailure('local_configuration')
        password = secrets.token_urlsafe(32)
        self.authorization = 'Basic ' + base64.b64encode(('opencode:' + password).encode()).decode()
        config_path = self.directory.parent / 'interactive-agent-config.json'
        config_path.write_text(json.dumps(self.configuration), encoding='utf-8')
        config_path.chmod(0o600)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('MYCOLLAB_', 'OPENCODE_'))}
        env.pop('OLDPWD', None); env.pop('INIT_CWD', None)
        env.update(PWD=str(self.directory), OPENCODE_CONFIG=str(config_path),
            OPENCODE_CONFIG_CONTENT=json.dumps(self.configuration), OPENCODE_SERVER_PASSWORD=password)
        self.process = subprocess.Popen([self.executable, 'serve', '--stdio', '--hostname', '127.0.0.1', '--port', '0'],
            cwd=self.directory, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=os.name == 'posix')
        handshake = queue.Queue(maxsize=1)
        def read():
            try:
                handshake.put(self.process.stdout.readline(8193), timeout=1)
            except (OSError, queue.Full):
                pass
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()
        try:
            raw = handshake.get(timeout=15)
            if len(raw) > 8192:
                raise ValueError()
            self.url = json.loads(raw)['url']
            parsed = urlsplit(self.url)
            if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
                raise ValueError()
            if self.call('GET', '/api/info')['version'] not in ('2.1.3', 'v2.1.3'):
                raise ValueError()
            return self
        except Exception as exc:
            self.__exit__(None, None, None)
            raise LocalFailure('local_configuration') from exc

    def call(self, method, path, payload=None):
        if not path.startswith('/api/') or '://' in path or '\n' in path or '\r' in path:
            raise LocalFailure('local_configuration')
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {'Authorization': self.authorization, 'Content-Type': 'application/json'}
        with self.opener.open(Request(self.url + path, data=data, headers=headers, method=method), timeout=10) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise LocalFailure('invalid_result')
            return json.loads(raw) if raw else None

    def __exit__(self, *_):
        if self.process:
            terminate(self.process)
            for stream in (self.process.stdin, self.process.stdout):
                if stream:
                    stream.close()
            self.reader.join(timeout=2)
