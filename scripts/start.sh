#!/bin/bash
set -Eeuo pipefail

COZE_WORKSPACE_PATH="${COZE_WORKSPACE_PATH:-$(pwd)}"
DEPLOY_RUN_PORT="${DEPLOY_RUN_PORT:-5000}"

echo "=== 启动生产环境 ==="
echo "工作目录: ${COZE_WORKSPACE_PATH}"
echo "前端端口: ${DEPLOY_RUN_PORT}"

# 安装 Python 依赖
echo "安装 Python 依赖..."
cd "${COZE_WORKSPACE_PATH}/backend"
pip install -r requirements.txt -q 2>/dev/null || pip3 install -r requirements.txt -q 2>/dev/null || true
cd "${COZE_WORKSPACE_PATH}"

# 启动后端服务（生产模式，不使用 reload）
echo "启动 FastAPI 后端 (端口 8000)..."
cd "${COZE_WORKSPACE_PATH}/backend"
COZE_PROJECT_ENV=PROD python3 -c "
import uvicorn
uvicorn.run('main:app', host='0.0.0.0', port=8000, log_level='warning', reload=False)
" > /tmp/backend.log 2>&1 &
BACKEND_PID=$!
cd "${COZE_WORKSPACE_PATH}"

# 等待后端启动（最多 15 秒）
echo "等待后端启动..."
i=0
while [ $i -lt 15 ]; do
    if curl -s -f http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "后端启动成功 (PID: $BACKEND_PID)"
        break
    fi
    i=$((i + 1))
    if [ $i -eq 15 ]; then
        echo "后端启动失败，检查日志:"
        cat /tmp/backend.log
        exit 1
    fi
    sleep 1
done

# 启动前端服务（生产模式）
echo "启动前端服务 (端口 ${DEPLOY_RUN_PORT})..."
COZE_PROJECT_ENV=PROD PORT=$DEPLOY_RUN_PORT exec node dist-server/server.js
