# 合同避坑审查员 (Contract Review Copilot)

AI 智能审查租房/消费合同中的霸王条款，基于 LangGraph 多智能体编排。

## 技术栈

- **前端**: React 18 + Vite 5 + TypeScript
- **后端**: FastAPI + LangGraph + Python 3.11
- **存储**: PostgreSQL + pgvector (Phase 2+)
- **部署**: Docker Compose

## 快速开始

### 本地开发

```bash
# 前端
cd frontend
npm install
npm run dev

# 后端 (新终端)
cd backend
pip install -e .
uvicorn src.main:app --reload --port 8000
```

访问 http://localhost:3000

### Docker Compose

```bash
docker compose up --build
```

## 项目结构

```
contract-review-copilot/
├── frontend/          # React + Vite 前端
├── backend/           # FastAPI 后端
├── evaluation/        # 评测模块
├── docker-compose.yml
└── README.md
```

## 开发规范

遵循 ECC (Everything Claude Code) 开发规范：
- Conventional Commits
- camelCase (TS) / snake_case (Python)
- 80%+ 测试覆盖率
