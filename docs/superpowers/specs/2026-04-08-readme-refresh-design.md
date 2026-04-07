# README Refresh Design

## Goal

Replace the outdated root `README.md` with a current, developer-friendly project guide that matches the actual repository state.

## Audience

- Developers who need to run the project locally
- Reviewers who need a quick architecture and feature overview
- Collaborators who need to understand the current MVP scope and limitations

## Problems In The Current README

- The content is stale and does not describe the current frontend or backend flows.
- The documented project structure no longer matches the repository.
- Redis cache, JWT email login, pgvector bootstrapping, and model fallback are missing.
- The file contains visible encoding issues that make it hard to read.

## Recommended Approach

Rewrite the README from scratch instead of editing the old file in place.

This keeps the document coherent and avoids preserving stale assumptions or broken formatting.

## Proposed README Structure

1. Project overview
   - What the product does
   - Current status as an MVP/demo-oriented system
2. Feature summary
   - Contract upload and parsing
   - SSE review flow
   - Breakpoint confirmation
   - Autofix suggestions
   - Review history
   - JWT email verification login
   - Model fallback and Redis cache
3. Tech stack
4. Repository structure
5. Quick start
   - Frontend local run
   - Backend local run
   - Docker Compose run
6. Environment variables
   - Main LLM
   - Fallback LLM
   - Embeddings
   - Redis
   - Database
   - SMTP/JWT
7. Backend flow and SSE event types
8. Testing commands
9. Current limitations
10. Suggested next steps

## Content Rules

- Use clear Chinese prose with English names only where they help identify packages, endpoints, or files.
- Be explicit about what is implemented now versus what is still incomplete or environment-dependent.
- Do not promise that backend tests are currently runnable in every environment.
- Keep setup steps copy-paste friendly.
- Reflect the real repository layout, including `backend/src/cache`, `backend/src/search`, `backend/src/vectorstore`, and the frontend test files.

## Non-goals

- No marketing rewrite or brand repositioning.
- No API reference for every request field.
- No attempt to document unreleased future phases in detail.
