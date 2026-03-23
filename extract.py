import json
import os
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY"),
)

MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-oss-120b")

with open("prompts/extraction.txt", "r", encoding="utf-8") as f:
    EXTRACTION_PROMPT = f.read()


def load_niche_context(niche: str = "recruiting") -> str:
    niche_file = f"niches/{niche}.txt"
    try:
        with open(niche_file, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def extract(company_info: str, niche: str = "recruiting") -> dict:
    niche_context = load_niche_context(niche)
    prompt = (
        EXTRACTION_PROMPT
        .replace("{niche_context}", niche_context)
        .replace("{company_info}", company_info)
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=512,
    )

    raw = response.choices[0].message.content.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError(f"Could not parse extraction JSON:\n{raw}")

    return data
