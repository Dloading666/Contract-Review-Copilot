<p align="center">
  <img src="docs/screenshots/logo.png" alt="合规智审 Copilot" width="100">
</p>

<h1 align="center">合规智审 Copilot</h1>

<p align="center">
  <strong>AI 驱动的租房合同智能审查助手 · 让每一份合同都经得起推敲</strong>
</p>

<p align="center">
  <a href="https://ctsafe.top" target="_blank">
    <img src="https://img.shields.io/badge/🚀%20在线体验-ctsafe.top-00C853?style=for-the-badge" alt="在线体验">
  </a>
  &nbsp;
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11">
  <img src="https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black" alt="React 18">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/LangGraph-Multi--Agent-FF6B35?style=for-the-badge" alt="LangGraph">
</p>

<p align="center">
  <img src="https://img.shields.io/github/license/Dloading666/Contract-Review-Copilot?style=flat-square" alt="License">
  <img src="https://img.shields.io/github/stars/Dloading666/Contract-Review-Copilot?style=flat-square" alt="Stars">
  <img src="https://img.shields.io/github/forks/Dloading666/Contract-Review-Copilot?style=flat-square" alt="Forks">
</p>

---

## 是什么

**合规智审 Copilot** 是一款面向租房与消费合同场景的开源 AI 审查工具。上传合同文件，多智能体流水线自动完成实体提取、风险扫描、法律依据检索，最终生成结构化「避坑指南」报告——帮你在签字之前就识别所有潜在陷阱。

