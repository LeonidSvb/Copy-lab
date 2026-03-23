ALTER TABLE prompts
    ADD COLUMN IF NOT EXISTS output_type   TEXT    NOT NULL DEFAULT 'text',
    ADD COLUMN IF NOT EXISTS output_column TEXT,
    ADD COLUMN IF NOT EXISTS json_schema   JSONB;

COMMENT ON COLUMN prompts.output_type   IS 'text = single string column, json = structured multi-column output';
COMMENT ON COLUMN prompts.output_column IS 'column name for text output (e.g. email_body, clean_name)';
COMMENT ON COLUMN prompts.json_schema   IS 'array of {name, type, description} defining output columns for json type';
