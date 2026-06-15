# 集团工作跟进系统 - 项目说明

## 项目概览

集团工作跟进系统是一个全栈 Web 应用，用于管理和跟踪集团各部门的工作进展。系统通过 IMAP 监听企业邮箱，使用 DeepSeek AI 自动分析邮件并提取工作项，支持多角色权限管理和看板展示。

## 技术栈

### 前端
- **框架**: React 18 + TypeScript
- **UI 库**: Ant Design 5 + Ant Design Icons
- **路由**: React Router DOM 6
- **构建工具**: Vite 7
- **HTTP 客户端**: Axios
- **样式**: Tailwind CSS

### 后端
- **框架**: FastAPI (Python 3.11+)
- **数据库**: SQLite (WAL 模式)
- **ORM**: SQLAlchemy 2.0 (异步)
- **认证**: JWT (python-jose)
- **密码哈希**: bcrypt (passlib)
- **邮件**: IMAP (imaplib)
- **AI**: DeepSeek API

## 目录结构

```
.
├── backend/                 # 后端 Python FastAPI 项目
│   ├── main.py             # FastAPI 入口
│   ├── config.py           # 配置管理
│   ├── database.py         # 数据库连接与初始化
│   ├── models.py           # SQLAlchemy 数据模型
│   ├── schemas.py          # Pydantic 数据模型
│   ├── auth.py             # JWT 认证与权限
│   ├── routers/            # API 路由
│   │   ├── auth.py         # 认证接口
│   │   ├── users.py        # 用户管理
│   │   ├── work_items.py   # 工作项管理
│   │   ├── departments.py  # 部门管理
│   │   ├── email_config.py # 邮箱配置
│   │   ├── holidays.py     # 节假日配置
│   │   ├── status_logs.py  # 状态日志
│   │   └── kanban.py       # 看板数据
│   ├── services/           # 业务服务
│   │   ├── email_service.py  # IMAP 邮件监听
│   │   └── ai_service.py     # DeepSeek AI 分析
│   └── requirements.txt    # Python 依赖
├── src/                    # 前端 React 源码
│   ├── main.tsx           # React 入口
│   ├── App.tsx            # 路由配置
│   ├── index.css          # 全局样式
│   ├── components/        # 组件
│   │   ├── AuthProvider.tsx   # 认证上下文
│   │   └── MainLayout.tsx     # 主布局
│   ├── pages/             # 页面
│   │   ├── LoginPage.tsx          # 登录页
│   │   ├── DashboardPage.tsx      # 首页（我的工作）
│   │   ├── KanbanPage.tsx         # 看板页
│   │   └── admin/                 # 后台管理
│   │       ├── UserManagementPage.tsx
│   │       ├── EmailConfigPage.tsx
│   │       ├── HolidayConfigPage.tsx
│   │       ├── WorkItemManagementPage.tsx
│   │       └── StatusLogPage.tsx
│   ├── services/          # 服务层
│   │   └── api.ts         # API 请求封装
│   └── types/             # 类型定义
│       └── index.ts
├── server/                # Express 服务器（前端代理）
│   ├── server.ts          # 服务器入口
│   ├── vite.ts            # Vite 集成
│   └── routes/
│       └── index.ts       # API 代理路由
├── scripts/               # 构建与启动脚本
├── package.json           # Node.js 依赖
├── vite.config.ts         # Vite 配置
└── tsconfig.json          # TypeScript 配置
```

## 核心功能

### 1. 邮件监听与 AI 分析
- 通过 IMAP 协议监听阿里企业邮箱
- 使用 DeepSeek V4-Flash AI 自动分析邮件内容
- 提取工作项信息：部门、任务类型、责任人、截止日期
- 支持降级处理（AI 不可用时使用关键词匹配）

### 2. 工作项管理
- 支持任务(task)和会签(cosign)两种类型
- 四种状态：待处理、进行中、已完成、已逾期
- 支持机密标记，仅高级角色可见
- 按部门分组展示

### 3. 权限系统
六种角色，分级权限：
- **管理员** (admin): 最高权限，可管理所有配置
- **总裁** (president): 可查看所有工作项（含机密）
- **规管** (regulator): 可查看和管理工作项
- **区总** (district_manager): 可查看和管理工作项
- **经理** (manager): 可管理工作项
- **专员** (staff): 仅可查看自己的工作项