**在线免费体验：[https://ctsafe.top](https://ctsafe.top)**

![首页截图](docs/screenshots/01-hero.png)

---

## 核心功能

| 功能 | 说明 |
|------|------|
| **多格式导入** | 支持 TXT / DOCX / PDF / 图片，多图批量上传 + 云端 OCR |
| **实体自动提取** | 识别出租方、承租方、租金、押金、违约金等关键要素 |
| **多智能体审查** | LangGraph 编排五阶段流水线，逐条分析风险条款 |
| **四级风险标注** | Critical / High / Medium / Low，精确定位问题位置 |
| **法律 RAG 检索** | pgvector 向量库 + DuckDuckGo 联网搜索双路法律依据 |
| **人工确认断点** | 高风险场景暂停流程，需人工确认后继续 |
| **流式实时反馈** | SSE 流式传输，每个审查阶段实时可见 |
| **AI 追问问答** | 针对任意风险条款追问 AI，深入理解合同含义 |
| **自动修订建议** | 一键生成条款修订建议文本 |
| **报告导出** | 导出结构化「避坑指南」Word 文档 |

---

## 界面预览

### 首页
![首页](docs/screenshots/01-hero.png)

### 智能审查界面
左侧实时展示审查进度与风险清单，右侧原文精确标注问题位置。

![审查界面](docs/screenshots/0768c8b4-77a9-483c-812f-e8f7e9d489a6.png)

---

## 系统架构

### 多智能体审查流水线

```
合同文本输入
     ↓
[实体提取 Agent] → 提取当事人、租金、押金、违约条款……
     ↓
[路由决策 Agent] → 选择 pgvector 语义检索 或 DuckDuckGo 联网搜索
     ↓
[逻辑审查 Agent] → 逐条扫描，输出风险项与法律依据
     ↓
[人工断点]       → ⏸ 暂停等待用户确认（高风险场景）
     ↓
[聚合报告 Agent] → SSE 流式输出结构化审查报告
```

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      前端 (React 18 + Vite)                  │
│   合同上传  │  流式审查展示  │  风险卡片  │  AI 问答面板       │
└──────────────────────────┬──────────────────────────────────┘
                           │ SSE / REST
┌──────────────────────────┴──────────────────────────────────┐
│                       后端 (FastAPI)                         │
│         LangGraph StateGraph 多智能体工作流                   │
└────────┬───────────────────┬──────────────────┬────────────┘
         ↓                   ↓                  ↓
   ┌──────────┐       ┌──────────┐       ┌──────────┐
   │PostgreSQL│       │  Redis   │       │  LLM API │
   │+pgvector │       │  缓存    │       │ (可配置)  │
   └──────────┘       └──────────┘       └──────────┘
```

---

## 技术栈

| 层级 | 技术选型 |
|------|---------|
| 前端 | React 18 · Vite 5 · TypeScript · Tailwind CSS |
| 后端 | Python 3.11 · FastAPI · LangGraph StateGraph |
| LLM | 可配置（支持 ZhipuAI GLM / SiliconFlow / OpenAI 兼容接口） |
| 向量嵌入 | ZhipuAI text-embedding-v4（1024 维） |
| 向量检索 | PostgreSQL + pgvector |
| Web 搜索 | DuckDuckGo（免费，无需 API Key） |
| 缓存 | Redis |
| OCR | 云端 OCR（图片合同识别） |
| 认证 | JWT + 邮箱验证码 |
| 部署 | Docker Compose |

---

## 快速开始

### 在线体验（推荐）

直接访问 **[https://ctsafe.top](https://ctsafe.top)** 免费使用，无需安装。

---

### 本地部署

#### 1. 克隆项目

```bash
git clone https://github.com/Dloading666/Contract-Review-Copilot.git
cd Contract-Review-Copilot
```

#### 2. 配置环境变量

创建 `backend/.env` 文件：

```env
# LLM API（OpenAI 兼容接口）
OPENAI_API_KEY=your-llm-api-key
OPENAI_BASE_URL=https://api.your-llm-provider.com/v1
OPENAI_MODEL=your-model-name

# 向量嵌入 API
EMBEDDING_API_KEY=your-embedding-api-key

# 数据库
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/contract_review
REDIS_URL=redis://localhost:6379/0

# 认证
JWT_SECRET=your-secret-key-here

# 邮件（可选，开发模式下验证码直接返回）
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USER=your@email.com
SMTP_PASSWORD=your-password
```

#### 3. Docker 一键启动（推荐）

```bash
docker compose up --build
```

访问 http://localhost:3000

#### 4. 手动启动（开发模式）

```bash
# 启动数据库依赖
docker compose up -d postgres redis

# 启动后端
cd backend
pip install -e .
uvicorn src.main:app --reload --port 8000

# 启动前端（新终端）
cd frontend
npm install
npm run dev
```

---

## 项目结构

```
Contract-Review-Copilot/
├── backend/
│   └── src/
│       ├── agents/              # 多智能体模块
│       │   ├── entity_extraction.py   # 实体提取
│       │   ├── routing.py             # 路由决策
│       │   ├── logic_review.py        # 风险审查
│       │   ├── breakpoint.py          # 人工断点
│       │   └── aggregation.py         # 报告聚合
│       ├── graph/               # LangGraph 工作流定义
│       ├── vectorstore/         # pgvector 向量存储
│       ├── search/              # DuckDuckGo 搜索
│       ├── cache/               # Redis 缓存
│       ├── main.py              # FastAPI 入口 + SSE 端点
│       └── auth.py              # JWT 认证
├── frontend/
│   └── src/
│       ├── components/          # UI 组件
│       ├── hooks/               # 自定义 Hooks（SSE 流式）
│       └── pages/               # 页面
├── docs/screenshots/            # 项目截图
├── docker-compose.yml
└── README.md
```

---

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/auth/send-code` | POST | 发送验证码 |
| `/api/auth/login` | POST | 验证登录，返回 JWT |
| `/api/review` | POST | 启动合同审查（SSE 流式返回） |
| `/api/review/confirm/{session_id}` | POST | 断点确认，恢复审查流程 |
| `/api/autofix` | POST | 生成条款修订建议 |

---

## 测试

```bash
# 后端单元测试
cd backend && pytest

# 前端单元测试
cd frontend && npm run test

# E2E 测试（Playwright）
npm run test:e2e
```

---

## 贡献

欢迎所有形式的贡献！

1. Fork 本仓库
2. 创建 Feature Branch：`git checkout -b feature/your-feature`
3. Commit 更改：`git commit -m 'feat: add your feature'`
4. Push：`git push origin feature/your-feature`
5. 发起 Pull Request

提交格式遵循 [Conventional Commits](https://www.conventionalcommits.org/)。

---

## License

本项目基于 [MIT License](LICENSE) 开源。

---

## 免责声明

> **重要提示：请在使用本工具前仔细阅读以下声明。**

1. **仅供参考，不构成法律意见**
   本工具由 AI 自动生成审查结果，所有输出内容（包括风险提示、条款分析、修订建议）均**仅供参考**，不构成任何形式的法律意见、法律建议或律师意见。AI 分析结果可能存在遗漏、误判或不适用于特定场景的情况。

2. **不替代专业法律咨询**
   对于涉及重大财产利益或复杂法律关系的合同，**强烈建议咨询持牌律师或专业法律人士**。本工具不能替代专业的法律服务。

3. **数据隐私**
   上传合同时，合同内容将通过网络发送至后端服务进行处理。请勿上传含有高度敏感个人信息的合同文本，或在上传前对敏感信息进行脱敏处理。本工具不对因数据泄露造成的损失承担责任。

4. **准确性限制**
   本工具基于 AI 大语言模型，受限于模型能力，可能存在幻觉、理解偏差等问题。法律法规随时间变化，本工具的知识库更新可能存在滞后。

5. **责任限制**
   在法律允许的最大范围内，本项目开发者不对因使用本工具产生的任何直接、间接、偶发、特殊或后果性损失承担责任，包括但不限于因信赖本工具输出内容而作出决策所导致的损失。

6. **使用即代表同意**
   使用本工具即表示您已阅读并同意上述免责声明。

---

## 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) — 多智能体工作流编排框架
- [FastAPI](https://fastapi.tiangolo.com/) — 高性能 Python Web 框架
- [pgvector](https://github.com/pgvector/pgvector) — PostgreSQL 向量扩展
- [DuckDuckGo Search](https://pypi.org/project/duckduckgo-search/) — 免费网络搜索

---

<p align="center">
  如果这个项目对你有帮助，请给一个 ⭐ Star 支持一下！
</p>

<p align="center">
  <a href="https://ctsafe.top">在线体验</a> ·
  <a href="https://github.com/Dloading666/Contract-Review-Copilot/issues">问题反馈</a> ·
  <a href="https://github.com/Dloading666/Contract-Review-Copilot/discussions">社区讨论</a>
</p>
