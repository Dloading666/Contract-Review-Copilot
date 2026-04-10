# Contract Review Copilot

面向租房与消费合同场景的 AI 审查工具。当前版本提供合同导入、OCR 提取、多阶段风险审查、人工确认断点、避坑指南报告生成、条款自动修订建议，以及基于审查结果的追问问答。

## 当前版本状态

- 主模型：SiliconFlow OpenAI 兼容接口
- 审查模型：`Qwen/Qwen3.5-4B`
- OCR 模型：`PaddlePaddle/PaddleOCR-VL-1.5`
- 主登录方式：手机号 + 短信验证码
- 辅助登录方式：邮箱 + 密码
- 邮箱注册后需绑定手机号，才能使用完整合同审查
- 审查主流程：OCR/导入 -> 实体提取 -> 法律检索路由 -> 风险扫描 -> 人工确认 -> 报告生成

说明：
- README 以当前已接入的公开功能为准。
- 仓库中如有未接入主流程的实验性或历史残留代码，不视为当前可用能力。

## 技术栈

### Frontend

- React 18
- Vite 5
- TypeScript
- Vitest

### Backend

- FastAPI
- Python 3.11
- LangGraph StateGraph
- PostgreSQL
- pgvector
- Redis

### AI / OCR / 检索

- SiliconFlow OpenAI 兼容接口
- Qwen 3.5 4B
- PaddleOCR-VL
- DuckDuckGo Web Search

## 核心功能

### 1. 合同导入

支持以下材料格式：

- `TXT`
- `DOCX`
- `PDF`
- `JPG / JPEG / PNG / WEBP`
- 多张合同图片批量导入

导入入口：

- 文本直接粘贴
- 文件上传
- 图片/PDF OCR 提取

### 2. 审查流水线

后端使用 LangGraph 编排多阶段审查流程：

1. `entity_extraction`
2. `routing`
3. `logic_review`
4. `breakpoint`
5. `aggregation`

其中：

- `entity_extraction`：提取出租方、承租方、租金、押金、期限等关键变量
- `routing`：决定优先走内置法律知识检索还是外部搜索
- `logic_review`：识别潜在不公平条款和风险点
- `breakpoint`：在需要人工确认时暂停
- `aggregation`：生成完整避坑指南报告

### 3. SSE 流式审查体验

前端通过 SSE 接收后端流式事件，实时刷新审查状态。

当前主要事件包括：

- `review_started`
- `entity_extraction`
- `routing`
- `rag_retrieval`
- `logic_review`
- `breakpoint`
- `stream_resume`
- `final_report`
- `review_complete`
- `error`

### 4. 人工确认断点

当系统识别到需要先确认的风险时，会在 `breakpoint` 阶段暂停。

用户可以：

- 结束当前流程
- 确认继续，生成完整避坑指南报告

### 5. 报告导出

支持将完整审查报告导出为 Word 文档：

- `POST /api/review/export-docx`

### 6. 条款自动修订建议

对于单条风险项，前端可调用自动修订接口生成更合理的条款建议：

- `POST /api/autofix`

### 7. 审查后问答

报告生成完成后，可基于：

- 合同原文节选
- 已识别风险摘要

继续进行问答追问：

- `POST /api/chat`

## 当前认证方式

### 主流程

- 手机号发送验证码：`POST /api/auth/phone/send-code`
- 手机号验证码登录：`POST /api/auth/phone/login`
- 绑定手机号：`POST /api/auth/phone/bind`

### 辅助流程

- 邮箱发送验证码：`POST /api/auth/send-code`
- 邮箱注册：`POST /api/auth/register`
- 邮箱密码登录：`POST /api/auth/login`

### 当前限制

- 未绑定手机号的账号不能使用完整合同审查
- `/api/review` 与 `/api/chat` 都要求用户已登录
- `/api/review` 进一步要求手机号已绑定并验证

## 项目结构

```text
Contract-Review-Copilot/
├─ backend/
│  ├─ src/
│  │  ├─ agents/              # 实体提取、路由、风险审查、断点、报告生成
│  │  ├─ graph/               # LangGraph 审查流程
│  │  ├─ ocr/                 # OCR 导入与文件解析
│  │  ├─ providers/           # 外部服务 Provider
│  │  ├─ search/              # DuckDuckGo 检索
│  │  ├─ vectorstore/         # pgvector / 内置法律知识
│  │  ├─ auth.py              # 登录、验证码、JWT
│  │  ├─ llm_client.py        # 单模型 LLM 调用入口
│  │  ├─ main.py              # FastAPI API 与 SSE
│  │  └─ schemas.py           # 请求响应模型
│  └─ tests/
├─ frontend/
│  ├─ src/
│  │  ├─ components/          # 审查面板、聊天面板、断点卡片等
│  │  ├─ contexts/            # AuthContext
│  │  ├─ hooks/               # useStreamingReview
│  │  ├─ lib/                 # SSE、历史记录、导出
│  │  ├─ pages/               # Login / Register / Settings
│  │  └─ App.tsx
├─ docs/
├─ docker-compose.yml
└─ README.md
```

## 本地开发

### 1. 启动依赖服务

如果你本地已经有 PostgreSQL 和 Redis，可直接复用；否则可用 Docker 单独起依赖。

### 2. 后端

```bash
cd backend
pip install -e .
uvicorn src.main:app --reload --port 8000
```

### 3. 前端

```bash
cd frontend
npm install
npm run dev
```

默认访问：

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend: [http://localhost:8000](http://localhost:8000)

## Docker

项目仍然保留完整的 Docker Compose 编排：

```bash
docker compose up --build
```

默认会启动：

- `frontend`
- `backend`
- `postgres`
- `redis`

## 环境变量

主要环境变量示例见：

- `backend/.env.example`

其中最核心的是：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `REVIEW_MODEL`
- `OCR_MODEL`
- `DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET` 或 `JWT_SECRET_FILE`
- `ALIYUN_SMS_*`

如果需要邮箱注册能力，还需要配置：

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `FROM_EMAIL`

## 测试

### Frontend

```bash
cd frontend
npm run test
```

### Backend

```bash
cd backend
pytest
```

## 当前公开 API 概览

### Auth

- `POST /api/auth/send-code`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/phone/send-code`
- `POST /api/auth/phone/login`
- `POST /api/auth/phone/bind`
- `GET /api/auth/me`

### Review / OCR / Chat

- `GET /health`
- `GET /api/models`
- `POST /api/ocr/ingest`
- `POST /api/ocr`
- `POST /api/ocr/extract`
- `POST /api/review`
- `POST /api/review/confirm/{session_id}`
- `POST /api/review/export-docx`
- `POST /api/autofix`
- `POST /api/chat`

## 开发说明

- 当前项目对外能力以 `backend/src/main.py` 与 `frontend/src/App.tsx` 实际接入为准
- README 只记录主流程已接通能力，不记录未接到前端或未暴露 API 的历史残留模块
- 若后续重新启用商业化、钱包或支付，请以实际接入状态为准补充文档
