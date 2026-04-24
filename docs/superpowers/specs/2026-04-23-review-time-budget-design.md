# 40-Second Initial Review Time Budget Design

Date: 2026-04-23
Status: Draft for review
Owner: Codex

## Goal

The contract review flow must show users actionable results within about 40 seconds, even on slow model responses.

The required user-visible output inside the 40-second budget is:

- initial risk cards
- an initial review summary

The system does not need to finish the full polished final report inside 40 seconds. Deep analysis may continue in the background and update the current page in place.

## Product Decision

The review experience will become a two-stage flow:

1. Fast review stage
   Delivers initial risk cards and an initial conclusion inside a hard time budget.
2. Deep completion stage
   Continues running after the initial result is shown, then enriches the same page with deeper analysis and the full report.

The page must not do a full refresh. Deep results update the current review session in place.

## User Experience

### Initial stage

Within about 40 seconds, the user sees:

- extracted key facts if available
- initial risk cards
- an initial conclusion banner or summary block
- a status message such as "Initial review ready, deep analysis is still running"

If the model finishes quickly, the initial result can contain both rule-based and model-enhanced findings. If the model is slow, the initial result must still be published using the rule engine and any completed upstream results.

### Deep stage

After the initial result is visible, the backend continues processing and the frontend updates in place:

- newly discovered risks receive a `新增` style badge
- risks whose severity increases receive a `已升级` style badge
- the summary status changes from `初步审查结果` to `深度审查已完成`
- a lightweight toast or inline notice announces deep completion, for example `已补充 2 条深度分析结果`

The UI must not:

- reload the page
- reset scroll position
- clear existing cards
- reorder existing cards unexpectedly

## Scope

This design applies to the main contract review pipeline:

- entity extraction
- routing and retrieval
- logic review
- breakpoint handoff
- final aggregation/report generation

This design does not change post-review chat behavior except that chat should continue to read the latest enriched review state after deep completion.

## Model Policy

For the contract review pipeline, remove `Qwen/Qwen3.5-4B` as the fallback review model.

The review path should use:

- primary review model: `deepseek-ai/DeepSeek-V3.2`
- no slow fallback review model

Reason:

- the fallback path adds long-tail latency and makes the 40-second budget hard to guarantee
- the rule engine is a better deterministic fallback for initial review than a second slower LLM lane

If DeepSeek fails or times out during the initial stage, the system must fall back to rule-based review and still publish the initial result on time.

## Time Budget

Use a hard deadline for the initial stage. Recommended server-side budget:

- total initial review deadline: 38 seconds
- UI/network buffer: about 2 seconds

Recommended internal budgets:

- entity extraction: up to 8 seconds
- routing and retrieval: up to 4 seconds
- initial logic review: up to 20 seconds
- result assembly and SSE flush: remaining budget

These budgets are ceilings, not targets. Fast completions should publish immediately.

## Review Architecture

### Fast path

The fast path must always run:

- rule-based entity extraction fallback capability
- rule-based clause review
- minimal retrieval if it completes inside budget
- DeepSeek-enhanced extraction/review only if it finishes before the deadline

The initial result is assembled from the best available completed work before the deadline expires.

### Deep path

The deep path starts from the same review session state and continues after the initial result is sent:

- complete longer LLM review if not finished yet
- complete richer retrieval context if still pending
- generate the full final report
- produce diff metadata describing newly added or upgraded findings

The deep path writes back into the review session state and emits additional SSE events for in-place UI updates.

## Backend Design

### 1. Review deadline controller

Add a review deadline controller that starts when `/api/review/stream` begins.

Responsibilities:

- tracks elapsed time for the initial stage
- stops waiting for slow optional work when the deadline is reached
- assembles and publishes the initial result from completed work
- keeps any safe background work running for deep completion

### 2. Fast review result schema

Extend session state with two result layers:

- `initial_review_results`
- `deep_review_results`

And add metadata:

- `review_stage`: `initial` or `deep`
- `initial_ready_at`
- `deep_completed_at`
- `finding_changes`: list of `new` or `upgraded` changes

### 3. Logic review split

Split logic review into:

