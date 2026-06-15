#!/bin/bash
set -Eeuo pipefail

COZE_WORKSPACE_PATH="${COZE_WORKSPACE_PATH:-$(pwd)}"
DEPLOY_RUN_PORT="${DEPLOY_RUN_PORT:-5000}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

echo "=== 启动生产环境 ==="
echo "工作目录: ${COZE_WORKSPACE_PATH}"
echo "前端端口: ${DEPLOY_RUN_PORT}"
echo "后端端口: ${BACKEND_PORT}"

# 清理旧进程
echo "清理旧进程..."
pkill -f "uvicorn.*main:app" 2>/dev/null || true
pkill -f "node.*dist-server/server.js" 2>/dev/null || true
sleep 1

# 检查并释放端口
for port in $DEPLOY_RUN_PORT $BACKEND_PORT; do
    pid=$(ss -lptn "sport = :$port" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | head -1)
    if [ -n "$pid" ]; then
        echo "释放端口 $port (PID: $pid)..."
        kill -9 "$pid" 2>/dev/null || true
        sleep 1
    fi
done

# 安装 Python 依赖
echo "安装 Python 依赖..."
cd "${COZE_WORKSPACE_PATH}/backend"
if ! pip install -r requirements.txt -q 2>&1; then
    echo "pip install 失败，尝试 pip3..."
    if ! pip3 install -r requirements.txt -q 2>&1; then
        echo "警告: Python 依赖安装失败，继续启动..."
    fi
fi
cd "${COZE_WORKSPACE_PATH}"

# 启动后端服务（生产模式，不使用 reload）
echo "启动 FastAPI 后端 (端口 ${BACKEND_PORT})..."
cd "${COZE_WORKSPACE_PATH}/backend"
COZE_PROJECT_ENV=PROD BACKEND_PORT=$BACKEND_PORT python3 -c "
import os
import uvicorn
port = int(os.environ.get('BACKEND_PORT', 8000))
uvicorn.run('main:app', host='0.0.0.0', port=port, log_level='warning', reload=False)
" > /tmp/backend.log 2>&1 &
BACKEND_PID=$!
cd "${COZE_WORKSPACE_PATH}"

# 等待后端启动（最多 15 秒）
echo "等待后端启动..."
i=0
while [ $i -lt 15 ]; do
    if curl -s -f http://localhost:${BACKEND_PORT}/api/health > /dev/null 2>&1; then
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
COZE_PROJECT_ENV=PROD PORT=$DEPLOY_RUN_PORT BACKEND_URL=http://localhost:${BACKEND_PORT} exec node dist-server/server.js
