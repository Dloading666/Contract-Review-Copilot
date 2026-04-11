# 合规智审 Copilot

<p align="center">
  <img src="docs/screenshots/logo.png" alt="合规智审 Copilot" width="120">
</p>

<p align="center">
  <strong>AI 智能合同审查助手 —— 让每一份租房合同都经得起推敲</strong>
</p>

<p align="center">
  <a href="https://ctsafe.top" target="_blank">
    <img src="https://img.shields.io/badge/🚀%20在线体验-ctsafe.top-00C853?style=for-the-badge" alt="在线体验">
  </a>
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
</p>

---

## 🎯 一句话介绍

**合规智审 Copilot** 是一款面向租房与消费合同场景的开源 AI 审查工具。上传合同，AI 自动识别风险条款、标注问题位置、生成避坑指南报告，帮你避开租房陷阱。

![首页截图](docs/screenshots/01-hero.png)

---

## ✨ 核心功能

<table>
<tr>
<td width="50%">

### 📄 多格式合同导入
- 支持 TXT / DOCX / PDF / 图片
- 多图批量上传 OCR 识别
- 云端 OCR 精准提取文字

</td>
<td width="50%">

### 🔍 多智能体审查流水线
- **实体提取**: 识别出租方、承租方、租金、押金等关键信息
- **风险扫描**: AI 自动检测不公平条款
- **法律依据**: 结合内置法律知识库 + 联网搜索
- **人工断点**: 关键风险需要确认后才继续

</td>
</tr>
<tr>
<td width="50%">

### ⚡ 流式实时反馈
- SSE 流式传输，审查进度实时可见
- 每个审查阶段都有可视化展示
- 支持追问 AI，深入理解风险条款

</td>
<td width="50%">

### 📊 专业报告导出
- 一键生成「避坑指南」报告
- 支持导出 Word 文档
- 条款自动修订建议

</td>
</tr>
</table>

---

## 🖼️ 界面预览

### 智能审查界面
AI 实时分析合同，标注风险位置，左侧展示审查进度和风险清单。

![审查界面](docs/screenshots/02-review.png)

> 上图展示了 AI 识别到「责任条款冲突」和「押金条款缺失」两类风险，并在右侧 PDF 中精确标注问题位置。

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (React 18)                       │
│  ┌────────────┐  ┌────────────┐  ┌──────────────────────┐   │
│  │ 合同上传   │  │ 流式展示   │  │ 风险交互 / 问答      │   │
│  └────────────┘  └────────────┘  └──────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │ SSE
┌──────────────────────────┴──────────────────────────────────┐
│                     后端 (FastAPI)                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              LangGraph 多智能体流水线                 │   │
│  │  ┌─────────┐   ┌─────────┐   ┌──────────┐           │   │
│  │  │ 实体提取 │ → │ 路由决策 │ → │ 风险审查  │           │   │
│  │  └─────────┘   └─────────┘   └──────────┘           │   │
│  │                                    ↓                 │   │
│  │  ┌─────────┐   ┌─────────┐   ┌──────────┐           │   │
│  │  │ 人工断点 │ ← │ 聚合报告 │ ← │ 逻辑审查  │           │   │
│  │  └─────────┘   └─────────┘   └──────────┘           │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ↓                  ↓                  ↓
   ┌─────────┐      ┌─────────┐       ┌──────────┐
   │PostgreSQL│      │  Redis  │       │Moonshot  │
   │+ pgvector│      │  缓存   │       │  Kimi API│
   └─────────┘      └─────────┘       └──────────┘
```

---

## 🚀 快速开始

### 在线体验

直接访问 **https://ctsafe.top** 免费使用，无需安装。

### 本地开发

#### 1. 克隆项目

```bash
git clone https://github.com/Dloading666/Contract-Review-Copilot.git
cd Contract-Review-Copilot
```

#### 2. 启动依赖服务

```bash
# 使用 Docker 启动 PostgreSQL + Redis
docker compose up -d postgres redis
```

#### 3. 启动后端

```bash
cd backend
pip install -e .
uvicorn src.main:app --reload --port 8000
```

#### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:3000

---

## ⚙️ 环境变量

创建 `backend/.env` 文件：

```env
# LLM API (Moonshot Kimi)
OPENAI_API_KEY=your-moonshot-api-key
OPENAI_BASE_URL=https://api.moonshot.cn/v1
REVIEW_MODEL=kimi-latest

# 数据库
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/contract_review
REDIS_URL=redis://localhost:6379/0

# 认证
JWT_SECRET=your-secret-key

# 阿里云短信（可选，用于手机号登录）
ALIYUN_SMS_ACCESS_KEY_ID=your-key
ALIYUN_SMS_ACCESS_KEY_SECRET=your-secret
ALIYUN_SMS_SIGN_NAME=你的签名
```

---

## 📁 项目结构

```
Contract-Review-Copilot/
├── backend/                    # Python FastAPI 后端
│   ├── src/
│   │   ├── agents/             # 多智能体模块
│   │   ├── graph/              # LangGraph 工作流
│   │   ├── vectorstore/        # PGVector 向量存储
│   │   ├── search/             # DuckDuckGo 搜索
│   │   ├── main.py             # FastAPI 入口
│   │   └── auth.py             # 用户认证
│   └── tests/                  # pytest 测试
├── frontend/                   # React + TypeScript 前端
│   ├── src/
│   │   ├── components/         # UI 组件
│   │   ├── hooks/              # 自定义 Hooks
│   │   └── pages/              # 页面组件
│   └── dist/                   # 构建输出
├── sample_contracts/           # 测试合同文件
└── docs/                       # 技术文档
```

---

## 🧪 测试

```bash
# 后端测试
cd backend
pytest

# 前端测试
cd frontend
npm run test
```

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + Vite 5 + TypeScript + Tailwind CSS |
| 后端 | Python 3.11 + FastAPI + LangGraph |
| LLM | Moonshot Kimi API |
| 向量检索 | PostgreSQL + pgvector |
| 缓存 | Redis |
| OCR | 云端 OCR 服务 |
| 搜索 | DuckDuckGo |

---

## 🤝 贡献指南

我们欢迎所有形式的贡献！

1. **Fork** 本仓库
2. 创建你的 **Feature Branch** (`git checkout -b feature/AmazingFeature`)
3. **Commit** 你的更改 (`git commit -m 'feat: add some AmazingFeature'`)
4. **Push** 到分支 (`git push origin feature/AmazingFeature`)
5. 打开 **Pull Request**

---

## 📜 License

本项目基于 [MIT License](LICENSE) 开源。

---

## 🙏 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) - 多智能体工作流编排
- [Moonshot AI](https://www.moonshot.cn/) - Kimi 大模型支持
- [FastAPI](https://fastapi.tiangolo.com/) - 高性能 Python Web 框架

---

<p align="center">
  <strong>如果觉得项目有帮助，请给我们点个 ⭐ Star！</strong>
</p>

<p align="center">
  <a href="https://ctsafe.top" target="_blank">在线体验</a> •
  <a href="https://github.com/Dloading666/Contract-Review-Copilot/issues">问题反馈</a> •
  <a href="https://github.com/Dloading666/Contract-Review-Copilot/discussions">社区讨论</a>
</p>
