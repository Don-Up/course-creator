#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_ROOT="$REPO_ROOT/apps/api"
WEB_ROOT="$REPO_ROOT/apps/web"
VENV_ROOT="$API_ROOT/.venv"

# POSIX virtualenvs keep executables in bin/, Windows ones in Scripts/.
venv_python() {
  if [[ -x "$VENV_ROOT/bin/python" ]]; then
    printf '%s' "$VENV_ROOT/bin/python"
  elif [[ -x "$VENV_ROOT/Scripts/python.exe" ]]; then
    printf '%s' "$VENV_ROOT/Scripts/python.exe"
  fi
}

# Prefer the interpreter of an existing virtualenv, then an explicit
# PYTHON_BIN, then the usual system interpreters. Any Python 3.12+ qualifies.
resolve_python() {
  local candidate
  for candidate in \
    "$(venv_python)" \
    "${PYTHON_BIN:-}" \
    "$(command -v python3.14 || true)" \
    "$(command -v python3.13 || true)" \
    "$(command -v python3.12 || true)" \
    "$(command -v python3 || true)" \
    "$(command -v python || true)"; do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

available_port() {
  local port="$1"
  while nc -z 127.0.0.1 "$port" >/dev/null 2>&1; do
    port=$((port + 1))
  done
  printf '%s' "$port"
}

API_PORT="$(available_port "${API_PORT:-8000}")"
WEB_PORT="$(available_port "${WEB_PORT:-5173}")"

PYTHON_BIN="$(resolve_python || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "需要 Python 3.12 或更高版本（3.13 / 3.14 均可）。"
  echo "macOS 可运行: brew install python@3.12"
  echo "也可以显式指定: PYTHON_BIN=/path/to/python bash scripts/start-agent.sh"
  exit 1
fi

# Windows 控制台仍使用传统代码页，强制 UTF-8 以正确解码中文课程内容。
if [[ "${OS:-}" == "Windows_NT" ]]; then
  export PYTHONUTF8=1
fi

if [[ -z "$(venv_python)" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_ROOT"
fi
VENV_PY="$(venv_python)"
if [[ -z "$VENV_PY" ]]; then
  echo "创建虚拟环境失败：$VENV_ROOT"
  exit 1
fi

# 装 `.[dev]`：pytest 与 ruff 是 AGENTS.md 里规定的验证工具，
# 只装运行时依赖会让文档里的 `pytest apps/api/tests` 直接报 ModuleNotFoundError。
if ! "$VENV_PY" -c "import fastapi, pytest" >/dev/null 2>&1; then
  # 在项目目录里用 `.[dev]` 安装：绝对路径后面直接跟 `[dev]` 会被
  # Git Bash 的路径转换改写，改成先 cd 再装最稳。
  (cd "$API_ROOT" && "$VENV_PY" -m pip install -e ".[dev]")
fi

if [[ ! -d "$WEB_ROOT/node_modules" ]]; then
  # 必须先 cd 进 apps/web 再安装：npm 从当前目录向上查找 package.json，
  # `npm --prefix` 在这种布局下会退回到仓库根目录去找。
  (cd "$WEB_ROOT" && npm install)
fi

stop_process() {
  local label="$1"
  local pid="$2"
  local attempts=0

  [[ -z "$pid" ]] && return
  kill -TERM "$pid" 2>/dev/null || return

  while kill -0 "$pid" 2>/dev/null && [[ "$attempts" -lt 30 ]]; do
    sleep 0.1
    attempts=$((attempts + 1))
  done

  if kill -0 "$pid" 2>/dev/null; then
    echo "$label 未在 3 秒内退出，正在强制回收"
    kill -KILL "$pid" 2>/dev/null || true
  fi
  wait "$pid" 2>/dev/null || true
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  stop_process "前端" "${WEB_PID:-}"
  stop_process "API" "${API_PID:-}"
  exit "$status"
}
trap 'exit 130' INT
trap 'exit 143' TERM
trap cleanup EXIT

(
  cd "$API_ROOT"
  # 用 `python -m uvicorn` 而不是 `$VENV_ROOT/bin/uvicorn`：Windows 虚拟环境
  # 的可执行文件在 `Scripts/`，直接写死 `bin/` 会在 Windows 上找不到。
  #
  # --reload：后端改完代码自动生效，不用每次手动重启进程（前端 vite 本来就有
  # 热更新，两边体验一致）。不加这个的话，跑着的进程永远是启动那一刻的代码，
  # 新加的路由会安静地变成 405。
  #
  # --reload-dir app：把监听范围收在 app 源码目录。不指定的话 uvicorn 监听当前
  # 工作目录（这里是 apps/api），会把 .venv 一起拖进去 —— watchfiles 的默认忽略
  # 名单里并没有 .venv。uvicorn 的过滤器只匹配 *.py，可 .venv 里全是 .py，
  # 装个包就会把进程重启一遍。收窄到 app 之后只有源码改动才重启。
  exec "$VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" \
    --reload --reload-dir app
) &
API_PID=$!

(
  cd "$WEB_ROOT"
  # 直接 exec vite 的入口脚本，而不是 `npm run dev`：npm 会把 vite 拉成
  # **孙进程**，cleanup 里的 `kill` 打到 npm 上，vite 不会被带走，
  # 结果 Ctrl+C 之后端口还占着。exec 之后 npm 这一层消失，vite 就是
  # WEB_PID 本身。
  VITE_API_TARGET="http://127.0.0.1:$API_PORT" \
    exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --port "$WEB_PORT"
) &
WEB_PID=$!

echo "AI Course Studio 脚手架已启动"
echo "前端: http://127.0.0.1:$WEB_PORT"
echo "API:  http://127.0.0.1:$API_PORT/docs"
echo "按 Ctrl+C 停止"

wait "$API_PID" "$WEB_PID"
