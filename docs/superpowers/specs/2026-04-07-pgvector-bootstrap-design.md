# PostgreSQL and pgvector Bootstrap

## Scope

This change adds an optional but production-like PostgreSQL + pgvector path to the MVP without making the database mandatory for basic frontend and backend startup. The goal is to let `docker compose up --build` start a usable stack, initialize vector storage, and support both built-in legal knowledge seeding and later local document imports.

## Services

- Add a `postgres` service to `docker-compose.yml` using a pgvector-enabled PostgreSQL image.
- Expose port `5432`, persist data with a named volume, and configure a healthcheck so the backend starts only after the database is ready.
- Override the backend container `DATABASE_URL` to use the Compose service hostname instead of `localhost`.

## Database Initialization

- Add an initialization SQL file mounted into `/docker-entrypoint-initdb.d/`.
- Enable the `vector` extension.
- Create `contracts` and `contract_chunks` tables plus the indexes required for contract lookups and cosine-similarity retrieval.
- Store chunk `metadata` in the database so RAG results can surface document titles instead of anonymous text chunks.
- Make the schema compatible with idempotent seed/import operations by introducing a stable `source_key` on contracts.

## Seeding and Imports

- Keep startup stable by separating schema creation from knowledge ingestion.
- Add a backend bootstrap script that can optionally seed the built-in legal knowledge after the database becomes reachable, controlled by an environment variable.
- Make built-in seeding idempotent so repeated runs do not duplicate the same knowledge base.
- Add a CLI import script for local `.txt`, `.pdf`, `.doc`, and `.docx` files. Imported documents are chunked, embedded, and stored under a deterministic `source_key` derived from the file path.

## Runtime Behavior

- Default behavior: database starts, schema initializes, backend starts, and no seed runs unless explicitly enabled.
- Optional behavior: set `AUTO_SEED_LEGAL_KNOWLEDGE=1` to ingest the repository's built-in legal knowledge on startup.
- Manual imports remain available even if auto-seed is disabled.
- If optional seeding fails, the backend should still start and log the error instead of blocking the whole stack.

## Documentation and Usage

- Update README with the local startup path, database container details, and commands for:
  - starting the stack,
  - enabling auto-seed,
  - running the built-in seed manually,
  - importing a local legal document directory.

## Non-goals

- No attempt to make PostgreSQL mandatory for Phase 1 demo usage.
- No new admin UI for database management.
- No large-scale legal corpus curation in this pass; the built-in seed only serves as a starter knowledge base.
