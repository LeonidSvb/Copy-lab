# IceGen — Icebreaker Generation System

## What this is

A pipeline that automatically generates, evaluates, and selects personalized cold email icebreakers for outreach campaigns.

Built to replace manual copy-paste from Google Sheets + ad-hoc LLM prompting with a repeatable, scored, auditable system.

## Business context

The sender (Leo) is a B2B connector — not a generic cold emailer.
The positioning: someone who monitors market signals and connects supply with demand, taking a cut.
Current active niche: recruiting (connecting companies mid-search with staffing/recruiting agencies).
Future niches: logistics, and others.

The emails do NOT come from a recruiter or job seeker.
The sender is a third-party connector who sees demand (companies actively hiring) and routes it to supply (recruiting agencies).

This distinction must be preserved in every prompt and every generated email.

## Pipeline

```
CSV input
  → extract()       LLM extracts dreamICP, company_type, subniche, painTheySolve
  → generate()      LLM fills the batch template 3 times → 3 variants
  → assemble()      adds greeting + body + CTA into full email
  → evaluate()      LLM scores each full email (specificity, genericness, clarity, role_confusion)
  → select_best()   picks winner by score, tiebreak = shorter
  → save to DB      all variants stored, best flagged
  → CSV output      best icebreaker + full email per lead
```

## Why eval pipeline (not just one prompt)

Copywriting is subjective and error-prone. Common failure modes:
- role confusion (implies sender is a recruiter, not a connector)
- generic phrases ("solutions", "leverage", "optimize")
- wrong ICP (names the candidate type, not the company buyer type)

Generating 3 variants + scoring each one catches these failures systematically instead of relying on manual review at scale.

This is a standard LLM-as-judge pattern used in production by OpenAI, Anthropic, and others.

## Key distinction for extraction (recruiting niche)

Recruiting agencies have two groups:
- CANDIDATES = people they place (engineers, lawyers, etc.) — their PRODUCT
- CLIENTS/BUYERS = companies that pay them to find candidates — their ICP

dreamICP = always the BUYERS, never the candidates.

Wrong: "software engineers at SaaS startups"
Right: "CTOs at Series A SaaS startups"

## Active batch

batch01 — recruiting niche, Q2 pipeline angle
Template: `prompts/batch01_recruiting_q2_connector.txt`
Input: `_US+ recruit 10-100 - batch5.csv`
DB: `icegen` (Postgres on Hostinger VPS)
Model: `openai/gpt-oss-120b` via Groq API

## File structure

```
main.py                   — CLI entry point
extract.py                — extraction step (niche-aware)
generate.py               — generation step (3 variants)
evaluate.py               — evaluation + selection
db.py                     — Postgres storage

prompts/
  extraction.txt                    — extracts dreamICP, company_type, subniche, painTheySolve
  batch01_recruiting_q2_connector.txt  — active prompt for this batch
  library_sop_company_insight.txt   — SSM SOP angle: "Noticed [company] helps..."
  library_sop_around_daily.txt      — SSM SOP angle: "I'm around [X] daily..."
  library_sop_deal_flow.txt         — SSM SOP angle: "Saw some movement on my side"
  evaluation.txt                    — scores full email

niches/
  recruiting.txt   — niche context, dreamICP examples, email template
  logistics.txt    — future niche (draft)

docs/
  models.md                         — Groq models, speeds, pricing, rate limits
  ssm_sop_connector_prompts.md      — connector copywriting angles (mentor material)
  antifragile_variable_prompts.md   — variable extraction prompts (mentor material)
```

## Running

```bash
# Install
pip install -r requirements.txt

# Test on 3 leads
python main.py --input "path/to/leads.csv" --output output.csv --limit 3

# Full batch
python main.py --input "path/to/leads.csv" --output output.csv
```

## Environment

See `.env.example`. Copy to `.env` and fill in:
- `GROQ_API_KEY` — Groq API key
- `POSTGRES_*` — connection to icegen DB on Hostinger VPS
- `DEFAULT_MODEL` — defaults to `openai/gpt-oss-120b`
