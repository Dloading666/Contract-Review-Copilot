# PostgreSQL + pgvector Quick Start

## What is included

This project now includes:

- a `postgres` service in `docker-compose.yml`
- automatic pgvector schema initialization
- optional built-in legal knowledge auto-seed
- a manual built-in seed command
- a local document import command for `.txt`, `.pdf`, `.doc`, and `.docx`

## Start the stack

```bash
docker compose up --build
```

This starts:

- `postgres` on `localhost:${POSTGRES_PORT:-5432}`
- `backend` on `localhost:8000`
- `frontend` on `localhost:3000`

## Schema initialization

The database schema is created automatically from:

```bash
backend/db/init/001_pgvector.sql
```

It creates:

- the `vector` extension
- the `contracts` table
- the `contract_chunks` table
- indexes for contract lookups and vector similarity search

## Optional built-in auto-seed

If you want Docker startup to ingest the repository's built-in legal knowledge, add this to `backend/.env`:

```bash
AUTO_SEED_LEGAL_KNOWLEDGE=1
```

If the optional seed fails, the backend still starts.

## Manual built-in seed

Using Docker:

```bash
docker compose exec -T backend python -m src.vectorstore.builtin_seed
```

Using a local Python environment:

```bash
cd backend
python -m src.vectorstore.builtin_seed
```

## Import your own legal documents

You do not need to collect your own legal corpus to get started. The built-in seed is enough to verify the pgvector retrieval path.

When you are ready, import your own local files:

Using Docker:

```bash
docker compose exec -T backend python -m src.vectorstore.import_documents /path/in/container
```

Using a local Python environment:

```bash
cd backend
python -m src.vectorstore.import_documents /path/to/legal-docs
```

Optional flags:

```bash
python -m src.vectorstore.import_documents /path/to/legal-docs --no-recursive --chunk-size 700 --overlap 80
```

## Notes

- `backend/.env` can keep `localhost` for local non-Docker development.
- Docker Compose overrides `DATABASE_URL` so the backend container talks to the `postgres` service.
- If you already created an older PostgreSQL volume with a different schema, recreate that volume before using this bootstrap path.
- The current Compose stack does not add Redis; if `REDIS_ENABLED=true`, cache operations may log connection errors but pgvector retrieval still falls back to direct database queries.
- If port `5432` is already occupied on your machine, run with a different host port, for example:

```powershell
$env:POSTGRES_PORT=5433
docker compose up --build
```
