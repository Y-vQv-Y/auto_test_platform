# AI 自动测试平台

基于 **Playwright + pytest** 的企业级自动化测试平台，支持 **多 AI 接口**智能生成测试用例并自动执行。

## 功能特性

### 核心能力
- **AI 驱动测试**：支持 OpenAI / Claude / 通义千问 / DeepSeek 等 AI 接口，自动读取源码生成测试用例
- **自动化执行**：基于 Playwright 驱动真实浏览器，支持异步执行和实时进度推送（WebSocket）
- **多项目支持**：管理多个被测项目的源代码路径、部署URL、框架类型

### CI/CD 集成
- **Jenkins 集成**：内置 Jenkins Pipeline 模板，CI/CD 阶段自动触发生成并执行测试
- **Webhook 回调**：支持 Jenkins webhook 签名验证，接收构建状态通知

### 安全控制
- **URL 白名单**：仅允许向授权 URL 发送测试请求，保护内网安全
- **工具白名单**：控制 Playwright 操作权限，禁止危险操作（evaluate / set_content 等）
- **只读模式**：可选只读执行，阻止测试脚本进行写操作
- **自动回滚**：测试异常时自动恢复环境到初始状态
- **安全审计日志**：记录所有安全相关事件

### 登录态管理
- **滑块验证码**：弹出完整浏览器让用户手动完成滑块验证
- **会话保持**：自动保存 cookies 和 localStorage，后续测试自动恢复登录状态
- **有效性校验**：具备登录态有效性主动校验机制，可在测试执行前自动确认会话状态，并支持手动触发校验与刷新。
- **Cookie 提取**：针对 `HttpOnly` 等安全限制，提供[详细的 Cookie 提取指南](docs/cookie_extraction_guide.md)，指导用户通过浏览器开发者工具获取完整会话信息。
- **自动登录配置**：支持配置用户名、密码及页面元素选择器，实现[全自动登录与会话保持](docs/auto_login_guide.md)。
- **实现网站登录**：提供[在项目中实现网站登录的详细指南](docs/project_login_implementation.md)，指导用户如何利用平台内置机制处理复杂登录场景。

### 用户体验
- **科技感看板**：实时展示测试进度、运行状态、统计报表
- **全中文支持**：界面、日志、AI 提示词均为中文
- **WebSocket 实时推送**：测试进度实时更新

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + SQLAlchemy |
| 测试引擎 | Playwright + pytest |
| AI 接口 | OpenAI / Anthropic / 通义千问 / DeepSeek |
| 前端 | React + Vite + Tailwind CSS |
| 实时通信 | WebSocket |
| 数据库 | SQLite（开发）/ PostgreSQL（生产） |
| CI/CD | Jenkins Pipeline |

## 快速开始

### 1. 安装依赖

```bash
# 后端依赖
pip install -r requirements.txt

# Playwright 浏览器
playwright install chromium

# 前端依赖（可选，如果使用已构建的前端）
cd frontend && npm install
```

### 2. 配置

项目根目录下的 `.env` 文件包含所有配置项：

```env
DEBUG=false
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite:///./data/test_platform.db
SECRET_KEY=change-this-to-a-secure-random-key    # 生产环境必须修改
READONLY_MODE=true
AUTO_ROLLBACK_ENABLED=true
PLAYWRIGHT_HEADLESS=true
```

### 3. 启动服务

```bash
# 启动后端（开发模式，支持热重载）
python run_backend.py
# 或: python -m uvicorn backend.main:app --reload --port 8000

# 启动前端（开发模式，可选）
cd frontend && npm run dev
```

### 4. 访问

- 后端 API 文档: http://localhost:8000/docs
- 前端界面: http://localhost:3000

## 使用流程

