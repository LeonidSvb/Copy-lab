# IceGen — Icebreaker Generation System

Automated pipeline that generates, scores, and selects personalized cold email icebreakers for B2B outreach.

Replaces manual copy-paste from Google Sheets + ad-hoc LLM prompting with a repeatable, scored, fully auditable system.

**Live UI:** http://72.61.143.225:8501
**Metabase analytics:** http://metabase.srv1133622.hstgr.cloud
**DB:** Postgres on `72.61.143.225:5432`, database `icegen`

---

## Business context

The sender (Leo) is a **B2B connector** — not a recruiter, not a job seeker.
Positioning: monitors market signals and routes supply to demand, taking a cut.
Active niche: **recruiting** (connecting companies mid-search with staffing agencies).

Every email must make this clear. The sender talks to hiring managers daily. He is not the agency. He is not the candidate. He connects them.

---

## How the pipeline works

```
CSV input
  → extract()       LLM reads company website summary → extracts dreamICP, company_type, subniche, painTheySolve
  → generate()      fills batch prompt template 3 times with temperature 0.6 → 3 email body variants
  → assemble()      adds "Hey {first_name}," greeting + body
  → evaluate()      LLM scores each full email on 4 dimensions
  → select_best()   picks winner by score, tiebreak = shorter icebreaker line
  → save to DB      all variants stored, best flagged with is_best=true
  → CSV output      best icebreaker + full email per lead
```

### Two modes

| Mode | What it does |
|---|---|
| `generate` (default) | Full pipeline: extract → generate 3 variants → evaluate → select best |
| `baseline` | Evaluates existing icebreakers from CSV columns `Personalisation 1/2/3` without generation — useful for benchmarking manual copy |

### Evaluation scoring

Each email is scored by the LLM on:

| Dimension | Range | Direction |
|---|---|---|
| `specificity` | 0–5 | higher = better |
| `clarity` | 0–5 | higher = better |
| `genericness_penalty` | 0–5 | subtracted |
| `role_confusion` | 0 or 1 | × -3 if sender sounds like a recruiter |
| `length_violation` | 0 or 1 | × -2 if too long |

`total_score = specificity + clarity - genericness_penalty - (role_confusion × 3) - (length_violation × 2)`

Full eval JSON is stored in `generations.evaluation_json`.

---

## Running the pipeline

### Option 1 — Streamlit UI (recommended)

Open **http://72.61.143.225:8501** in the browser.

1. Select config from the sidebar dropdown
2. Choose mode: `generate` or `baseline`
3. Set limit (optional, 0 = all leads)
4. Upload CSV
5. Click **Run pipeline**
6. Watch live logs, download results CSV when done

History tab shows all previous runs with results from the DB.

### Option 2 — CLI

```bash
# 1. Open SSH tunnel (local machine only — needed because Postgres binds to 127.0.0.1 on VPS)
scripts\tunnel.bat

# 2. Run in a new terminal
pip install -r requirements.txt

# Full generation pipeline, 3 leads as a test
python scripts/main.py --input "path/to/leads.csv" --output output.csv --limit 3

# Full batch
python scripts/main.py --input "path/to/leads.csv" --output output.csv

# Baseline evaluation mode
python scripts/main.py --input "path/to/leads.csv" --output output_baseline.csv --mode baseline
```

CLI arguments:

| Arg | Default | Description |
|---|---|---|
| `--input` | required | Path to input CSV |
| `--output` | `output.csv` | Path to output CSV |
| `--config` | `configs/recruiting_v1.json` | Batch config file |
| `--mode` | `generate` | `generate` or `baseline` |
| `--limit` | None | Max leads to process |

> Note: Streamlit on the VPS connects to Postgres directly (no tunnel). The tunnel is only needed when running CLI from a local machine.

---

## CSV input format

Required columns (exact names from Apollo/LinkedIn export):

| CSV column | Internal name | Used for |
|---|---|---|
| `First Name` | `first_name` | Greeting |
| `Last Name` | `last_name` | Logging |
| `Email` | `email` | Output |
| `Company Name` | `company_name` | Extraction input |
| `Company Website` | `website` | Stored |
| `Website Summary` | `website_summary` | Main extraction input |
| `Company Short Description` | `short_description` | Extraction input |
| `Title` | `title` | Stored |
| `LinkedIn` | `linkedin_url` | Stored |
| `Personalisation` | `baseline_1` | Baseline mode only |
| `Personalisation2` | `baseline_2` | Baseline mode only |
| `Personalisation3` | `baseline_3` | Baseline mode only |

