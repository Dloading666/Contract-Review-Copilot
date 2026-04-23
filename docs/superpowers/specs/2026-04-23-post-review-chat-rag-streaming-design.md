# Post-Review Chat RAG Streaming Design

Date: 2026-04-23
Status: Draft for implementation approval

## Goal

Upgrade the post-review chat experience so that follow-up Q&A after a contract review can:

1. retrieve stronger supporting evidence with backend-only query rewriting
2. combine local `pgvector` recall with external legal search and general web search
3. answer with true streaming output instead of waiting for the full completion
4. use `deepseek-ai/DeepSeek-V3.2` as the only chat-answer model
5. show explicit source references after the streamed answer finishes

This change applies only to the interactive chat that happens after contract review. It does not change the main contract-review pipeline prompts, issue extraction, or report generation flow.

## Product Decisions

### Confirmed decisions

- Query rewriting is backend-only and must not change the user-visible question.
- Retrieval order is staged:
  1. `pgvector`
  2. targeted legal search
  3. general web search
- Later stages are used only when earlier stages are insufficient.
- Retrieval completes first; answer streaming starts only after evidence assembly is done.
- Chat answering uses only `deepseek-ai/DeepSeek-V3.2`.
- The final assistant message includes a source section with:
  - law or regulation names
  - page titles
  - links

### User experience

When the user asks a follow-up question in the chat panel:

1. the UI immediately shows a pending assistant message and a retrieval status
2. the backend performs query rewrite and staged retrieval
3. once retrieval is complete, the answer begins streaming token-by-token
4. when streaming finishes, the same message shows a `References` section below the answer body

The user should never see rewritten queries or internal retrieval diagnostics in the normal chat transcript.

## Current State

### Backend chat

Current [`/api/chat`](/D:/agent%20project/Contract-Review-Copilot/backend/src/main.py) is non-streaming and only sends:

- the user question
- a contract-text excerpt
- a risk-summary excerpt

to the chat model. It does not have a dedicated retrieval orchestration stage for follow-up chat.

### Search

Current search utilities in [duckduckgo.py](/D:/agent%20project/Contract-Review-Copilot/backend/src/search/duckduckgo.py) are effectively disabled and return empty results. The existing project therefore has:

- local `pgvector` retrieval available in [store.py](/D:/agent%20project/Contract-Review-Copilot/backend/src/vectorstore/store.py)
- no real live legal or general web search in the current chat path

### Frontend chat

Current [ChatPanel.tsx](/D:/agent%20project/Contract-Review-Copilot/frontend/src/components/ChatPanel.tsx) submits a normal POST request and replaces a placeholder bubble after the full response returns. It does not consume SSE for chat tokens or render structured source lists for chat replies.

## Proposed Architecture

Add a dedicated post-review chat retrieval-and-streaming layer.

### New backend responsibilities

Introduce a chat retrieval orchestrator module responsible for:

1. query rewrite generation
2. staged retrieval
3. retrieval sufficiency checks
4. result deduplication and reranking
5. evidence-pack assembly for the answer model
6. structured source output for the frontend

### Suggested module boundaries

- `backend/src/chat_retrieval/query_rewrite.py`
  - generate backend-only rewritten queries
- `backend/src/chat_retrieval/retrieval.py`
  - stage `pgvector`, targeted legal search, and general web search
- `backend/src/chat_retrieval/rerank.py`
  - deduplicate and score evidence items
- `backend/src/chat_retrieval/evidence.py`
  - format evidence pack and final source metadata

Exact filenames may vary, but the logic should remain separated by responsibility.

## Query Rewrite Design

### Purpose

Improve recall without distorting the user's intent.

### Rules

- Always retain the original user question as the highest-priority query.
- Generate `2-4` additional rewritten queries.
- Rewrites may use only:
  - user question
  - contract excerpt or summary
  - identified risk cards or risk summary
  - contract type or legal focus already inferred by the review pipeline
- Rewrites must not introduce unrelated legal topics.
- Rewrites are for retrieval only and must never be displayed in the UI.

### Rewrite perspectives

Each rewrite should fall into one of these controlled perspectives:

- clause or risk wording
- legal basis wording
- remedy or negotiation wording
- regional or scenario wording, only when explicitly supported by the review context

### Example

If the user asks:

`Is this non-refundable deposit clause reasonable?`

