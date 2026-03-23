# Changelog - IceGen

**RULES: Follow [Keep a Changelog](https://keepachangelog.com/) standard. Only 6 categories: Added/Changed/Deprecated/Removed/Fixed/Security. Concise, technical, no fluff.**

---

## [Unreleased]

### Planned — Unified Enrichment Architecture (v0.15.0)

**Concept:** extract / generate / evaluate — это один и тот же паттерн: input columns + prompt → output.
Разница только в формате вывода: `text` (одна колонка) или `json` (несколько колонок по схеме).

**Migration 007** — расширение таблицы `prompts`:
- `output_type TEXT DEFAULT 'text'` — `'text'` | `'json'`
- `output_column TEXT` — имя выходной колонки (для text типа, напр. `email_body`, `clean_name`)
- `json_schema JSONB` — для json типа: `[{"name": "dreamICP", "type": "string", "description": "..."}]`; имена полей = имена колонок в результате

**scripts/enrichment.py** (новый файл, заменяет extract.py + generate.py + evaluate.py):
- `run_enrichment(prompt_text, context_vars, output_type, json_schema, temperature, max_tokens)` — единая функция
- text режим: вызов модели → строка → возврат; refusal detection остаётся
- json режим: `response_format={"type": "json_object"}` в API + схема дописывается в конец промпта как инструкция; возврат dict
- `run_enrichment_variants(prompt_text, context_vars, n, temperature)` — для generation (3 варианта → pick best)
- `INSUFFICIENT_DATA` константа

**scripts/main.py** — рефакторинг `process_generate()`:
- extract() → `run_enrichment(..., output_type="json")`
- generate_variants() → `run_enrichment_variants(...)`
- evaluate() → `run_enrichment(..., output_type="json")`
- extract.py / generate.py / evaluate.py становятся deprecated (пока не удаляем)

**app.py — расширение Prompt Editor:**
- При сохранении промпта: поле `output_type` (radio: Text / JSON)
- Если Text: поле `Output column name` (напр. `email_body`)
- Если JSON: таблица Schema Fields (Field name | Type | Description); строки = будущие колонки
- При выборе промпта из коллекции: показывать output_type + output_column / json_schema

**app.py — видимость колонок в результатах:**
- multiselect "Visible columns" над таблицей результатов
- По умолчанию: `first_name`, `email`, `company_name`, `best_score`, `best_full_email`
- Скрытые колонки включены в CSV download

### Planned — Retry logic
- Exponential backoff on Groq 429 errors

---

## [0.14.0] - 2026-03-24 - Context-driven generation + prompt collection + run stats UI

### Added
- `migrations/006_prompts_table.sql` — `prompts` table with soft delete (`deleted_at`), type, notes
- `db.py` — `get_prompts()`, `save_prompt()`, `delete_prompt()` (soft)
- `main.py` — `DEFAULT_CONTEXT_COLUMNS` — default columns passed as context to generation
- `app.py` — Run tab: prompt editor (select from DB collection OR paste custom), save/delete prompt UI
- `app.py` — Run tab: context column multiselect (auto-detects long-text columns as default)
- `app.py` — Run tab: CSV preview expanded to 20 rows
- `app.py` — After run: stats block (total, OK, failed, duration, avg score, score>5 count) + "Regenerate N failed leads" button

### Changed
- `generate.py` — completely rewritten: no more rigid fill-in-the-blank template; accepts `prompt_text` + `context_vars` dict; context appended as `key: value` block after prompt separator
- `main.py` — `process_generate()` builds `context_vars` from selected columns + extracted variables; `run()` accepts `prompt_text` and `context_columns`
- `prompts/batch01_recruiting_q2_connector.txt` — rewritten as instruction prompt (no template variables); model gets context block with extracted data and writes freely

---

## [0.13.0] - 2026-03-24 - Batch load fix + dedup normalization

### Fixed
- `db.py` — added `_normalize_csv()`: strips BOM (`\ufeff`) and normalizes line endings (`\r\n` → `\n`) before hashing; same-data files exported from Excel with different line endings now correctly deduplicate
- `app.py` — same normalization applied on file upload before hashing and saving
- `app.py` — Run tab now shows banner "Loaded from batch: filename" + lead count + preview when content was loaded from Batches tab (previously invisible, looked like nothing happened)
- `app.py` — Batches tab "Load batch" now stores `csv_loaded_from=batch` flag so Run tab distinguishes upload vs batch-load

---

## [0.12.0] - 2026-03-24 - Refusal guard + history expanders + prompt fix

### Fixed
- `prompts/batch01_recruiting_q2_connector.txt` — removed strict job_titles whitelist (CFOs, plant managers only) that caused model refusals for CTOs and other valid titles; replaced with open examples
- `generate.py` — added refusal detection: if model returns "I'm sorry / I cannot / can't fulfill / not in allowed list" etc., variant is saved as `INSUFFICIENT_DATA` instead of garbage text
- `main.py` — `INSUFFICIENT_DATA` variants skip evaluation entirely (score=0, no tokens wasted)

### Changed
- `app.py` — History tab redesigned: flat list of runs replaced by `st.expander` per run; each expander shows 4 metrics (leads, duration, cost, model), aggregate score stats (avg, non-zero avg, leads with score>0), full results table, download button

---

## [0.11.0] - 2026-03-24 - Log display fix + results always shown + cost fix + row count fix

### Fixed
- `app.py` — results now saved to `session_state` even when `shared["error"]` is set (split `if/elif` into separate `if` blocks — partial successes were silently dropped)
- `app.py` — log display replaced `st.code` (copy button broken) with `st.text_area` + `st.download_button("Download log as .txt")` for reliable copy/export
- `configs/model_pricing.json` — file was copied to app root on VPS instead of `configs/`, causing "cost unknown" in all run summaries; fixed path
- `db.py` — `row_count` was calculated via `content.count("\n")` which overcounted multi-line CSV fields (400 leads → 3526); fixed to use `csv.reader` for correct row counting. Existing DB records patched.

---

## [0.10.0] - 2026-03-23 - Smart duplicate detection + batch run history

### Added
- `db.find_source_file_by_hash()` — exact duplicate check by MD5
- `db.find_source_files_by_name()` — name collision check (same name, different content)
- `db.get_runs_for_source_file()` — all runs for a given batch with stats (leads, config, duration, cost, error count)
- Upload duplicate logic: exact match → info banner with date + run count; same name different content → warning banner; new file → silent save
- Batches tab: runs history per selected batch (run_id, leads, config, source_type, duration, cost, error count, date)

### Changed
- `db.get_runs()` — now returns `source_type`, `duration_sec`, `cost_usd`, `model`

---

## [0.9.0]
- **Retry logic** — exponential backoff on Groq rate limit errors (429).
- **Email preview in Streamlit** — click a lead in results table → see full email rendered.

---

## [0.9.0] - 2026-03-23 - Parallelism, batch management, per-lead stats

### Added
- **Parallelism** — `ThreadPoolExecutor` in `run()`, configurable `max_workers` (1–10). CLI: `--workers N`. Streamlit: slider in sidebar. 400 leads: ~50 min → ~5 min at workers=10.
- **Batch management tab** in Streamlit — CSV saved to `source_files` immediately on upload (before running). Batches tab shows all uploads, "Load this batch" loads it into Run tab without re-uploading.
- `db.get_source_files()` — list of uploaded batches with filename, row count, size, date
- `db.get_source_file_content()` — fetch raw CSV from DB by source_file_id
- `db.update_input_stats()` — writes per-lead tokens and duration to `inputs` table
- `migrations/005_per_lead_stats.sql` — adds `tokens_in`, `tokens_out`, `duration_sec` to `inputs`
- Thread-safe logging — `log_lock` prevents garbled output when workers > 1

### Changed
- `process_generate()` / `process_baseline()` — track lead-level timing, call `update_input_stats()` at end
- `run()` — uses `ThreadPoolExecutor`, results collected by position (order preserved), usage accumulated with `usage_lock`
- `app.py` — `init_schema()` called once at startup, not per run. Parallel workers slider added.

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