- `rule_review_clauses(contract_text)`:
  deterministic and fast, used as guaranteed baseline
- `model_review_clauses(...)`:
  DeepSeek-driven, budget-aware, optional for initial stage if it returns in time

Merge behavior:

- if model review completes before deadline, merge model findings with rule findings
- if model review does not complete, publish rule findings immediately
- later, when model review finishes in deep stage, merge and diff against what the user already saw

### 4. Remove second-pass JSON retry for initial stage

The current LLM review retries once when JSON parsing fails. For the initial stage, this retry should be disabled or guarded by remaining budget.

Rule:

- if there is not enough remaining budget, skip retry and use rule results

### 5. Remove artificial sleeps in review SSE

The current review graph stream adds deliberate sleeps between stages and issues. Those sleeps materially increase user wait time and must be removed or reduced to near-zero in the initial stage.

This is required to make the 40-second target realistic without lowering accuracy.

### 6. Deep completion worker

After initial publication, continue deep processing asynchronously for the same session.

Acceptable implementation options:

- background `asyncio` task tied to the process
- queue-backed worker if the current queue service is already suitable

For this implementation cycle, prefer the simplest in-process background continuation that reuses the existing paused/session state model.

## SSE/Event Design

Keep existing review events where practical, but add explicit stage events:

- `initial_review_ready`
- `deep_review_started`
- `deep_review_update`
- `deep_review_complete`

Payload expectations:

- `initial_review_ready`
  includes initial risk cards, initial summary, and `review_stage=initial`
- `deep_review_update`
  includes only changed or newly available findings plus change metadata
- `deep_review_complete`
  includes final enriched review state and completion summary

The initial stage must not wait for aggregation. Aggregation belongs to deep completion unless it already finished within budget.

## Frontend Design

### Review state

Extend frontend review state with:

- `reviewStage`
- `deepUpdateNotice`
- per-card `changeType`: `new`, `upgraded`, or `none`

### Rendering rules

- show the initial risk cards immediately when `initial_review_ready` arrives
- keep the contract viewer and current scroll position unchanged
- append or enrich cards in place when deep updates arrive
- display a small inline notice or toast on deep completion

### Messaging

Suggested wording:

- initial stage: `初步审查结果已生成，正在补全深度分析...`
- deep completion: `深度审查已完成，已补充 N 条分析结果`

## Accuracy Strategy

The fast stage should prioritize catching high-impact, decision-changing issues first:

- deposit not returned
- excessive penalties
- unilateral termination
- auto-renewal traps
- utility shutoff/self-help clauses
- sublease or authorization risk

The deep stage can then improve:

- medium and low-risk coverage
- explanation quality
- legal reference richness
- final report polish

This preserves decision-useful accuracy while meeting the time target.

## Failure Handling

### If DeepSeek times out in initial stage

- publish rule-based initial risk cards
- mark the result as `initial`
- continue deep stage only if useful and safe

### If deep completion fails

- keep the initial result visible
- show a small non-blocking notice such as `深度分析暂未补全，当前显示的是初步结果`

### If no substantive issue is found

- still publish an initial no-risk conclusion inside the deadline
- deep stage may still refine supporting explanation

## Testing

### Backend

Add tests for:

- initial result published before deep completion
- deadline expiration falls back to rule results
- no fallback routing to Qwen review model
- deep completion emits diff metadata for new and upgraded findings
- removed or reduced artificial sleeps do not break event order

### Frontend

Add tests for:

- initial results render without full-page reset
- deep updates patch cards in place
- new and upgraded badges render correctly
- lightweight completion notice appears once deep results arrive

## Rollout

Implementation should happen in this order:

1. remove review fallback model usage and trim initial-stage waits
2. split initial and deep review state/event flow
3. update frontend to render initial and deep stages separately
4. add timing-focused tests and verify a representative contract reaches initial output in about 40 seconds

## Open Choices Resolved

The following decisions are fixed for implementation:

- no full-page auto refresh
- deep results auto-update in place
- only a lightweight user notice on deep completion
- initial result inside 40 seconds is mandatory
- full report may complete later
- review fallback model is removed in favor of rule-based fallback
