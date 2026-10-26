import argparse
import json
import os
from pathlib import Path
import random
import signal
import sys
import time
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


def run_cli(argv=None):
    parser = argparse.ArgumentParser(description="MyCollab 本地 OpenCode 文本辅助 Runner")
    parser.add_argument("--config", type=Path, default=Path("~/.config/MyCollab/mycollab-runner.json"),
                        help="配置文件（默认：~/.config/MyCollab/mycollab-runner.json）")
    parser.add_argument("--once", action="store_true", help="只领取一次，用于接入验证")
    args = parser.parse_args(argv)
    path = args.config.expanduser()
    try:
        if os.name == "posix" and path.stat().st_mode & 0o077:
            parser.error("配置文件必须仅本人可读写，请先 chmod 600。")
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        parser.error(f"配置文件不存在：{path}。请创建配置文件，或使用 --config 指定路径。")
    except OSError:
        parser.error(f"无法读取配置文件：{path}。请检查文件及访问权限。")
    except (ValueError, UnicodeError):
        parser.error(f"配置文件不是有效的 UTF-8 JSON：{path}。")
    if not isinstance(config, dict) or any(not isinstance(config.get(key), str) or not config[key].strip()
                                          for key in ("server", "device_token", "model")):
        parser.error("配置必须包含非空字符串 server、device_token 和 model。")
    if "opencode" in config and (not isinstance(config["opencode"], str) or not config["opencode"].strip()):
        parser.error("opencode 必须是非空的可执行文件路径或名称。")
    try:
        client = BridgeClient(config["server"], config["device_token"])
    except ValueError:
        parser.error("服务器地址无效：请使用 HTTPS 站点根地址（本机开发允许 HTTP），不得包含凭据、查询或片段。")
    delay = 15
    while True:
        try:
            request = client.post("claim/", {})
            if request:
                execute(client, request, config["model"], config.get("opencode", "opencode"))
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


def main(argv=None):
    # testrun 通过 SIGTERM 停止后台 Runner，复用 Ctrl-C 的资源清理。
    previous = signal.signal(signal.SIGTERM, signal.default_int_handler)
    try:
        run_cli(argv)
    except KeyboardInterrupt:
        print("\nRunner 已停止；未回传的请求将由服务器租约过期处理。", file=sys.stderr, flush=True)
        return 130
    finally:
        signal.signal(signal.SIGTERM, previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
