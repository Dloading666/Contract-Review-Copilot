# Contract Review Copilot Repair Pass

## Scope

This repair pass fixes the current contract review flow end to end without expanding the product into a new standalone assistant. The goal is to make the existing MVP coherent, protected, testable, and demonstrably usable.

## Backend

- Replace the hand-wired review pipeline with a real LangGraph `StateGraph` for the review phase and a second `StateGraph` for report aggregation.
- Keep the existing SSE contract stable so the frontend does not need to change event names.
- Inject legal retrieval context into the logic review prompt so pgvector and DuckDuckGo results can affect model output.
- Enforce JWT authentication on review-related endpoints, including review start, resume, and autofix.
- Add missing runtime dependencies used by the codebase.

## Frontend

- Reuse the shared `sseClient` inside `useStreamingReview` instead of duplicating stream parsing logic.
- Pass auth headers on review and autofix requests.
- Make review state restorable from history snapshots instead of only storing filenames.
- Turn the chat box into a working review-side assistant that answers from the current review data.
- Add a working sample-contract action in the upload area.

## Testing

- Configure Vitest with `jsdom`.
- Fix the existing hook tests to match the real SSE payload shape.
- Add component tests for the main interaction surface.
- Add backend pytest coverage for the graph flow, auth protection, and prompt wiring.

## Non-goals

- No new persistence layer for review history beyond browser storage.
- No separate backend chat endpoint in this pass.
- No redesign of the existing UI language or layout.
