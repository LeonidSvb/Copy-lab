# Changelog - IceGen

**RULES: Follow [Keep a Changelog](https://keepachangelog.com/) standard. Only 6 categories: Added/Changed/Deprecated/Removed/Fixed/Security. Concise, technical, no fluff.**

---

## [Unreleased]

### Planned
- **Parallelism** — `ThreadPoolExecutor` in `run()`, ~10–20 concurrent leads. 400 leads: 50 min → 3–5 min. Groq limit: 1000 RPM / 250K TPM.
- **Per-lead token tracking** — currently tokens are aggregated per run. Could add `tokens_in/out` to `generations` table for granular cost breakdown per lead.
- **Retry logic** — exponential backoff on Groq rate limit errors (429).
- **Email preview in Streamlit** — click a lead in results table → see full email rendered.

---

## [0.8.0] - 2026-03-23 - Run stats: tokens, cost, timing, errors, source tracking

### Added
- `migrations/004_run_stats.sql` — adds to `runs`: `source_type`, `completed_at`, `duration_sec`, `model`, `tokens_in`, `tokens_out`, `cost_usd`, `errors_json`
- `configs/model_pricing.json` — pricing table for all Groq models (input/output per 1M tokens). Add new models here, no code changes needed.
- `db.update_run_stats()` — writes timing, tokens, cost, errors to `runs` at end of pipeline
- `db.create_run()` — now accepts `source_type` param (`"cli"` or `"streamlit"`)
- Error logging: each exception captured as `{email, company, step, message, timestamp}` → stored in `runs.errors_json`

### Changed
- `extract()` — returns `(data, usage)` tuple
- `generate_variants()` — returns `(variants, usage)` tuple with summed usage across all variant calls
- `evaluate()` — returns `(data, usage)` tuple
- `process_generate()` / `process_baseline()` — accumulate usage per lead, return `(result, usage)`
- `run()` — accumulates total usage across all leads, calculates cost via `model_pricing.json`, logs summary line: `N leads | Xs | Tin/Tout tokens | $X.XXXX`
- `app.py` — passes `source_type="streamlit"` to `run()`; CLI passes `source_type="cli"`

---

## [0.7.0] - 2026-03-23 - Test run / full run flow

### Added
- Run tab: "Test run — first N leads" button with configurable size (default 10)
- Run tab: "Full run — all N leads" primary button
- Results persist in `session_state` — visible after clicking either button without re-uploading CSV
- CSV content stored in `session_state` on upload — buttons work after page rerun

### Removed
- "Limit leads" sidebar input — replaced by test/full run buttons

---

## [0.6.0] - 2026-03-23 - Generation controls in Streamlit UI

### Added
- Streamlit sidebar: generation prompt selector (all prompts except extraction/evaluation/blocks)
- Streamlit sidebar: prompt preview expander (shows raw prompt text before running)
- Streamlit sidebar: variants per lead slider (1–6, default 3)
- Streamlit sidebar: generation temperature slider (0.0–1.0, default 0.6)
- Controls disabled automatically when mode = baseline

### Changed
- `generate_variants()` — accepts `variant_count` and `temperature` params (defaults preserved)
- `process_generate()` — accepts and passes `batch_prompt_file`, `variant_count`, `temperature_generation`
- `run()` — accepts `batch_prompt_file`, `variant_count`, `temperature_generation`
- Output CSV now includes `variant_N_email` for all N variants dynamically (not hardcoded 1/2/3)
- `ANGLES` extended to 10 entries to support up to 10 variants

---

## [0.5.0] - 2026-03-23 - Streamlit frontend + pipeline stability

### Added
- `app.py` — Streamlit UI: CSV upload, config selector, mode/limit controls, live log output, results table, download button, run history tab
- `db.save_source_file_from_content()` — saves source file from string content (used by Streamlit uploads, no file path needed)
- `db.get_runs()` — returns last N runs with config name and lead count for history tab
- `db.get_run_results()` — returns best generations per lead for a given run_id
- `run()` in `main.py` now accepts `df`, `csv_content`, `csv_filename` params — works from both Streamlit and CLI

### Changed
- `scripts/extract.py` — prompt loaded inside `extract()`, not at module import (prevented Streamlit import crash)
- `scripts/generate.py` — prompt loaded inside `generate_variants()`, not at module import; accepts optional `batch_prompt_file` param
- `scripts/evaluate.py` — prompt loaded inside `evaluate()`, not at module import
- `run()` in `main.py` — all `print()` replaced with `log_fn` callback (default: `print`, Streamlit passes `st.write`); `output_csv=None` skips file write
- `process_baseline()` and `process_generate()` — accept `log_fn` param

### Fixed
- `select_best()` in `evaluate.py` — was accessing `v["eval"]` (KeyError), now correctly uses `v["score"]`

---

## [0.4.0] - 2026-03-23 - Baseline evaluation mode

### Added
- `--mode baseline` flag in `main.py` — evaluates existing icebreakers from CSV (Personalisation 1/2/3) without running generation
- `--mode generate` remains the default (full pipeline)
- `migrations/003_nullable_extraction_id.sql` — extraction_id nullable for baseline rows

### Changed
- `COLUMN_MAP` now includes `Personalisation`, `Personalisation2`, `Personalisation3` → `baseline_1/2/3`
- `main.py` split into `process_baseline()` and `process_generate()` functions

---

## [0.3.0] - 2026-03-23 - Source file storage

### Added
- `source_files` table: stores raw CSV content, MD5 hash, row count, file size
- `runs.source_file_id` FK to `source_files`
- `db.save_source_file()`: deduplicates by hash — same file uploaded twice = one record
- `migrations/002_add_source_files.sql`

### Changed
- `main.py`: saves source file to DB before creating run

---

## [0.2.0] - 2026-03-23 - Scripts reorganization + DB + Metabase

### Added
- `scripts/tunnel.bat` - SSH tunnel to Postgres on VPS (localhost:15432)
- `CHANGELOG.md` - this file
- Metabase `icegen` database connected at metabase.srv1133622.hstgr.cloud

### Changed
- All Python files moved from root to `scripts/` — pipeline now runs as `python scripts/main.py`
- All scripts use `ROOT = Path(__file__).parent.parent` for reliable path resolution
- `schema.sql` moved to `migrations/001_initial_schema.sql`
- `db.py` now applies migrations in order, tracks applied files in `schema_migrations` table
- `.env` updated to use SSH tunnel: `POSTGRES_HOST=localhost`, `POSTGRES_PORT=15432`

### Fixed
- Postgres not reachable from local machine (VPS binds to 127.0.0.1 only) — solved via SSH tunnel

---

## [0.1.0] - 2026-03-23 - Initial skeleton

### Added
- Pipeline: `extract.py` → `generate.py` → `evaluate.py` → `db.py`
- `scripts/main.py` - CLI entry point (`--input`, `--output`, `--config`, `--limit`)
- `configs/recruiting_v1.json` - first batch config
- `prompts/extraction.txt` - extracts dreamICP, company_type, subniche, painTheySolve
- `prompts/batch01_recruiting_q2_connector.txt` - active generation prompt for this batch
- `prompts/blocks.txt` - reusable prompt building blocks
- `prompts/library_sop_*.txt` - SSM SOP connector angle library (3 angles)
- `prompts/evaluation.txt` - LLM-as-judge scoring prompt
- `niches/recruiting.txt` - niche context and email template
- `niches/logistics.txt` - future niche draft
- `migrations/001_initial_schema.sql` - DB schema: configs, runs, inputs, extractions, generations
- `docs/models.md` - Groq models reference with pricing and rate limits
- `docs/ssm_sop_connector_prompts.md` - connector copywriting SOP
- `docs/antifragile_variable_prompts.md` - variable extraction prompts
- `CLAUDE.md` - project context and rules
- `.gitignore` - excludes .env, CSVs, __pycache__

---

**Maintained by:** Leo
**Last Updated:** 2026-03-23