---

## File structure

```
app.py                        — Streamlit UI entry point
scripts/
  main.py                     — CLI entry point + run() function used by both CLI and Streamlit
  extract.py                  — extraction step: LLM reads company info → structured JSON
  generate.py                 — generation step: fills prompt template 3 times
  evaluate.py                 — evaluation step: LLM scores email + select_best()
  db.py                       — all Postgres reads and writes
  tunnel.bat                  — opens SSH tunnel for local CLI access

prompts/
  extraction.txt                       — extracts dreamICP, company_type, subniche, painTheySolve
  batch01_recruiting_q2_connector.txt  — active generation prompt (Q2 recruiting batch)
  evaluation.txt                       — LLM-as-judge scoring prompt
  library_sop_company_insight.txt      — angle: "Noticed [company] helps..."
  library_sop_around_daily.txt         — angle: "I'm around [X] daily..."
  library_sop_deal_flow.txt            — angle: "Saw some movement on my side"
  blocks.txt                           — reusable prompt building blocks

configs/
  recruiting_v1.json          — active config for recruiting niche

niches/
  recruiting.txt              — niche context, dreamICP examples, email template
  logistics.txt               — future niche draft

migrations/
  001_initial_schema.sql      — configs, runs, inputs, extractions, generations tables
  002_add_source_files.sql    — source_files table + runs.source_file_id FK
  003_nullable_extraction_id.sql — extraction_id nullable (needed for baseline mode)

docs/
  models.md                   — Groq models, speeds, pricing, rate limits
  ssm_sop_connector_prompts.md       — connector copywriting SOP (mentor material)
  antifragile_variable_prompts.md    — variable extraction prompts (mentor material)
```

---

## Database schema

Migrations are applied automatically on every pipeline run via `db.init_schema()`. Applied files are tracked in `schema_migrations` — each migration runs exactly once.

### Tables

#### `configs`
Stores config JSON for each batch. One row per config name.

```sql
id          SERIAL PRIMARY KEY
name        TEXT              -- e.g. "recruiting_v1"
params_json JSONB             -- full config: model, temps, batch_prompt, etc.
created_at  TIMESTAMPTZ
```

#### `source_files`
Raw CSV content stored for auditability. Deduplicates by MD5 hash — uploading the same file twice creates one record.
See: [`migrations/002_add_source_files.sql`](migrations/002_add_source_files.sql)

```sql
id         SERIAL PRIMARY KEY
filename   TEXT
content    TEXT              -- full raw CSV
file_hash  TEXT              -- MD5, used for deduplication
row_count  INTEGER
file_size  INTEGER           -- bytes
created_at TIMESTAMPTZ
```

#### `runs`
One row per pipeline execution.

```sql
id             SERIAL PRIMARY KEY
config_id      INTEGER → configs.id
source_file_id INTEGER → source_files.id
source         TEXT              -- original CSV filename
total_inputs   INTEGER           -- number of leads processed
created_at     TIMESTAMPTZ
```

#### `inputs`
One row per lead from the CSV.

```sql
id               SERIAL PRIMARY KEY
run_id           INTEGER → runs.id
first_name       TEXT
last_name        TEXT
email            TEXT
company_name     TEXT
website          TEXT
website_summary  TEXT    -- main extraction input
short_description TEXT
title            TEXT
linkedin_url     TEXT
created_at       TIMESTAMPTZ
```

#### `extractions`
LLM extraction result. One row per input in generate mode.

```sql
id         SERIAL PRIMARY KEY
input_id   INTEGER → inputs.id
run_id     INTEGER → runs.id
data_json  JSONB    -- {dreamICP, company_type, subniche, painTheySolve, clean_company_name, reasoning}
created_at TIMESTAMPTZ
```

#### `generations`
All email variants — 3 per lead in generate mode, 1–3 in baseline mode.
The winner has `is_best=true`, `rank=1`.
`extraction_id` is nullable (NULL in baseline mode).
See: [`migrations/003_nullable_extraction_id.sql`](migrations/003_nullable_extraction_id.sql)

