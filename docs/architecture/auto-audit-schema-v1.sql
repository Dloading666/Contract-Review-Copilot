CREATE TABLE IF NOT EXISTS audit_runs (
    id BIGSERIAL PRIMARY KEY,
    trigger_type TEXT NOT NULL,
    environment TEXT NOT NULL,
    git_sha TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    overall_score INTEGER NOT NULL,
    release_decision TEXT NOT NULL,
    summary JSONB NOT NULL DEFAULT '[]'::jsonb,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS audit_scores (
    run_id BIGINT PRIMARY KEY REFERENCES audit_runs(id) ON DELETE CASCADE,
    concurrency_performance_score INTEGER NOT NULL,
    async_decoupling_score INTEGER NOT NULL,
    content_safety_score INTEGER NOT NULL,
    storage_architecture_score INTEGER NOT NULL,
    large_file_handling_score INTEGER NOT NULL,
    anti_bot_registration_score INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_findings (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
    finding_key TEXT NOT NULL,
    dimension TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    impact TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    acceptance_criteria TEXT NOT NULL,
    owner_hint TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_metrics (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
    metric_name TEXT NOT NULL,
    metric_value NUMERIC,
    metric_unit TEXT,
    target_value NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS optimization_tasks (
    id BIGSERIAL PRIMARY KEY,
    finding_id BIGINT NOT NULL REFERENCES audit_findings(id) ON DELETE CASCADE,
    priority TEXT NOT NULL,
    owner TEXT,
    plan_version TEXT,
    eta_date DATE,
    verification_run_id BIGINT REFERENCES audit_runs(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_findings_run_id ON audit_findings(run_id);
CREATE INDEX IF NOT EXISTS idx_audit_findings_dimension ON audit_findings(dimension);
CREATE INDEX IF NOT EXISTS idx_audit_findings_severity ON audit_findings(severity);
CREATE INDEX IF NOT EXISTS idx_audit_metrics_run_id ON audit_metrics(run_id);
CREATE INDEX IF NOT EXISTS idx_optimization_tasks_finding_id ON optimization_tasks(finding_id);
