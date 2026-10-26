import argparse
import json
import os
from pathlib import Path
import random
import time
from uuid import uuid4
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .opencode import run, LocalFailure, Cancelled


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class BridgeClient:
    def __init__(self, url, token):
        parsed = urlsplit(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ValueError("服务器地址仅允许站点根地址。")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")):
            raise ValueError("必须使用 HTTPS；本机开发可使用 HTTP。")
        self.url, self.token = url.rstrip("/"), token
        self.opener = build_opener(NoRedirect())

    def post(self, path, payload):
        req = Request(self.url + "/api/agent-runner/" + path, data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}, method="POST")
        with self.opener.open(req, timeout=15) as response:
            raw = response.read(512 * 1024 + 1)
            if len(raw) > 512 * 1024:
                raise ValueError("服务器响应过大。")
            return json.loads(raw) if raw else None

    def reference(self, path, payload):
        req = Request(self.url + '/api/agent-runner/' + path, data=json.dumps(payload).encode(),
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'}, method='POST')
        with self.opener.open(req, timeout=30) as response:
            raw = response.read(20 * 1024 * 1024 + 1)
            if len(raw) > 20 * 1024 * 1024:
                raise ValueError('参考图片过大。')
            return raw

    def upload(self, path, attempt_id, data):
        boundary = 'mycollab' + uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="attempt_id"\r\n\r\n{attempt_id}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="candidate.png"\r\n'
            'Content-Type: image/png\r\n\r\n').encode() + data + f'\r\n--{boundary}--\r\n'.encode()
        req = Request(self.url + '/api/agent-runner/' + path, data=body, headers={
            'Authorization': 'Bearer ' + self.token, 'Content-Type': 'multipart/form-data; boundary=' + boundary}, method='POST')
        with self.opener.open(req, timeout=60) as response:
            raw = response.read(512 * 1024 + 1)
            if len(raw) > 512 * 1024:
                raise ValueError('服务器响应过大。')
            return json.loads(raw)

    def publish_code(self, path, attempt_id, patch, report):
        boundary = 'mycollab' + uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="attempt_id"\r\n\r\n{attempt_id}\r\n').encode()
        for name, data in (('patch', patch), ('report', report)):
            body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{name}.txt"\r\nContent-Type: text/plain\r\n\r\n').encode() + data + b'\r\n'
        body += f'--{boundary}--\r\n'.encode()
        req = Request(self.url + '/api/agent-runner/' + path, data=body, headers={
            'Authorization': 'Bearer ' + self.token, 'Content-Type': 'multipart/form-data; boundary=' + boundary}, method='POST')
        with self.opener.open(req, timeout=60) as response:
            raw = response.read(512 * 1024 + 1)
            if len(raw) > 512 * 1024:
                raise ValueError('服务器响应过大。')
            return json.loads(raw)


def execute(client, request, model, executable):
    endpoint = f"requests/{request['id']}/"
    attempt = {"attempt_id": request["attempt_id"]}
    def heartbeat():
        try:
            return client.post(endpoint + "heartbeat/", attempt)["status"] == "running"
        except Exception:
            # 无法续租时停止本次模型调用，绝不自动再生成。
            return False
    try:
        result = run(request, model=model, executable=executable, heartbeat=heartbeat)
        payload = {**attempt, "result": result}
    except Cancelled:
        try:
            client.post(endpoint + "heartbeat/", {**attempt, "stopped": True})
        except Exception:
            pass
        return
    except LocalFailure as exc:
        payload = {**attempt, "error": exc.code}
    except Exception:
        payload = {**attempt, "error": "local_failure"}
    # 仅重试同一结果回传；绝不重试模型执行。
    for index in range(3):
        try:
            client.post(endpoint + "result/", payload)
            return
        except HTTPError as exc:
            if exc.code < 500:
                return
        except (OSError, ValueError):
            pass
        time.sleep(2 ** index)
    print("结果未能回传；服务器租约将过期，未重新执行模型。", flush=True)


def main():
    parser = argparse.ArgumentParser(description="MyCollab 本地文本与图像 Runner")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--once", action="store_true", help="只领取一次，用于接入验证")
    parser.add_argument('--select', metavar='REQUEST_ID', help='明确选择本地候选并上传；不会调用模型')
    parser.add_argument('--keys', nargs='+', help='选择预览中的候选编号，例如 candidate_1')
    parser.add_argument('--publish-code', metavar='REQUEST_ID', help='人工审查后发布已有补丁与报告；不调用模型')
    parser.add_argument('--list-repositories', action='store_true', help='只列出本地仓库标识及允许的验证摘要')
    args = parser.parse_args()
    if os.name == "posix" and args.config.stat().st_mode & 0o077:
        parser.error("配置文件必须仅本人可读写，请先 chmod 600。")
    config = json.loads(args.config.read_text())
    if sum(bool(value) for value in (args.select, args.publish_code, args.list_repositories)) > 1:
        parser.error('选择图片、发布代码和列出仓库不能同时使用。')
    if args.list_repositories:
        from .code_workspace import configuration
        for key in config.get('repositories', {}):
            repository = configuration(config, key)
            print(key + '：' + ('、'.join(item['label'] for item in repository['verification']) or '未配置验证'))
        return
    client = BridgeClient(config["server"], config["device_token"])
    if args.publish_code:
        if args.keys:
            parser.error('--keys 只用于图像选择。')
        from .code_execution import publish
        publish(client, config, args.publish_code)
        return
    if args.select:
        from .images import select
        if not args.keys:
            parser.error('--select 必须显式提供 --keys，不默认选择候选。')
        select(client, config, args.select, args.keys)
        return
    if args.keys:
        parser.error('--keys 只能与 --select 一起使用。')
    delay = 15
    while True:
        try:
            request = client.post("claim/", {})
            if request:
                if request.get('kind') == 'code_implement':
                    from .code_execution import execute_code
                    execute_code(client, request, config)
                elif request.get('kind') in ('image_generate', 'image_edit'):
                    from .images import execute_image
                    execute_image(client, request, config)
                else:
                    execute(client, request, config.get("model", ""), config.get("opencode", "opencode"))
                delay = 15
            else:
                delay = min(60, delay * 1.5)
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise SystemExit("设备凭据过期、撤销或用户停用，请重新绑定。")
            delay = min(60, delay * 2)
        except (OSError, ValueError):
            print("连接暂不可用，等待后重试领取。", flush=True)
            delay = min(60, delay * 2)
        if args.once:
            break
        time.sleep(delay + random.uniform(0, 3))


if __name__ == "__main__":
    main()
