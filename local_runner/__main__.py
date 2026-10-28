import argparse
import _thread
from datetime import datetime
import subprocess
import ssl
import threading
import json
import os
from pathlib import Path
import random
import signal
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from .opencode import run, LocalFailure, Cancelled
from .state import StateStore
from .parent_process import ParentProcess
from .child_process import version_check


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class BridgeClient:
    def __init__(self, url, token, ca_file=None):
        parsed = urlsplit(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ValueError("服务器地址仅允许站点根地址。")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")):
            raise ValueError("必须使用 HTTPS；本机开发可使用 HTTP。")
        self.url, self.token = url.rstrip("/"), token
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context(cafile=ca_file)))

    def post(self, path, payload):
        req = Request(self.url + "/api/agent-runner/" + path, data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}, method="POST")
        with self.opener.open(req, timeout=15) as response:
            raw = response.read(512 * 1024 + 1)
            if len(raw) > 512 * 1024:
                raise ValueError("服务器响应过大。")
            return json.loads(raw) if raw else None


def execute(client, request, model, executable, store=None):
    if store:
        store.begin(request)
    started = time.monotonic()
    def lease_deadline(value):
        try:
            remaining = datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() - time.time()
            return time.monotonic() + max(0, min(150, remaining - 20))
        except (AttributeError, ValueError, TypeError):
            return time.monotonic()
    deadline = lease_deadline(request.get('lease_expires_at'))
    if store and time.monotonic() >= deadline:
        store.status('expired')
        return

    endpoint = f"requests/{request['id']}/"
    attempt = {"attempt_id": request["attempt_id"]}
    def heartbeat():
        nonlocal deadline
        try:
            response = client.post(endpoint + "heartbeat/", attempt)
            if response["status"] != "running":
                return False
            deadline = lease_deadline(response.get("lease_expires_at"))
            return time.monotonic() < deadline
        except HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                return False
        except (OSError, ValueError, KeyError):
            pass
        # 仅在已确认租约安全窗口内容忍短暂断网，不延长服务器租约。
        return time.monotonic() < deadline
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
    if store:
        store.save_result(request, payload)
        store.status('delivering', execution_ms=round((time.monotonic() - started) * 1000))
        store.recover(client)
        return
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
    parser.add_argument("--config-stdin", action="store_true",
                        help="从标准输入读取一行私有配置；--config 仅决定状态目录，不写入凭据")
    parser.add_argument("--control-stdin", action="store_true", help="配置行后的管道输入或关闭触发停止，仅供桌面宿主")
    parser.add_argument("--desktop-events", action="store_true", help="取得独占锁后输出桌面就绪事件")
    parser.add_argument("--once", action="store_true", help="只领取一次，用于接入验证")
    parser.add_argument("--diagnose", action="store_true", help="检查配置、版本及服务器，不领取任务或调用模型")
    parser.add_argument("--status", action="store_true", help="读取脱敏本地运行状态")
    parser.add_argument("--parent-pid", type=int, help="桌面进程退出时停止 Runner")
    args = parser.parse_args(argv)
    if args.desktop_events and not args.control_stdin:
        parser.error("桌面事件要求停止管道。")
    if args.control_stdin and (not args.config_stdin or args.status):
        parser.error("停止管道要求 --config-stdin，且不能用于状态读取。")
    if args.parent_pid is not None and args.parent_pid <= 1:
        parser.error("父进程编号无效。")
    if args.parent_pid:
        try:
            parent = ParentProcess(args.parent_pid)
        except OSError:
            parser.error("无法监测桌面宿主，请重新启动客户端。")
        def watch_parent():
            try:
                while parent.alive():
                    time.sleep(1)
            except OSError:
                pass
            finally:
                parent.close()
                # 让主线程走既有 finally 清理，Windows 上也不直接 TerminateProcess。
                if os.name == 'posix':
                    os.kill(os.getpid(), signal.SIGTERM)
                else:
                    os._exit(130)
        threading.Thread(target=watch_parent, daemon=True).start()
    path = args.config.expanduser()
    try:
        if args.config_stdin:
            # 宿主通过匿名管道交接凭据，不放入 argv、环境或明文临时文件。
            raw = bytearray()
            # 不使用缓冲读取，避免预读并吞掉紧随配置行到达的停止指令。
            while len(raw) <= 32 * 1024:
                chunk = os.read(sys.stdin.fileno(), 1)
                if not chunk:
                    break
                raw.extend(chunk)
                if chunk == b"\n":
                    break
            if not raw or len(raw) > 32 * 1024 or not raw.endswith(b"\n"):
                parser.error("标准输入配置必须是最多 32 KiB、以换行结束的一行 JSON。")
            config = json.loads(raw.decode("utf-8"))
        else:
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
        client = BridgeClient(config["server"], config["device_token"], ca_file=config["ca_file"]) if config.get("ca_file") else BridgeClient(config["server"], config["device_token"])
    except (ValueError, OSError, ssl.SSLError):
        parser.error("服务器地址或 CA 证书无效：请使用 HTTPS 站点根地址（本机开发允许 HTTP），不得包含凭据、查询或片段。")
    store = StateStore(path, config["server"], config["device_token"])
    if args.status:
        print(json.dumps(store.snapshot(), ensure_ascii=False))
        return
    stop_event = threading.Event() if args.control_stdin else None
    if stop_event is not None:
        def watch_control():
            try:
                # 无缓冲 fd 读取不会在解释器退出时占用 stdin 的缓冲锁。
                os.read(sys.stdin.fileno(), 1)
            except OSError:
                pass
            finally:
                stop_event.set()
                if os.name == 'posix':
                    os.kill(os.getpid(), signal.SIGTERM)
                else:
                    _thread.interrupt_main(signal.SIGTERM)
        threading.Thread(target=watch_control, daemon=True).start()
    if args.diagnose:
        checks = {"config": "ok", "opencode": "unavailable", "server": "unavailable", "protocol": 1}
        try:
            version = version_check(config.get("opencode", "opencode"))
            checks["opencode"] = "ok" if version.returncode == 0 and version.stdout.strip() == "opencode v2.1.3" else "incompatible"
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            info = client.post("status/", {})
            checks["server"] = "ok" if info.get("schema_versions") == [1] else "incompatible"
            checks["capabilities"] = info.get("capabilities", [])
        except HTTPError as exc:
            checks["server"] = "unauthorized" if exc.code in (401, 403) else "unavailable"
        except (OSError, ValueError, AttributeError):
            pass
        print(json.dumps(checks, ensure_ascii=False))
        return
    try:
        with store.lock():
            delay = 3
            store.status('starting')
            if args.desktop_events:
                print(json.dumps({'event': 'ready'}), flush=True)
            try:
                while True:
                    try:
                        # 先恢复落盘结果；未成功恢复时不领取新任务。
                        recovered = store.recover(client)
                        request = client.post("claim/", {}) if recovered else None
                        if request:
                            execute(client, request, config["model"], config.get("opencode", "opencode"), store)
                            delay = 3
                        else:
                            delay = min(10, delay * 1.5)
                        store.status('idle' if recovered else 'offline')
                    except HTTPError as exc:
                        if exc.code in (401, 403):
                            store.status('unauthorized')
                            raise SystemExit("设备凭据过期、撤销或用户停用，请重新绑定。")
                        store.status('offline')
                        delay = min(30, delay * 2)
                    except (OSError, ValueError):
                        store.status('offline')
                        print("连接或本地状态暂不可用，等待重试；不会重新执行模型。", flush=True)
                        delay = min(30, delay * 2)
                    if args.once:
                        break
                    pause = delay + random.uniform(0, 1)
                    if stop_event is not None:
                        if stop_event.wait(pause):
                            raise KeyboardInterrupt
                    else:
                        time.sleep(pause)
            finally:
                store.status('stopped')
    except ValueError as exc:
        parser.error(str(exc))


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