possible backend queries may look like:

- original: `Is this non-refundable deposit clause reasonable`
- clause-focused: `non refundable deposit rental contract clause`
- legal-focused: `Civil Code deposit return standard form clause`
- remedy-focused: `non refundable deposit clause revision suggestion`

The frontend still displays only the original user message.

## Retrieval Strategy

### Stage 1: pgvector

Use the original question plus rewritten legal-focused queries to search the local legal knowledge base first.

Expected value:

- lowest latency
- strongest consistency with the project's seeded legal knowledge
- best for common rental and consumer-contract issues

### Stage 2: targeted legal search

If local recall is insufficient, query targeted legal sources next.

Targeted legal search should prefer official or law-focused sources such as:

- government or judicial sites
- official regulation repositories
- authoritative legal-information portals

This stage is intended to find:

- statutory text
- judicial interpretations
- local regulatory guidance
- high-quality legal explainers

### Stage 3: general web search

If the first two stages still do not provide enough coverage, use broader web search.

This stage is intended to supplement:

- recent interpretations
- public explainers
- industry practice articles
- contextual references not present in local or targeted legal sources

General web results must be filtered more aggressively than legal-source results.

## Sufficiency Rules

Escalation to the next retrieval stage should not rely on a single threshold.

Move from `pgvector` to targeted legal search when one or more of the following are true:

- too few local hits
- low top-hit similarity
- high duplication among local hits
- local hits fail to cover the user's main risk topic
- the user asks for locality, recency, case practice, or policy nuances

Move from targeted legal search to general web search when:

- targeted legal results are still sparse
- results do not cover the user question's angle
- the question explicitly implies practical or recent interpretation

## Evidence Assembly and Reranking

Combine all retrieved items into a single evidence pack with source metadata.

### Evidence item shape

Each candidate item should normalize into something like:

- `source_type`
  - `pgvector`
  - `legal_search`
  - `web_search`
- `title`
- `snippet`
- `url`
- `authority_score`
- `relevance_score`
- `dedupe_key`
- `law_name` or `regulation_name` when available

### Reranking priorities

Prefer evidence that is:

1. directly relevant to the user question
2. directly connected to the reviewed contract's identified risks
3. authoritative
4. non-duplicative
5. concise enough to fit the answer prompt budget

The final evidence pack should contain only a small, high-confidence set of items. Do not pass large raw search dumps to the model.

## Chat Answer Generation

### Model

Use only `deepseek-ai/DeepSeek-V3.2` for post-review chat answers.

The chat lane should no longer use a fallback model for this new retrieval-backed answer flow.

### Prompt structure

The answer prompt should include:

- user question
- reviewed contract excerpt or summary
- identified risks
- assembled evidence pack
- response-format instructions

### Response requirements

The model should:

- answer directly
- explain the risk and impact
- give actionable contract or negotiation advice
- clearly distinguish stronger legal basis from weaker web references when needed
- avoid claiming certainty when evidence is thin

## Streaming Design

### API shape

Add a new streaming endpoint rather than replacing the existing synchronous endpoint immediately.

Recommended endpoint:

- `POST /api/chat/stream`

Rationale:

- keeps `/api/chat` available as a compatibility fallback
- minimizes regression risk
- makes the streaming contract explicit

### SSE event sequence

Recommended event flow:

1. `chat_retrieval_started`
2. `chat_retrieval_stage`
3. `chat_retrieval_complete`
4. `chat_token`
5. `chat_sources`
6. `chat_complete`
7. `error`

### Event payload intent

- `chat_retrieval_started`
  - indicates retrieval has begun
- `chat_retrieval_stage`
  - optional lightweight status for `pgvector`, legal search, or web search
- `chat_retrieval_complete`
  - indicates answer generation is about to start
- `chat_token`
  - incremental answer text chunks
- `chat_sources`
  - final structured sources block
- `chat_complete`
  - marks end of stream

The frontend should not expose all internal diagnostics. Retrieval-stage events can map to short user-facing status text like `retrieving supporting materials...`.

## Frontend Changes

### ChatPanel behavior

Upgrade [ChatPanel.tsx](/D:/agent%20project/Contract-Review-Copilot/frontend/src/components/ChatPanel.tsx) to:

