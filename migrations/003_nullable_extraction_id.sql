-- Migration 003: allow NULL extraction_id in generations (needed for baseline mode)
ALTER TABLE generations ALTER COLUMN extraction_id DROP NOT NULL;
