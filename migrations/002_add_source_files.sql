-- Migration 002: store raw source files for auditability

CREATE TABLE IF NOT EXISTS source_files (
    id           SERIAL PRIMARY KEY,
    filename     TEXT NOT NULL,
    content      TEXT NOT NULL,        -- raw CSV content
    file_hash    TEXT NOT NULL,        -- MD5 of content (detect duplicates)
    row_count    INTEGER,
    file_size    INTEGER,              -- bytes
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_files_hash ON source_files(file_hash);

-- Link runs to source_files
ALTER TABLE runs ADD COLUMN IF NOT EXISTS source_file_id INTEGER REFERENCES source_files(id);
