# IceGen — Icebreaker Generation System

## What this is

A pipeline that automatically generates and evaluates personalized cold email icebreakers for outreach campaigns.

Built to replace manual copy-paste from Google Sheets + ad-hoc LLM prompting with a repeatable, scored, auditable system.

## Business context

The sender (Leo) is a B2B connector — not a generic cold emailer.
The positioning: someone who monitors market signals and connects supply with demand, taking a cut.
Current active niche: recruiting (connecting companies mid-search with staffing/recruiting agencies).
Future niches: logistics, and others.

The emails do NOT come from a recruiter or job seeker.
The sender is a third-party connector who sees demand (companies actively hiring) and routes it to supply (recruiting agencies).

This distinction must be preserved in every prompt and every generated email.

## Architecture — Unified Enrichment

All pipeline steps use one pattern: **input columns + prompt → output**.

Two output types:
- `text` — single string → one output column (e.g. `email_body`, `pain_point`)
- `json` — structured dict → multiple columns defined by `json_schema`

```
CSV input
  → run_enrichment(extraction prompt, json)   extracts dreamICP, company_type, subniche, painTheySolve
  → run_enrichment(generation prompt, text)   writes icebreaker body
  → run_enrichment(evaluation prompt, json)   scores specificity, clarity, role_confusion, etc.
  → select_best()                             picks highest score, tiebreak = shorter
  → save to DB                               all variants stored, best flagged
  → CSV output                               best email per lead
```

Core function: `scripts/enrichment.py` → `run_enrichment(prompt_text, context_vars, output_type, json_schema, temperature, max_tokens, log_fn)`

## Key distinction for extraction (recruiting niche)

Recruiting agencies have two groups:
- CANDIDATES = people they place (engineers, lawyers, etc.) — their PRODUCT
- CLIENTS/BUYERS = companies that pay them to find candidates — their ICP

dreamICP = always the BUYERS, never the candidates.

Wrong: "software engineers at SaaS startups"
Right: "CTOs at Series A SaaS startups"

## Active batch

batch01 — recruiting niche, Q2 pipeline angle
Prompt: `prompts/batch01_recruiting_q2_connector.txt`
DB: `icegen` (Postgres on Hostinger VPS, user: n8n)
Model: `openai/gpt-oss-120b` via Groq API
App: Streamlit at `72.61.143.225:8501`, runs as `/opt/icegen/bin/streamlit run /opt/icegen/app/app.py`

## File structure

```
app.py                    — Streamlit UI
scripts/
  main.py                 — pipeline orchestration + CLI entry point
  enrichment.py           — unified LLM caller (text + json output modes)
  db.py                   — Postgres storage (migrations, prompts, runs, inputs, generations)
  seed_prompts.py         — one-time script to seed prompts table
  tunnel.bat              — SSH tunnel to Postgres on VPS (localhost:15432)

prompts/
  extraction.txt                      — extraction prompt (json output)
  evaluation.txt                      — scoring prompt (json output)
  batch01_recruiting_q2_connector.txt — active generation prompt

niches/
  recruiting.txt   — niche context passed to extraction
  logistics.txt    — future niche (draft)

migrations/
  001–007           — DB schema, applied automatically by init_schema()

configs/
  recruiting_v1.json    — active config (niche: recruiting)
  model_pricing.json    — token pricing per model

docs/
  models.md                        — Groq models reference
  ssm_sop_connector_prompts.md     — connector copywriting angles
  antifragile_variable_prompts.md  — variable extraction prompts
```

## Prompts table (DB)

Prompts stored in `prompts` table with fields:
- `name`, `type` (generation/extraction), `content`, `notes`
- `output_type` — `text` | `json`
- `output_column` — column name for text output
- `json_schema` — `[{name, type, description}]` for json output

## Rules for Claude

- **Never push to GitHub without explicit permission from Leo.**
- **Never commit sensitive files** (.env, CSV with leads, output files).
- **Scripts go in `scripts/`**, never in the project root.
- **New DB changes = new migration file** (`migrations/00N_description.sql`), never edit existing ones.
- **Update CHANGELOG.md** on every meaningful change before committing.
- **Deploy to VPS via scp**, not git (VPS is not a git repo).

## Running locally

```bash
pip install -r requirements.txt

# 1. Open SSH tunnel first (separate terminal)
scripts\tunnel.bat

# 2. Test on 3 leads
python scripts/main.py --input "path/to/leads.csv" --limit 3

# 3. Full batch
python scripts/main.py --input "path/to/leads.csv"
```

## Deploy to VPS

```bash
scp -i ~/.ssh/id_ed25519_hostinger scripts/main.py root@72.61.143.225:/opt/icegen/app/scripts/
scp -i ~/.ssh/id_ed25519_hostinger app.py root@72.61.143.225:/opt/icegen/app/
# then restart Streamlit on VPS
```

## Environment

See `.env.example`. Copy to `.env` and fill in:
- `GROQ_API_KEY` — Groq API key
- `POSTGRES_*` — connection to icegen DB on Hostinger VPS
- `DEFAULT_MODEL` — defaults to `openai/gpt-oss-120b`
