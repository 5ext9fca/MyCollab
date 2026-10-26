#!/usr/bin/env bash
# 启动本地测试环境；不清空数据库，不调用生产部署配置。
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
seed_demo=false
case "${1:-}" in
  "") ;;
  --seed) seed_demo=true ;;
  -h|--help)
    cat <<'HELP'
用法：./testrun.sh [--seed]
启动 PostgreSQL、执行迁移并运行 Django、Vite 与 LocalRunner；缺少依赖时自动安装。
--seed  加载演示数据（已存在时跳过，不重置数据）
前端：http://127.0.0.1:5173
后端：http://127.0.0.1:8000
LocalRunner 使用 ~/.config/MyCollab/mycollab-runner.json；未配置时提示并跳过。
Ctrl+C 停止本次前后端与 LocalRunner 进程；保留 PostgreSQL 容器和数据。
首次运行需要 Python 3.14、Node 24+、Docker Compose，以及依赖下载网络。
HELP
    exit 0 ;;
  *) echo "未知参数：$1；请使用 --help。" >&2; exit 2 ;;
esac
if (( $# > 1 )); then
  echo "参数过多；请使用 --help。" >&2
  exit 2
fi

cd "$project_root"
for tool in docker node npm curl; do
  command -v "$tool" >/dev/null || { echo "缺少命令：$tool" >&2; exit 1; }
done
docker compose version >/dev/null
docker info >/dev/null
node -e 'if (Number(process.versions.node.split(".")[0]) < 24) { console.error("需要 Node 24 或更新版本"); process.exit(1) }'

python_bin="$project_root/backend/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  command -v python3.14 >/dev/null || { echo "需要 Python 3.14，请先安装。" >&2; exit 1; }
  python3.14 -m venv "$project_root/backend/.venv"
fi
"$python_bin" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else "backend/.venv 必须使用 Python 3.14")'
# 固定使用仓库本地数据库，避免继承外部数据库或生产 Django 配置。
export POSTGRES_DB=mycollab POSTGRES_USER=mycollab POSTGRES_PASSWORD=mycollab
export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432
export DJANGO_SETTINGS_MODULE=config.settings DJANGO_DEBUG=true
export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
export DJANGO_MEDIA_ROOT="$project_root/backend/media"

"$python_bin" - <<'PY'
import socket
for port in (8000, 5173):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            raise SystemExit(f"端口 {port} 已被占用，请先停止对应服务后重试。")
PY

if ! "$python_bin" -m pip check >/dev/null 2>&1 ||
   ! "$python_bin" -c 'import django, rest_framework, psycopg, gunicorn' >/dev/null 2>&1; then
  "$python_bin" -m pip install -r "$project_root/backend/requirements.txt"
fi
if [[ ! -x "$project_root/frontend/node_modules/.bin/vite" ]]; then
  (cd "$project_root/frontend" && npm ci)
fi

echo "启动本地 PostgreSQL，等待数据库就绪……"
docker compose -f "$project_root/docker-compose.yml" up -d --wait --wait-timeout 60 db
(cd "$project_root/backend" && "$python_bin" manage.py migrate --noinput && "$python_bin" manage.py check)
if "$seed_demo"; then
  (cd "$project_root/backend" && "$python_bin" manage.py seed_demo)
fi

backend_pid=""
frontend_pid=""
runner_pid=""
cleanup() {
  trap - EXIT
  trap '' INT TERM
  for pid in "$backend_pid" "$frontend_pid" "$runner_pid"; do
    if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; fi
  done
  for pid in "$backend_pid" "$frontend_pid" "$runner_pid"; do
    if [[ -n "$pid" ]]; then wait "$pid" 2>/dev/null || true; fi
  done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# 禁用 Django 重载子进程，确保退出时只清理本次启动的进程。
(cd "$project_root/backend" && exec "$python_bin" -u manage.py runserver 127.0.0.1:8000 --noreload) &
backend_pid=$!
(cd "$project_root/frontend" && exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort) &
frontend_pid=$!

ensure_running() {
  if ! kill -0 "$backend_pid" 2>/dev/null || ! kill -0 "$frontend_pid" 2>/dev/null; then
    echo "前端或后端已退出，正在停止本次环境；请查看上方错误。" >&2
    exit 1
  fi
}
ready=false
for ((attempt=0; attempt<60; attempt++)); do
  ensure_running
  if curl --noproxy '*' -fsS --max-time 1 http://127.0.0.1:8000/api/auth/csrf/ >/dev/null 2>&1 &&
     curl --noproxy '*' -fsS --max-time 1 http://127.0.0.1:5173/ >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
if ! "$ready"; then echo "服务启动超时。" >&2; exit 1; fi
runner_config="$HOME/.config/MyCollab/mycollab-runner.json"
if [[ -f "$runner_config" ]]; then
  echo "启动 LocalRunner，使用配置：$runner_config"
  "$python_bin" -u -m local_runner --config "$runner_config" &
  runner_pid=$!
else
  echo "未找到 LocalRunner 配置：${runner_config}；跳过自动启动。配置方法见 local_runner/README.md。"
fi
echo "测试环境已就绪：http://127.0.0.1:5173"
echo "按 Ctrl+C 停止前后端与 LocalRunner；数据库和数据会保留。后端代码修改后需重启脚本。"
while true; do
  ensure_running
  if [[ -n "$runner_pid" ]] && ! kill -0 "$runner_pid" 2>/dev/null; then
    runner_status=0
    wait "$runner_pid" || runner_status=$?
    echo "LocalRunner 已退出（退出码 ${runner_status}）；前后端继续运行，请查看上方提示。" >&2
    runner_pid=""
  fi
  sleep 1
done
