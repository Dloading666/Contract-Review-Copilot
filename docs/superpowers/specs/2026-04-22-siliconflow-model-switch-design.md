# SiliconFlow Model Switch Design

Date: 2026-04-22

## Goal

Switch the repository's primary contract-review model chain to SiliconFlow `deepseek-ai/DeepSeek-V3.2` with `Qwen/Qwen3.5-4B` as the fallback model, and reduce user-visible latency for follow-up chat replies without changing the product's existing review flow.

This design covers repository changes first. Deployment to the public server will happen only after the repository changes are implemented and verified locally.

## Current State

The current repository already routes review chat completions through SiliconFlow, but the configuration surface is inconsistent:

- `backend/src/config.py` defaults `primary_review_model` to `Qwen/Qwen3.5-4B` and `fallback_review_model` to `deepseek-ai/DeepSeek-V2.5`.
- `backend/src/llm_client.py` comments still describe an older OpenRouter-first chain that no longer matches runtime behavior.
- `/api/chat` uses the same review model chain as the contract-review pipeline, so conversational Q&A can be slowed down or fail when the main review model is slow.
- The repository currently relies on environment variables for runtime API keys, but source defaults and inline comments make the active provider/model story hard to trust.

Observed production symptom: the chat endpoint can return a timeout-based `503` when `Qwen/Qwen3.5-4B` is used as the first model in the shared review/chat chain.

## Chosen Approach

Use a split configuration model inside the repository:

1. Contract review and final report generation switch to:
   - Primary: `deepseek-ai/DeepSeek-V3.2`
   - Fallback: `Qwen/Qwen3.5-4B`
2. Conversational follow-up chat and OCR text correction stop inheriting the review chain by default.
3. A separate fast chat chain is introduced so the product can keep review quality higher while prioritizing quicker answers for interactive Q&A.

This keeps the user's requested review-model upgrade intact while avoiding the main usability regression caused by sharing one slow chain across review, report generation, and chat.

## Configuration Design

### Review chain

Add or normalize explicit repository settings for:

- `PRIMARY_REVIEW_MODEL`
- `FALLBACK_REVIEW_MODEL`

The repository defaults become:

- `PRIMARY_REVIEW_MODEL=deepseek-ai/DeepSeek-V3.2`
- `FALLBACK_REVIEW_MODEL=Qwen/Qwen3.5-4B`

These remain SiliconFlow-backed through the existing `OPENAI_API_KEY` and `OPENAI_BASE_URL` configuration path.

### Fast chat chain

Add a dedicated chat chain so `/api/chat` can use lower-latency defaults without altering the main review chain:

- `PRIMARY_CHAT_MODEL`
- `FALLBACK_CHAT_MODEL`

Repository defaults:

- `PRIMARY_CHAT_MODEL=Qwen/Qwen3.5-4B`
- `FALLBACK_CHAT_MODEL=deepseek-ai/DeepSeek-V3.2`

Rationale:

- Use the lighter model first for interactive replies.
- Fall back to the stronger model when the lighter one errors or times out.
- Keep the review/report path optimized for quality rather than first-token speed.

### OCR correction chain

`correct_ocr_text()` should use the dedicated chat chain instead of the review chain. OCR correction is an editing task with shorter outputs and does not need to consume the highest-cost review path by default.

### API key handling

No API key will be written into tracked source files. The repository will continue reading the SiliconFlow key from environment variables only.

## Runtime Behavior Changes

### `create_chat_completion()`

Refactor the shared LLM client so callers can request a model lane instead of always inheriting the review lane. Proposed lanes:

- `review`
- `chat`

Callers that do not specify a lane default to `review` to preserve current review behavior.

### `/api/chat`

Change `/api/chat` to request the `chat` lane explicitly. This isolates user Q&A from the heavier review defaults.

### OCR correction

Change `correct_ocr_text()` to request the `chat` lane explicitly.

### Review pipeline

Keep the existing contract-review pipeline, aggregation, and breakpoint flow on the `review` lane.

## Speed Optimizations

### Faster fallback for chat

Interactive chat should use a shorter timeout than the main review/report flow. The target behavior is:

- Chat times out faster than review generation.
- On timeout, chat falls through immediately to the fallback model.
- The user receives either a real reply or a concise degraded fallback instead of waiting on a long hanging request.

### Lower output ceiling for chat

Reduce chat `max_tokens` from its current report-like ceiling to a Q&A-oriented ceiling so the model is less likely to over-generate.

This keeps answers focused and usually improves first-byte and total response time.

### Keep Qwen thinking disabled

Retain the existing `enable_thinking=false` fast-path behavior for applicable Qwen models. This is already implemented in the client and should remain active for the chat lane.

### Keep context bounded

Do not expand chat context beyond the current contract excerpt and risk summary. The goal is to avoid repeatedly sending the full contract body when not necessary.

This design does not add vector retrieval or long-context memory to chat.

## Documentation Cleanup

Update repository comments and configuration descriptions so they match actual runtime behavior:

- `backend/src/config.py`
- `backend/src/llm_client.py`
- any sample env or local docs that still describe the older provider/model chain

The goal is to remove misleading OpenRouter-first commentary from the review path if the repository is now SiliconFlow-first.

## Testing Plan

### Local verification

- Confirm config resolution returns the new review defaults.
- Confirm `/api/chat` requests the chat lane instead of the review lane.
- Confirm OCR correction requests the chat lane instead of the review lane.
- Confirm review generation still requests the review lane.
- Run backend syntax validation for changed Python files.
- Run frontend production build if any client-side labels or behavior need adjustment.

### Manual behavior checks

- Ask a short follow-up question after a completed review and confirm the backend reports the chat lane's primary or fallback model.
- Trigger a simulated primary chat failure and confirm fallback to the secondary chat model.
- Verify review/report generation still uses `DeepSeek-V3.2` first.

## Out of Scope

- Rotating or replacing the live production API key.
- Changing the public server in this design phase.
- Adding streaming chat responses.
- Changing OCR image model selection.
- Reworking the review prompts themselves.

## Implementation Notes

- Favor environment-variable-driven defaults over hardcoded secrets.
- Preserve backward compatibility for callers that currently rely on `create_chat_completion()` without a lane argument.
- Keep the diff focused on configuration, call-site routing, and timeout/token tuning.

## Risks

### Model availability risk

If SiliconFlow does not support `deepseek-ai/DeepSeek-V3.2` under the exact requested identifier in the current account/region, review calls will fail until the identifier is corrected. Implementation should keep the fallback chain intact and make the effective model visible in logs.

### Behavioral drift risk

Splitting review and chat lanes may slightly change OCR correction phrasing and chat answer style. This is acceptable as long as outputs remain concise and contract-grounded.

### Configuration drift risk

If defaults are changed in code but not mirrored in sample env usage, future deployments may still run the old chain. The implementation should update both code defaults and any repository-level env examples that define these models.

## Rollout

1. Update repository config defaults and lane-aware model resolution.
2. Verify locally.
3. Push repository changes.
4. Update the server environment and restart backend services.
5. Run a public smoke test for chat and full review flow.

