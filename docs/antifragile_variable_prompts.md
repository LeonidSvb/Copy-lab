# Anti-Fragile Ready-to-Use Variable Prompts (SSM Copy-Paste Library)

Source: SSM mentor materials

Run each variable separately. Don't batch.

---

## Variable 1 & 2: {{pain_point}}

Identifies one specific pain point this company likely faces.

**Prompt:**
```
Your job: Identify one specific pain point this company likely faces based on their business description.

Company info:
[PASTE COMPANY INFO HERE]

Good examples:
- "scaling outbound without burning domains"
- "finding qualified sales hires in a tight market"
- "managing deal flow across multiple funds"
- "keeping SOC 2 compliance costs down"
- "getting consistent case referrals"

Rules:
- Only ONE pain point
- 8-12 words maximum
- Write it like you're explaining to a friend
- Use lowercase, no punctuation at the end
- Base it ONLY on what's in the company info — if unclear, say "insufficient data"
- Don't use generic phrases like "growing their business" or "increasing revenue"
- The pain should be something they're experiencing NOW

Give me: Just the pain point phrase. Nothing else.
```

---

## Variable 3: {{relevant_observation}}

A specific, recent observation that proves you actually looked.

**Prompt:**
```
Your job: Identify one specific, recent observation about this company.

Company info:
[PASTE COMPANY INFO HERE]

Good examples:
- "Saw you just opened the second office in Naperville"
- "Noticed you brought on two new partners last month"
- "Congrats on the Series A with Andreessen"
- "Saw you're hiring for 3 sales roles right now"
- "Noticed you hit 50 employees this quarter"

Rules:
- Under 12 words
- Casual and natural
- Only use info from the input — if nothing recent, say "insufficient data"
- No corporate language
- No quotation marks, no punctuation at the end

Give me: Just the observation phrase. Nothing else.
```

---

## Variable 4: {{current_method}}

How they're probably getting customers right now.

**Prompt:**
```
Your job: Describe how this company is most likely getting customers right now.

Company info:
[PASTE COMPANY INFO HERE]

Good examples:
- "referrals and word of mouth"
- "Google ads and some SEO"
- "cold calling and LinkedIn outreach"
- "conference networking and partnerships"
- "account-based sales and demos"

Rules:
- 4-7 words maximum
- Be realistic for their stage/industry
- Lowercase, no punctuation
- Avoid jargon

Give me: Just the method phrase. Nothing else.
```

---

## Variable 5: {{outcome}}

Specific outcome they'd get from the service (with numbers).

**Prompt:**
```
Your job: State the specific outcome they would get — with concrete numbers.

Service: [YOUR SERVICE DESCRIPTION]
Company: [COMPANY INFO]

Good examples:
- "5-10 qualified consultations per month"
- "3-5 partnership meetings with Fortune 500 companies"
- "15-20 demo calls with your ICP every quarter"
- "8-12 qualified appointments monthly"

Rules:
- Include specific numbers (ranges fine: "5-10")
- 6-10 words maximum
- Focus on END RESULT, not process
- Lowercase, no punctuation
- Realistic — don't promise the moon

Give me: Just the outcome phrase. Nothing else.
```

---

## Tips

- Save good outputs → add them to your examples section
- If AI keeps making same mistake → add a specific rule to prevent it
- If you keep getting "insufficient data" → you need more company info OR rules are too strict
- Human review first 3-5 outputs before scaling
