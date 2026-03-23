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

with open("prompts/evaluation.txt", "r", encoding="utf-8") as f:
    EVALUATION_PROMPT = f.read()


def evaluate(full_email: str) -> dict:
    prompt = EVALUATION_PROMPT.replace("{full_email}", full_email)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
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
            raise ValueError(f"Could not parse evaluation JSON:\n{raw}")

    return data


def select_best(variants: list[dict]) -> int:
    best_idx = 0
    best_score = float("-inf")

    for i, v in enumerate(variants):
        score = v["eval"].get("total_score", 0)
        if score > best_score:
            best_score = score
            best_idx = i
        elif score == best_score:
            current_len = len(variants[best_idx]["icebreaker_line"])
            candidate_len = len(v["icebreaker_line"])
            if candidate_len < current_len:
                best_idx = i

    return best_idx
