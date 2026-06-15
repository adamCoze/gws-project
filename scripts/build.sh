#!/bin/bash
set -Eeuo pipefail

COZE_WORKSPACE_PATH="${COZE_WORKSPACE_PATH:-$(pwd)}"

echo "=== 构建生产版本 ==="
echo "工作目录: ${COZE_WORKSPACE_PATH}"

# 安装 Node.js 依赖
echo "安装 Node.js 依赖..."
cd "${COZE_WORKSPACE_PATH}"
pnpm install

# 安装 Python 依赖（在构建阶段安装，确保部署环境有缓存）
echo "安装 Python 依赖..."
cd "${COZE_WORKSPACE_PATH}/backend"
pip install -r requirements.txt -q 2>/dev/null || pip3 install -r requirements.txt -q 2>/dev/null || {
    echo "警告: Python 依赖安装失败，将在运行时重试"
}
cd "${COZE_WORKSPACE_PATH}"

# 构建前端（直接调用 vite，避免递归）
echo "构建前端..."
cd "${COZE_WORKSPACE_PATH}"
pnpm exec vite build

# 打包 server
echo "打包 server..."
cd "${COZE_WORKSPACE_PATH}"
pnpm tsup server/server.ts --format esm --out-dir dist-server --external vite

echo "=== 构建完成 ==="
