#!/bin/bash
set -Eeuo pipefail

PORT=5000
COZE_WORKSPACE_PATH="${COZE_WORKSPACE_PATH:-$(pwd)}"
DEPLOY_RUN_PORT="${DEPLOY_RUN_PORT:-${PORT}}"

cd "${COZE_WORKSPACE_PATH}"

kill_port_if_listening() {
    local pids
    pids=$(ss -H -lntp 2>/dev/null | awk -v port="${DEPLOY_RUN_PORT}" '$4 ~ ":"port"$"' | grep -o 'pid=[0-9]*' | cut -d= -f2 | paste -sd' ' - || true)
    if [[ -z "${pids}" ]]; then
      echo "Port ${DEPLOY_RUN_PORT} is free."
      return
    fi
    echo "Port ${DEPLOY_RUN_PORT} in use by PIDs: ${pids} (SIGKILL)"
    echo "${pids}" | xargs -I {} kill -9 {}
    sleep 1
}

echo "Clearing port ${DEPLOY_RUN_PORT} before start."
kill_port_if_listening

# 安装 Python 依赖
echo "Installing Python dependencies..."
cd "${COZE_WORKSPACE_PATH}/backend"
pip install -r requirements.txt -q 2>/dev/null || pip3 install -r requirements.txt -q 2>/dev/null || true
cd "${COZE_WORKSPACE_PATH}"

# 启动后端服务 (FastAPI on port 8000)
echo "Starting FastAPI backend on port 8000..."
cd "${COZE_WORKSPACE_PATH}/backend"
DEPLOY_RUN_PORT=8000 python3 main.py &
BACKEND_PID=$!
cd "${COZE_WORKSPACE_PATH}"

# 启动前端服务 (Vite dev server on port 5000)
echo "Starting Vite dev server on port ${DEPLOY_RUN_PORT}..."
PORT=${DEPLOY_RUN_PORT} pnpm tsx watch server/server.ts &
FRONTEND_PID=$!

# 等待所有进程
wait $FRONTEND_PID $BACKEND_PID