### 4. 看板展示
- 按部门分组展示工作项
- 四列看板：待处理、进行中、已完成、已逾期
- 支持按部门筛选
- 机密工作项根据角色权限过滤

### 5. 后台管理
- 用户管理：增删改查、重置密码
- 邮箱配置：IMAP 连接配置、连接测试
- 节假日配置：工作日计算
- 工作项管理：手动编辑工作项
- 状态变更日志：记录所有状态变更

## 数据库设计

### 主要表
- `users`: 用户表（含角色、部门关联）
- `departments`: 部门表
- `work_items`: 工作项表（含状态、类型、机密标记）
- `status_logs`: 状态变更日志表
- `email_configs`: 邮箱配置表
- `holidays`: 节假日表

### SQLite WAL 模式
启用 Write-Ahead Logging 提高并发性能：
```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=10000;
```

## 启动说明

### 开发环境
```bash
# 安装依赖
pnpm install
cd backend && pip install -r requirements.txt

# 启动服务（前端 + 后端）
bash scripts/dev.sh
```

### 生产环境
```bash
# 构建
bash scripts/build.sh

# 启动
bash scripts/start.sh
```

### 环境变量
- `DEPLOY_RUN_PORT`: 前端服务端口（默认 5000）
- `DATABASE_URL`: 数据库连接（默认 sqlite+aiosqlite:///./data/gws.db）
- `SECRET_KEY`: JWT 密钥
- `DEEPSEEK_API_KEY`: DeepSeek API 密钥
- `DEEPSEEK_API_URL`: DeepSeek API 地址
- `DEEPSEEK_MODEL`: DeepSeek 模型名称

## 默认账户

- 用户名: `admin`
- 密码: `admin123`
- 角色: 管理员

## API 接口

### 认证
- `POST /api/auth/login` - 登录
- `GET /api/auth/me` - 获取当前用户

### 工作项
- `GET /api/work-items` - 获取工作项列表
- `GET /api/work-items/my` - 获取我的工作项
- `POST /api/work-items` - 创建工作项
- `PUT /api/work-items/{id}` - 更新工作项
- `PATCH /api/work-items/{id}/status` - 更新状态
- `DELETE /api/work-items/{id}` - 删除工作项

### 看板
- `GET /api/kanban` - 获取看板数据

### 部门
- `GET /api/departments` - 获取部门列表
- `POST /api/departments` - 创建部门
- `PUT /api/departments/{id}` - 更新部门
- `DELETE /api/departments/{id}` - 删除部门

### 用户管理
- `GET /api/users` - 获取用户列表
- `POST /api/users` - 创建用户
- `PUT /api/users/{id}` - 更新用户
- `DELETE /api/users/{id}` - 删除用户
- `POST /api/users/{id}/reset-password` - 重置密码

### 邮箱配置
- `GET /api/email-configs` - 获取邮箱配置
- `POST /api/email-configs` - 创建配置
- `PUT /api/email-configs/{id}` - 更新配置
- `DELETE /api/email-configs/{id}` - 删除配置
- `POST /api/email-configs/{id}/test` - 测试连接

### 节假日
- `GET /api/holidays` - 获取节假日列表
- `POST /api/holidays` - 创建节假日
- `PUT /api/holidays/{id}` - 更新节假日
- `DELETE /api/holidays/{id}` - 删除节假日

### 状态日志
- `GET /api/status-logs` - 获取状态变更日志

## 开发规范

- 使用 TypeScript strict 模式
- 禁止隐式 any
- 函数参数必须标注类型
- 使用 Tailwind CSS 进行样式开发
- 前端使用 Ant Design 组件库
- 后端使用 FastAPI 异步特性

## 注意事项

1. **机密工作项**: 仅总裁及以上角色可见
2. **邮箱前缀匹配**: "我的工作"通过邮箱前缀匹配责任人
3. **WAL 模式**: SQLite 启用 WAL 提高并发性能
4. **AI 降级**: DeepSeek API 不可用时使用关键词匹配
5. **状态日志**: 所有状态变更自动记录日志