1. **创建项目** -- 配置名称、部署 URL、源代码路径
2. **配置 AI** -- 添加 OpenAI/Claude 等 API Key 和模型
3. **生成测试** -- 选择 AI 配置和测试类型，自动读取源码生成 Playwright 测试代码
4. **执行测试** -- 选择测试用例，配置部署 URL，开始 Playwright 自动化测试
5. **查看报告** -- 实时查看进度、结果详情、失败截图

## 项目结构

```
auto_test_platform/
├── backend/
│   ├── main.py                 # FastAPI 主入口（生命周期、路由注册、静态文件）
│   ├── config.py               # 全局配置（Pydantic BaseSettings）
│   ├── database.py             # 数据库模型（8张表）
│   ├── api/                    # API 路由
│   │   ├── projects.py         # 项目 CRUD
│   │   ├── test_runs.py        # 测试运行（生成/执行/取消/报告）+ WebSocket
│   │   ├── ai_configs.py       # AI 配置 CRUD
│   │   ├── jenkins.py          # Jenkins 集成配置
│   │   └── settings_api.py     # 仪表盘、安全设置、验证码、测试用例、系统信息
│   ├── ai_engine/              # AI 多接口引擎
│   │   ├── base.py             # AIProvider 抽象基类
│   │   ├── factory.py          # AIFactory 工厂
│   │   └── providers.py        # 5个 AI 提供商实现
│   ├── test_engine/            # 测试执行引擎
│   │   ├── generator.py        # 测试用例生成器
│   │   ├── runner.py           # Playwright 测试运行器
│   │   └── reporter.py         # HTML 报告生成器
│   ├── security/               # 安全控制
│   │   ├── url_validator.py    # URL 白名单验证
│   │   ├── whitelist.py        # Playwright 工具白名单
│   │   └── rollback.py         # 自动回滚
│   ├── captcha/
│   │   └── handler.py          # 验证码处理
│   └── jenkins_integration/
│       └── integration.py      # Jenkins 集成
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # 路由定义（7个页面）
│   │   ├── main.jsx            # React 入口
│   │   ├── api/index.js        # API 客户端（37个接口，与后端完全对齐）
│   │   ├── components/         # Layout + Sidebar
│   │   └── pages/              # 7个页面组件
│   └── index.html
├── generated_tests/            # 生成的测试文件
├── test_reports/               # 测试报告
├── data/                       # SQLite 数据库文件
├── requirements.txt            # Python 依赖（26个包）
├── .env                        # 环境配置
└── README.md                   # 本文件
```

## 数据库

项目使用 SQLAlchemy ORM，启动时自动创建以下 8 张表：

| 表名 | 说明 | 主要字段数 |
|------|------|-----------|
| projects | 被测项目 | 11 |
| test_cases | 测试用例 | 11 |
| test_runs | 测试运行记录 | 22 |
| test_results | 单条测试结果 | 12 |
| ai_configs | AI 提供商配置 | 13 |
| jenkins_configs | Jenkins 连接配置 | 9 |
| login_records | 登录态记录 | 13 |
| security_logs | 安全审计日志 | 7 |

## API 概览

后端共有 **45 个路由**，覆盖以下模块：

- 项目管理（5 个 RESTful API）
- 测试运行（11 个 API，含 WebSocket）
- AI 配置（5 个 CRUD API）
- Jenkins 集成（7 个 API）
- 安全设置（5 个 API）
- 验证码（3 个 API）
- 测试用例（3 个 API）
- 系统信息（2 个 API）

## 已知问题 / 改进建议

- `frontend/package.json` 中 `recharts` 依赖已声明但未被代码引用，可考虑移除
- `frontend/index.html` 引用了 `/vite.svg` favicon 但文件不存在
- `.env` 中的 `SECRET_KEY` 为默认值，生产环境务必替换为安全随机密钥

## Docker 部署

项目提供完整的 Docker 容器化支持，支持两种部署模式。

### 部署模式

