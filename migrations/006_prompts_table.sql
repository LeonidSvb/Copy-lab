-- Migration 006: prompt collection

CREATE TABLE IF NOT EXISTS prompts (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'generation',  -- 'generation' | 'extraction' | 'evaluation'
    content     TEXT NOT NULL,
    notes       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    deleted_at  TIMESTAMPTZ  -- soft delete: NULL = active
);
