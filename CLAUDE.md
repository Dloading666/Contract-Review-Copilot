# CLAUDE.md — Contract Review Copilot

> This project follows the Everything Claude Code (ECC) development conventions.

## Project Overview

- **Type**: Task-Oriented Agentic UI (任务导向型智能体交互界面)
- **Purpose**: AI-powered review of rental/consumer contracts for unfair clauses
- **Phase**: Phase 1 MVP — Frontend + FastAPI SSE + LangGraph (Mock data)

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18 + Vite 5 + TypeScript |
| Backend | FastAPI + Python 3.11 |
| AI Orchestration | LangGraph StateGraph |
| Storage | PostgreSQL + pgvector (Phase 2+) |
| Search | DuckDuckGo (free, no API key) |

## Key Conventions

### Naming
- TypeScript/JS: `camelCase` for files and functions
- Python: `snake_case` for files and functions
- Components: `PascalCase`

### Testing
- Frontend: Vitest (`*.test.ts`)
- Backend: pytest (`test_*.py`)
- Target: 80%+ coverage

### Commit Format (Conventional Commits)
```
feat: add entity extraction agent
fix: resolve SSE chunk boundary bug
docs: update API documentation
test: add breakpoint confirmation test
```

## Development Commands

```bash
# Frontend
cd frontend
npm install
npm run dev          # Dev server on :3000
npm run build        # Production build
npm run test         # Vitest unit tests

# Backend
cd backend
pip install -e .     # Install dependencies
uvicorn src.main:app --reload --port 8000

# Docker
docker compose up --build
```

## Architecture

### Agent Pipeline (LangGraph StateGraph)

```
contract_text
    ↓
[entity_extraction] → extracted_entities
    ↓
[routing] → routing_decision (pgvector vs duckduckgo)
    ↓
[logic_review] → logic_review_results
    ↓
[breakpoint] → needs_human_review (pause for human confirmation)
    ↓
[aggregation] → final_report (SSE streamed)
```

### SSE Event Types

| Event | Direction | Purpose |
|-------|-----------|---------|
| `review_started` | → Frontend | Review began |
| `entity_extraction` | → Frontend | Variables extracted |
| `routing` | → Frontend | Search strategy decided |
| `logic_review` | → Frontend | Per-clause risk found |
| `breakpoint` | → Frontend | Awaiting human confirmation |
| `stream_resume` | → Frontend | User confirmed, resume |
| `final_report` | → Frontend | Streaming report paragraphs |
| `review_complete` | → Frontend | Done |
| `error` | → Frontend | Error occurred |

## Files Quick Reference

```
backend/src/
├── main.py              # FastAPI app + SSE endpoint
├── schemas.py           # Pydantic request/response models
├── config.py            # Environment settings
├── agents/
│   ├── entity_extraction.py
│   ├── routing.py
│   ├── logic_review.py
│   ├── breakpoint.py
│   └── aggregation.py
└── graph/
    ├── state.py          # ReviewState TypedDict
    └── review_graph.py   # LangGraph StateGraph

frontend/src/
├── hooks/useStreamingReview.ts  # SSE client hook
├── components/
│   ├── ContractInput.tsx       # Textarea + file upload
│   ├── ReviewStream.tsx        # Container for agent cards
│   ├── AgentCard.tsx            # Individual agent result card
│   ├── BreakpointCard.tsx      # Human confirmation card
│   └── FinalReport.tsx         # Streaming report display
└── lib/sseClient.ts            # SSE fetch utility
```
