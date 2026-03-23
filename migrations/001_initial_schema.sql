-- IceGen DB Schema
-- Database: icegen

CREATE TABLE IF NOT EXISTS configs (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    params_json JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS runs (
    id           SERIAL PRIMARY KEY,
    config_id    INTEGER REFERENCES configs(id),
    source       TEXT,        -- csv filename or 'manual'
    total_inputs INTEGER,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS inputs (
    id                SERIAL PRIMARY KEY,
    run_id            INTEGER REFERENCES runs(id),
    first_name        TEXT,
    last_name         TEXT,
    email             TEXT,
    company_name      TEXT,
    website           TEXT,
    website_summary   TEXT,   -- main input for extraction
    short_description TEXT,   -- company short description from LinkedIn
    title             TEXT,   -- lead's job title
    linkedin_url      TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS extractions (
    id         SERIAL PRIMARY KEY,
    input_id   INTEGER REFERENCES inputs(id),
    run_id     INTEGER REFERENCES runs(id),
    data_json  JSONB,          -- full output: dreamICP, company_type, subniche, painTheySolve, reasoning
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS generations (
    id              SERIAL PRIMARY KEY,
    input_id        INTEGER REFERENCES inputs(id),
    run_id          INTEGER REFERENCES runs(id),
    extraction_id   INTEGER REFERENCES extractions(id),
    config_id       INTEGER REFERENCES configs(id),
    variant_index   INTEGER,   -- 1, 2, 3
    angle           TEXT,      -- observation / pain / signal / baseline_1 / baseline_2 / baseline_3
    icebreaker_line TEXT,      -- first line only (for quick review)
    full_email      TEXT,      -- full assembled email
    score           NUMERIC,
    evaluation_json JSONB,     -- full eval: specificity, genericness, clarity, role_confusion, issues...
    rank            INTEGER,   -- 1 = best for this input
    is_best         BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
