#!/bin/bash
set -Eeuo pipefail

COZE_WORKSPACE_PATH="${COZE_WORKSPACE_PATH:-$(pwd)}"
PORT=5000
DEPLOY_RUN_PORT="${DEPLOY_RUN_PORT:-$PORT}"

# 安装 Python 依赖
cd "${COZE_WORKSPACE_PATH}/backend"
pip install -r requirements.txt -q 2>/dev/null || pip3 install -r requirements.txt -q 2>/dev/null || true
cd "${COZE_WORKSPACE_PATH}"

# 启动后端服务
echo "Starting FastAPI backend on port 8000..."
cd "${COZE_WORKSPACE_PATH}/backend"
DEPLOY_RUN_PORT=8000 python3 main.py &
cd "${COZE_WORKSPACE_PATH}"

# 启动前端服务
echo "Starting production server on port ${DEPLOY_RUN_PORT}..."
PORT=$DEPLOY_RUN_PORT node dist-server/server.js
