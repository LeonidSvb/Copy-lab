"""One-time script to seed the prompts table with the initial prompt collection."""
import json
import psycopg2
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

conn = psycopg2.connect(
    host=os.getenv("POSTGRES_HOST"), port=os.getenv("POSTGRES_PORT"),
    dbname=os.getenv("POSTGRES_DB"), user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
)
cur = conn.cursor()

# (name, type, content, notes, output_type, output_column, json_schema)
PROMPTS = [

# ── GENERATION ─────────────────────────────────────────────────────────────

("batch01_q2_connector", "generation", """\
You are writing the body of a cold outreach email to a recruiting agency founder.

The sender is a B2B connector — NOT a recruiter. The sender monitors the market and connects \
companies mid-search with recruiting agencies. The sender takes a cut for the intro. \
This distinction must be clear.

Tone: casual, direct, peer-to-peer — not a sales pitch.
Capitalisation: always capitalize I and the first word of every sentence. Do not capitalize common nouns.
Punctuation: use simple hyphen - not em dash.
Length: 3 short sentences max. No greeting, no subject line, no sign-off.

Here is an example of the right tone and style:
---
I spend a lot of time talking to CFOs at mid-size manufacturing companies - so I usually know \
who's actively searching before it hits the market.

Most finance recruiters hit Q2 with a thin pipeline after a busy Q1. I connect agencies to \
companies that are mid-search right now - no cold BD, just warm intros.

Worth a quick chat to see if there's a fit?
---

Using the company information below, write a unique icebreaker that:
- Opens with what kind of buyer the sender talks to (based on dreamICP)
- Mentions the Q2 pipeline angle
- Ends with the warm intro offer

Return only the email body. No explanation, no quotes.\
""",
"Q2 pipeline angle. Main batch01 prompt. Context-driven, no template variables.",
"text", "email_body", None),


("ssm_noticed_company", "generation", """\
You are writing the body of a cold outreach email to a recruiting agency founder.

The sender is a B2B connector with market insight into what the agency's buyer companies are struggling with.

Output format — follow exactly:
Noticed [clean_company_name] helps [job_titles] at [company_type] — I know a few who [pain_description].

Worth intro'ing you?

Rules:
- clean_company_name: use clean_company_name from context if available, otherwise shorten \
company_name to 1-2 core words, drop LLC/Inc/Corp/Ltd/Recruiting/Staffing
- job_titles: real plural titles from dreamICP (CFOs, IT directors, plant managers) — \
never "decision-makers" or "leaders"
- company_type: specific type from dreamICP (mid-sized law firms, Series A startups, regional banks)
- pain_description: natural complaint the buyer would say to a friend \
(waste hours on, can't find, lose money when)
- No corporate speak: no solutions, leverage, optimize, streamline, platform
- ONE sentence + "Worth intro'ing you?" only

Use the company data provided below. Return only the two lines. No greeting, no explanation.\
""",
"SSM SOP Prompt #1. Company-based connector insight. 'Noticed [company] helps...'",
"text", "email_body", None),


("ssm_market_conversations", "generation", """\
You are writing the body of a cold outreach email to a recruiting agency founder.

The sender is a B2B connector who talks to the agency's buyer type constantly and hears their complaints firsthand.

Output format — follow exactly (3 lines):
Figured I'd reach out — I talk to a lot of [dreamICP] and they keep saying they [painTheySolve].

Thought you two should connect.

Let me know if this is something you'd want.

Rules:
- dreamICP: plural ICP group written like operators talk \
("founders in logistics", "CEOs in SaaS", "HR directors in manufacturing") — from context
- painTheySolve: operator-style complaint, like overheard in a hallway \
("can't keep up", "waste hours on hiring", "never get clear pricing") — from context
- No corporate speak: no optimize, solutions, scalable, streamline, platform
- Conversational, casual — not a pitch
- If no real pain data exists in context: return "INSUFFICIENT_DATA"

Use the company data provided below. Return only the 3 lines. No greeting, no explanation.\
""",
"SSM SOP Prompt #2. Market conversations angle. 'Figured I'd reach out — I talk to a lot of...'",
"text", "email_body", None),


("ssm_around_daily", "generation", """\
You are writing the body of a cold outreach email to a recruiting agency founder.

The sender is a B2B connector immersed in the agency's buyer market daily.

Output format — follow exactly (1 line):
Figured I'd reach out — I'm around [dreamICP] daily and they keep saying they [painTheySolve].

Rules:
- dreamICP: plural ICP group, operator language \
("founders in logistics", "CEOs in SaaS", "CFOs at mid-market firms") — from context
- painTheySolve: real complaint, natural language \
("can't keep up with hiring", "never find reliable partners", "waste hours chasing updates") — from context
- No buzzwords: no optimize, leverage, solutions, streamline, platform
- One sentence only. Must feel like real market signal.
- If no real pain data: return "INSUFFICIENT_DATA"

Use the company data provided below. Return only the single line. No greeting, no explanation.\
""",
"SSM SOP Prompt #3. 'I'm around them daily' angle. One-liner opener.",
"text", "email_body", None),


("ssm_deal_flow", "generation", """\
You are writing the body of a cold outreach email to a recruiting agency founder.

The sender is a B2B connector with live deal-flow and market movement insight.

Output format — follow exactly (3 lines):
Saw some movement on my side —
Figured I'd reach out — I'm around [dreamICP] daily and they keep saying they [painTheySolve].
Can plug you into the deal flow if you want.

Rules:
- dreamICP: plural ICP group, operator language \
("founders in logistics", "CEOs in SaaS", "HR directors in manufacturing") — from context
- painTheySolve: real operator complaint \
("can't keep up with volume", "never get reliable timelines", "waste hours chasing updates") — from context
- Tone: insider, operator, plugged-in — not a pitch
- No corporate speak: no optimize, solutions, streamline, platform
- If no real pain data: return "INSUFFICIENT_DATA"

Use the company data provided below. Return only the 3 lines exactly. No greeting, no explanation.\
""",
"SSM SOP Prompt #4. Deal-flow angle. 'Saw some movement on my side...'",
"text", "email_body", None),


# ── EXTRACTION ─────────────────────────────────────────────────────────────

("clean_company_name", "extraction", """\
Normalize the company name to the core brand employees actually use in casual conversation.

Rules:
- Maximum 2 words
- Keep the most distinctive part of the name
- Remove generic terms: Recruitment, Staffing, Recruiting, Search, Ltd, Inc, LLC, Group,
  Services, Global, International, Corp, Associates, Consulting, Solutions, Partners, HR
- Preserve original capitalization
- Prefer the name employees would casually say to friends

Return only the cleaned name. No explanation.\
""",
"Extraction prompt: normalize company name to 1-2 word brand. Input: company_name column.",
"text", "clean_company_name", None),


("ssm_pain_point", "extraction", """\
Your job: Identify one specific pain point this company likely faces based on their business description.

Good examples:
- "scaling outbound without burning domains"
- "finding qualified sales hires in a tight market"
- "managing deal flow across multiple funds"
- "keeping SOC 2 compliance costs down"
- "getting consistent case referrals"
- "filling senior roles without a big BD team"
- "keeping pipeline warm after a busy quarter"

Rules you MUST follow:
- Only ONE pain point
- 8-12 words maximum
- Write it like you're explaining to a friend, not giving a business presentation
- Use lowercase, no punctuation at the end
- Base it ONLY on what's in the company info below — if you can't identify a clear pain point, say "insufficient data"
- Don't use generic phrases like "growing their business" or "increasing revenue" — be specific
- The pain point should be something they're actively experiencing NOW, not a future goal
- No corporate speak: no "optimize," "leverage," "solutions," "streamline"

Give me: Just the pain point phrase. Nothing else. No explanation.\
""",
"SSM extraction: one specific pain point, 8-12 words lowercase.",
"text", "pain_point", None),


("ssm_relevant_observation", "extraction", """\
Your job: Identify one specific, recent observation about this company that shows you actually looked at their business.

Good examples:
- "Saw you just opened the second office in Naperville"
- "Noticed you brought on two new partners last month"
- "Congrats on the Series A with Andreessen"
- "Saw you're hiring for 3 sales roles right now"
- "Noticed you hit 50 employees this quarter"

Rules you MUST follow:
- Keep it under 12 words
- Write it casual and natural, like you're mentioning it to a colleague
- Only use information directly from the input — if you can't find something recent or interesting, say "insufficient data"
- Don't use corporate language or sound overly formal
- No quotation marks, no punctuation at the end
- Make it feel like a genuine observation, not a sales pitch
- Focus on recent changes, milestones, or growth signals if possible

Give me: Just the observation phrase. Nothing else. No explanation.\
""",
"SSM extraction: specific recent observation about the company.",
"text", "relevant_observation", None),

]

inserted = 0
for name, ptype, content, notes, output_type, output_column, json_schema in PROMPTS:
    cur.execute(
        "SELECT id FROM prompts WHERE name = %s AND deleted_at IS NULL",
        (name,)
    )
    if cur.fetchone():
        print(f"  skip (exists): {name}")
        continue
    cur.execute(
        """INSERT INTO prompts (name, type, content, notes, output_type, output_column, json_schema)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (name, ptype, content, notes, output_type, output_column,
         json.dumps(json_schema) if json_schema else None),
    )
    print(f"  inserted: {name} ({ptype}, output_type={output_type})")
    inserted += 1

conn.commit()
cur.close()
conn.close()
print(f"\nDone. {inserted} prompts inserted.")
