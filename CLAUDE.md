# AI 自动测试平台 — 项目手册

## 项目概述

基于 **Playwright + pytest** 的企业级自动化测试平台，支持多 AI 接口智能生成测试用例并自动执行。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI + SQLAlchemy + Pydantic |
| 数据库 | SQLite（开发）/ PostgreSQL（生产） |
| 测试引擎 | Playwright + pytest |
| AI 接口 | OpenAI / Anthropic / 通义千问 / DeepSeek |
| 前端 | React 18 + Vite 5 + Tailwind CSS |
| 实时通信 | WebSocket |
| 部署 | Docker + Docker Compose |

## 项目结构

```
auto_test_platform/
├── backend/                    # 后端（FastAPI）
│   ├── main.py                 # 入口、CORS、路由注册、静态文件服务
│   ├── config.py               # Pydantic Settings 配置
│   ├── database.py             # SQLAlchemy 模型（8 张表）
│   ├── api/                    # API 路由（5 个模块）
│   ├── ai_engine/              # AI 多接口引擎（抽象基类 + 工厂 + 5 个提供商）
│   ├── test_engine/            # 测试执行引擎（生成器 + 运行器 + 报告器）
│   ├── security/               # 安全控制（URL 白名单、工具白名单、自动回滚）
│   ├── captcha/                # 验证码处理
│   └── jenkins_integration/    # Jenkins 集成
├── frontend/                   # 前端（React + Vite）
│   ├── src/
│   │   ├── api/index.js        # API 客户端（37 个接口）
│   │   ├── components/         # Layout + Sidebar
│   │   └── pages/              # 7 个页面
│   ├── Dockerfile              # 前端 Docker 镜像
│   └── nginx.conf              # Nginx 生产配置
├── Dockerfile (backend/)       # 后端 Docker 镜像
└── docker-compose.yml          # 服务编排
```

## 关键架构决策

### 前后端连接方式

前端 API 客户端（`frontend/src/api/index.js`）通过 Vite 环境变量 `VITE_API_BASE_URL` 控制连接目标：

- **空字符串（默认）** → 同源访问。适用于 Vite Proxy（开发）或 Nginx 反向代理（生产）
- **完整 URL** → 前后端分离部署。构建时注入后端地址，前端直接跨域请求

WebSocket 连接自动适配上述模式：分离部署时推导 `http://` → `ws://` / `https://` → `wss://`。

### 数据库

- 开发环境使用 SQLite（文件存储）
- 生产环境建议替换为 PostgreSQL（修改 `DATABASE_URL` 环境变量即可）
- 使用 SQLAlchemy ORM，启动时自动建表

### AI 引擎

- 采用工厂模式 + 抽象基类，支持 OpenAI / Anthropic / 通义千问 / DeepSeek / 自定义
- 新增提供商只需继承 `AIProvider` 基类并注册到工厂

## 开发命令

```bash
# 后端
python run_backend.py              # 启动开发服务器（热重载）
pip install -r requirements.txt    # 安装依赖
playwright install chromium        # 安装 Playwright 浏览器

# 前端
cd frontend && npm run dev         # 启动 Vite 开发服务器
cd frontend && npm run build       # 构建生产版本

# Docker
docker compose up -d               # 启动所有服务
docker compose up backend -d       # 仅启动后端
```

## 关键约束

- 后端默认端口 **8000**，前端开发端口 **3000**
- 前端 API 路径必须为 `/api/v1/...` 格式
- 所有 API 路由注册在 `backend/main.py` 中
- 静态文件服务：生产模式下后端会自动挂载 `frontend/dist`（如果存在）
- 前端 SPA 路由回退：Nginx 配置中通过 `try_files $uri $uri/ /index.html` 实现

## 安全注意事项

- `SECRET_KEY` 生产环境必须改为安全随机字符串
- URL 白名单默认关闭（放通所有 HTTP/HTTPS URL），可在安全设置页面开启
- `.env` 文件包含敏感信息，不应提交到版本控制

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore

## GSD Workflow

This project uses GSD (Get Shit Done) for workflow management. Planning artifacts live in `.planning/`.

**Active config:** YOLO mode, Fine granularity, Parallel execution, Inherit models
**Current phase:** Phase 1 — Security Hardening (run `/gsd-discuss-phase 1`)

**Key commands:**
- `/gsd-progress` — check project status
- `/gsd-discuss-phase 1` — start Phase 1
- `/gsd-plan-phase 1` — plan Phase 1 directly
- `/gsd-execute-phase` — execute current phase plans

**GSD rules:**
- Check `.planning/STATE.md` for current phase and progress
- Check `.planning/PROJECT.md` for context and constraints
- Check `.planning/ROADMAP.md` for phase structure and dependencies
- Check `.planning/REQUIREMENTS.md` for detailed requirement specs
- Planning docs are in version control — commit them alongside code
