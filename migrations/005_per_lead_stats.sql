-- Migration 005: per-lead resource tracking

ALTER TABLE inputs ADD COLUMN IF NOT EXISTS tokens_in    INTEGER;
ALTER TABLE inputs ADD COLUMN IF NOT EXISTS tokens_out   INTEGER;
ALTER TABLE inputs ADD COLUMN IF NOT EXISTS duration_sec NUMERIC;
