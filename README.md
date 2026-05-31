# Contract Review Copilot

<p align="center">
  <img src="docs/screenshots/logo.png" alt="Contract Review Copilot" width="120">
</p>

<p align="center">
  <strong>An AI contract review assistant that helps rental agreements stand up to scrutiny.</strong>
</p>

<p align="center">
  <a href="https://ctsafe.top" target="_blank">
    <img src="https://img.shields.io/badge/Live%20Demo-ctsafe.top-00C853?style=for-the-badge" alt="Live Demo">
  </a>
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
</p>

<p align="center">
  <a href="README.zh-CN.md">Chinese README</a>
</p>

---

## One-line intro

**Contract Review Copilot** is an open-source AI review tool for rental and consumer contracts. Upload a contract, and the system extracts key facts, detects unfair clauses, highlights risky text, and generates a practical risk-avoidance report.

![Home screen](docs/screenshots/01-hero.png)

---

## Core features

<table>
<tr>
<td width="50%">

### Multi-format contract intake
- Supports TXT, DOCX, PDF, and image uploads.
- Handles batch image uploads with OCR.
- Uses cloud OCR to extract contract text accurately.

</td>
<td width="50%">

### Multi-agent review pipeline
- **Entity extraction**: identifies parties, rent, deposit, term, penalties, and other key facts.
- **Risk scanning**: detects unfair or high-risk clauses with AI.
- **Legal grounding**: combines an internal legal knowledge base with web search.
- **Human breakpoint**: pauses on important risks for user confirmation before continuing.

</td>
</tr>
<tr>
<td width="50%">

### Real-time streaming feedback
- Streams progress over SSE.
- Shows every review stage visually.
- Supports follow-up questions to help users understand clause risks.

</td>
<td width="50%">

### Professional report export
- Generates an "Avoid Pitfalls Guide" report.
- Supports Word document export.
- Provides suggested clause revisions.

</td>
</tr>
</table>

---

## UI preview

### Intelligent review workspace

The AI analyzes the contract in real time, highlights risky clauses, and shows review progress and risk cards in the left panel.

![Review workspace](docs/screenshots/02-review.png)

> The screenshot shows the system detecting issues such as conflicting liability terms and missing deposit clauses, then marking the relevant locations in the PDF viewer.

---

## Architecture

```text
+-------------------------------------------------------------+
|                      Frontend (React 18)                     |
|  +---------------+  +---------------+  +------------------+  |
|  | Contract input|  | Streamed flow |  | Risk chat / Q&A  |  |
|  +---------------+  +---------------+  +------------------+  |
+-----------------------------+-------------------------------+
                              | SSE
+-----------------------------+-------------------------------+
|                       Backend (FastAPI)                      |
|  +-------------------------------------------------------+   |
|  |              LangGraph multi-agent pipeline           |   |
|  |  +----------------+  +---------+  +---------------+   |   |
|  |  | Entity extract |->| Routing |->| Logic review  |   |   |
|  |  +----------------+  +---------+  +---------------+   |   |
|  |                                           |           |   |
|  |  +------------+  +-------------+  +---------------+   |   |
|  |  | Breakpoint |<-| Aggregation |<-| Review output |   |   |
|  |  +------------+  +-------------+  +---------------+   |   |
|  +-------------------------------------------------------+   |
+-----------------------------+-------------------------------+
                              |
           +------------------+------------------+
           |                  |                  |
           v                  v                  v
     +------------+      +---------+       +-------------+
     | PostgreSQL |      | Redis   |       | LLM API     |
     | + pgvector |      | cache   |       | review/OCR  |
     +------------+      +---------+       +-------------+
```

---

## Quick start

### Live demo

Visit **https://ctsafe.top** to try the app without installing anything.

### Local development

#### 1. Clone the repository

```bash
git clone https://github.com/Dloading666/Contract-Review-Copilot.git
cd Contract-Review-Copilot
```

#### 2. Start dependencies

```bash
# Start PostgreSQL and Redis with Docker
docker compose up -d postgres redis
```

#### 3. Start the backend

```bash
cd backend
pip install -e .
uvicorn src.main:app --reload --port 8000
```

#### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 in your browser.

---

## Environment variables

Create `backend/.env`:

```env
# LLM API
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=your-base-url
REVIEW_MODEL=model-name

# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/contract_review
REDIS_URL=redis://localhost:6379/0

# Auth
JWT_SECRET=your-secret-key

# Aliyun SMS, optional for phone login
ALIYUN_SMS_ACCESS_KEY_ID=your-key
ALIYUN_SMS_ACCESS_KEY_SECRET=your-secret
ALIYUN_SMS_SIGN_NAME=your-sign-name
```

---

## Project structure

```text
Contract-Review-Copilot/
├── backend/                    # Python FastAPI backend
│   ├── src/
│   │   ├── agents/             # Multi-agent modules
│   │   ├── graph/              # LangGraph workflow
│   │   ├── vectorstore/        # PGVector storage
│   │   ├── search/             # DuckDuckGo search
│   │   ├── main.py             # FastAPI entry point
│   │   └── auth.py             # Authentication
│   └── tests/                  # pytest tests
├── frontend/                   # React + TypeScript frontend
│   ├── src/
│   │   ├── components/         # UI components
│   │   ├── hooks/              # Custom hooks
│   │   └── pages/              # Page components
│   └── dist/                   # Build output
├── sample_contracts/           # Sample contract files
└── docs/                       # Technical documentation
```

---

## Tests

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm run test
```

---

## Tech stack

| Layer | Technology |
| ----- | ---------- |
| Frontend | React 18 + Vite 5 + TypeScript + Tailwind CSS |
| Backend | Python 3.11 + FastAPI + LangGraph |
| LLM | ZhipuAI / OpenAI-compatible LLM API |
| Vector search | PostgreSQL + pgvector |
| Cache | Redis |
| OCR | Cloud OCR service |
| Search | DuckDuckGo |

---

## Contributing

Contributions are welcome.

1. Fork this repository.
2. Create a feature branch: `git checkout -b feature/AmazingFeature`.
3. Commit your changes: `git commit -m "feat: add some AmazingFeature"`.
4. Push the branch: `git push origin feature/AmazingFeature`.
5. Open a pull request.

---

## License

This project is open-sourced under the [MIT License](LICENSE).

---

## Acknowledgements

- [LangGraph](https://github.com/langchain-ai/langgraph) for multi-agent workflow orchestration.
- [ZhipuAI](https://www.zhipuai.cn/) and OpenAI-compatible LLM providers for model support.