```sql
id              SERIAL PRIMARY KEY
input_id        INTEGER → inputs.id
run_id          INTEGER → runs.id
extraction_id   INTEGER → extractions.id  -- NULL for baseline
config_id       INTEGER → configs.id
variant_index   INTEGER   -- 1, 2, 3
angle           TEXT      -- observation / pain / signal / baseline_1 / baseline_2 / baseline_3
icebreaker_line TEXT      -- first line only, for quick scanning
full_email      TEXT      -- full assembled email with greeting
score           NUMERIC   -- total_score from evaluation
evaluation_json JSONB     -- {specificity, genericness_penalty, clarity, role_confusion, length_violation, issues, verdict}
rank            INTEGER   -- 1 = best for this input
is_best         BOOLEAN
created_at      TIMESTAMPTZ
```

### Entity relationship

```
source_files ──< runs >── configs
                  |
                inputs
                  |
            extractions
                  |
            generations
```

---

## Config file

`configs/recruiting_v1.json` — active config for the Q2 recruiting batch:

```json
{
  "name": "recruiting_v1",
  "niche": "recruiting",
  "batch_prompt": "prompts/batch01_recruiting_q2_connector.txt",
  "model": "openai/gpt-oss-120b",
  "temperature_extraction": 0.2,
  "temperature_generation": 0.6,
  "temperature_evaluation": 0.1,
  "variant_count": 3
}
```

To create a new batch: copy this file, change `name` and `batch_prompt`, save as `configs/new_name.json`. It will appear in the Streamlit config dropdown automatically.

---

## Environment variables

Copy `.env.example` to `.env` and fill in:

```env
GROQ_API_KEY=          # Groq API key — get from console.groq.com
POSTGRES_HOST=         # localhost (with tunnel) or 72.61.143.225 (direct)
POSTGRES_PORT=         # 15432 (tunnel) or 5432 (direct/VPS)
POSTGRES_DB=icegen
POSTGRES_USER=n8n
POSTGRES_PASSWORD=
DEFAULT_MODEL=openai/gpt-oss-120b
```

---

## VPS infrastructure

All services run on `72.61.143.225` (Hostinger VPS, Ubuntu 24.04):

| Service | Port | Access |
|---|---|---|
| Streamlit | 8501 | http://72.61.143.225:8501 |
| Metabase | 3000 | http://metabase.srv1133622.hstgr.cloud |
| Postgres | 5432 | localhost only (SSH tunnel for local access) |

**Streamlit systemd service:**

```bash
systemctl status icegen     # check status
systemctl restart icegen    # restart after code changes
systemctl stop icegen       # stop

# Logs
journalctl -u icegen -f
```

**Deploying code changes to VPS:**

```bash
# After editing scripts locally, copy to VPS:
scp -i ~/.ssh/id_ed25519_hostinger scripts/main.py root@72.61.143.225:/opt/icegen/app/scripts/
scp -i ~/.ssh/id_ed25519_hostinger app.py root@72.61.143.225:/opt/icegen/app/

# Then restart:
ssh -i ~/.ssh/id_ed25519_hostinger root@72.61.143.225 "systemctl restart icegen"
```

---

## Key design decisions

**Why 3 variants + LLM scoring instead of one prompt?**

Copywriting is subjective and fails in predictable ways:
- Role confusion — email implies sender is a recruiter, not a connector
- Generic phrases — "solutions", "leverage", "optimize", "streamline"
- Wrong ICP — names the candidate type instead of the hiring manager

Generating 3 variants and scoring each one catches these failures systematically. This is the LLM-as-judge pattern used in production by OpenAI and Anthropic.

**dreamICP = buyers, not candidates**

For recruiting agencies, the extraction must identify the **client** (the company paying the agency), not the candidate type they place.

Wrong: `"software engineers at SaaS startups"` — that's the product, not the buyer
Right: `"CTOs at Series A SaaS startups"` — that's who pays the agency

This distinction is enforced in `prompts/extraction.txt` and `niches/recruiting.txt`.

**Why Streamlit, not Next.js?**

Single-user internal tool. Streamlit runs in the same Python process as the pipeline — no API layer, no separate server, no JS. The Streamlit UI calls `run()` directly from `scripts/main.py`, same function used by the CLI.

---

## Adding a new niche

1. Create `niches/your_niche.txt` — niche context, ICP examples, what pain looks like
2. Create `prompts/your_batch_prompt.txt` — generation template with `{job_titles}`, `{company_type}`, `{recruiting_subniche}` placeholders
3. Create `configs/your_niche_v1.json` — set `"niche": "your_niche"`, point `batch_prompt` to your prompt
4. Run: `python scripts/main.py --input leads.csv --config configs/your_niche_v1.json`