| 模式 | 适用场景 | 关键差异 |
|------|---------|---------|
| **同源部署** | 传统服务器部署，前后端同域名 | Nginx 反向代理 `/api`，前端使用相对路径 |
| **分离部署** | 前端托管在 CDN / Vercel / S3 | 前端构建时通过 `VITE_API_BASE_URL` 注入后端地址 |

### 文件结构

```
auto_test_platform/
├── backend/Dockerfile          # 后端镜像构建
├── frontend/Dockerfile         # 前端镜像构建（多阶段：Node → Nginx）
├── frontend/nginx.conf         # Nginx 配置（SPA 回退 + 可选 API 代理）
├── frontend/.env.production    # 生产环境前端配置模板
├── docker-compose.yml          # 编排前后端服务
└── .dockerignore               # 构建上下文过滤
```

### 方式一：Docker Compose（同源部署，推荐）

```bash
# 构建前后端服务
docker compose build --no-cache backend frontend

# 构建并启动所有服务
docker compose up -d

# 查看日志
docker compose logs -f

# 仅启动后端
docker compose up backend -d

# 停止
docker compose down
```

访问 http://localhost:3000 即可使用。

### 方式二：分离部署（前后端分开构建）

#### 构建后端镜像

```bash
docker build -t auto-test-backend:latest -f backend/Dockerfile .
```

#### 构建前端镜像（注入后端地址）

```bash
# 构建时传入后端 API 地址
docker build \
  --build-arg VITE_API_BASE_URL=https://api.example.com \
  -t auto-test-frontend:latest \
  -f frontend/Dockerfile .
```

#### 运行

```bash
# 后端
docker run -d \
  --name auto-test-backend \
  -p 8000:8000 \
  -e SECRET_KEY=your-production-key \
  -v auto-test-data:/app/data \
  auto-test-backend:latest

# 前端
docker run -d \
  --name auto-test-frontend \
  -p 3000:80 \
  auto-test-frontend:latest
```

### 方式三：纯后端镜像（前端单独部署）

如果前端托管在 Vercel / Netlify / S3 等平台，只需构建和运行后端：

```bash
# 构建
docker build -t auto-test-backend:latest -f backend/Dockerfile .

# 运行
docker run -d \
  --name auto-test-backend \
  -p 8000:8000 \
  -e SECRET_KEY=your-production-key \
  -e DATABASE_URL=postgresql://user:pass@host/db \
  auto-test-backend:latest
```

前端构建时设置 `VITE_API_BASE_URL=https://your-backend-domain.com`，部署到静态托管平台即可。

### 环境变量参考

通过 `-e` 或 `environment:` 传入以下环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `8000` | 监听端口 |
| `DATABASE_URL` | `sqlite:///./data/test_platform.db` | 数据库连接（生产建议用 PostgreSQL） |
| `SECRET_KEY` | `change-this-to-a-secure-random-key` | **生产环境必须修改** |
| `DEBUG` | `false` | 调试模式 |
| `URL_WHITELIST_ENABLED` | `false` | URL 白名单开关（关闭=放通所有URL） |
| `READONLY_MODE` | `true` | 只读模式 |
| `AUTO_ROLLBACK_ENABLED` | `true` | 自动回滚 |
| `PLAYWRIGHT_HEADLESS` | `true` | 无头模式 |
| `OPENAI_API_KEY` | — | OpenAI API Key |
| `ANTHROPIC_API_KEY` | — | Anthropic API Key |

### 前后端连接机制

```
开发模式（Vite Proxy）：
  浏览器 ── /api/* ──> Vite Dev Server ──proxy──> FastAPI (:8000)

生产_同源_（Nginx 反向代理）：
  浏览器 ──> Nginx (:80) ── /api/* ──> FastAPI (:8000)
                       └── / ──> 静态文件

生产_分离_（构建时注入）：
  前端（CDN） ── /api/* ──直接──> FastAPI (https://api.example.com:8000)
  VITE_API_BASE_URL=https://api.example.com
```