- send follow-up questions to `/api/chat/stream`
- create a pending assistant bubble immediately
- show retrieval status before tokens arrive
- append streamed answer chunks into the same assistant bubble
- attach `References` after the answer body completes

### Message model

Extend chat message state to support:

- `status`
  - `retrieving`
  - `streaming`
  - `complete`
  - `error`
- partial assistant content
- structured source list

### Source rendering

After answer streaming completes, render a bottom section such as:

- `References`
- regulations first
- web references second

Each source entry should show:

- regulation name or title
- optional site name
- clickable URL when available

## Failure and Degradation Behavior

### Retrieval degradation

- If `pgvector` fails, continue to external retrieval.
- If targeted legal search fails, continue to general web search.
- If all external retrieval fails, answer from contract context plus risk summary and explicitly state that outside evidence is limited.

### Model degradation

If `DeepSeek-V3.2` fails during chat:

- keep the existing partial streamed content if any
- mark the assistant message as interrupted
- allow the user to retry

### Source degradation

If an answer is produced with only local evidence:

- show only regulation or local-source references

If answer evidence is weak:

- add a visible caveat in the answer body

## Data Contracts

### Request

Extend the existing chat request payload or create a streaming equivalent that includes:

- `message`
- `contract_text`
- `risk_summary`
- `review_session_id`

No query rewrite fields are exposed to the client.

### Final source payload

The source payload should be structured JSON, not pre-rendered markdown, so the frontend can render it cleanly.

Suggested shape:

```json
{
  "sources": [
    {
      "category": "regulation",
      "title": "Civil Code Article 497",
      "site_name": "National Law Database",
      "url": "https://...",
      "snippet": "..."
    },
    {
      "category": "web",
      "title": "Deposit Clause Risk Analysis",
      "site_name": "Example Legal Site",
      "url": "https://...",
      "snippet": "..."
    }
  ]
}
```

## Configuration

Add explicit settings for the new chat retrieval path.

Suggested settings:

- `CHAT_STREAM_MODEL`
- `CHAT_QUERY_REWRITE_COUNT`
- `CHAT_PGVECTOR_TOP_K`
- `CHAT_PGVECTOR_MIN_SIMILARITY`
- `CHAT_TARGETED_SEARCH_TOP_K`
- `CHAT_WEB_SEARCH_TOP_K`
- `CHAT_MAX_EVIDENCE_ITEMS`
- `CHAT_ENABLE_TARGETED_SEARCH`
- `CHAT_ENABLE_WEB_SEARCH`

`CHAT_STREAM_MODEL` should default to `deepseek-ai/DeepSeek-V3.2`.

## Testing Scope

### Backend tests

Add tests for:

- rewrite output count and structure
- sufficiency escalation logic
- retrieval result normalization
- deduplication and reranking
- `/api/chat/stream` SSE event ordering
- degradation when one or more retrieval stages fail

### Frontend tests

Add tests for:

- pending assistant state during retrieval
- token-by-token streaming rendering
- final source block rendering
- interrupted stream behavior
- retry behavior after chat error

## Rollout Plan

### Phase 1

- add backend retrieval orchestration
- add streaming endpoint
- keep old `/api/chat` unchanged

### Phase 2

- switch frontend chat to the new streaming endpoint
- render sources

### Phase 3

- evaluate whether the old `/api/chat` can remain as fallback or internal smoke-test path

## Out of Scope

This design does not include:

- changing the main review graph
- changing the report generation flow
- exposing rewritten queries to users
- adding multi-model chat fallback
- making retrieval itself stream to the UI token-by-token before evidence is ready

## Risks

### Latency risk

Adding staged external retrieval will increase time-to-first-token. This is accepted because the user explicitly prefers retrieval to finish before streaming begins.

### Noise risk

General web search can introduce low-quality pages. This is why the design keeps it last, applies reranking, and requires explicit source display.

### Complexity risk

Mixing local, legal, and web retrieval into one answer path can sprawl if boundaries are not enforced. Retrieval orchestration, reranking, and rendering should remain separate units.

## Recommendation

Implement the new post-review chat path with:

- backend-only query rewriting
- staged retrieval with sufficiency checks
- `DeepSeek-V3.2` as the sole answer model
- a new `/api/chat/stream` SSE endpoint
- explicit source rendering in the chat UI

This gives the project a stronger answer quality ceiling without weakening answer traceability or user trust.
