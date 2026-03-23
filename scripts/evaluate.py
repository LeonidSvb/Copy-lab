import json
import os
import re
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY"),
)

MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-oss-120b")


def evaluate(full_email: str) -> tuple[dict, dict]:
    with open(ROOT / "prompts/evaluation.txt", "r", encoding="utf-8") as f:
        evaluation_prompt = f.read()

    prompt = evaluation_prompt.replace("{full_email}", full_email)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1024,
    )

    usage = {
        "prompt_tokens":     response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
    }

    raw = response.choices[0].message.content.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*?\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                raise ValueError(f"Could not parse evaluation JSON:\n{raw[:300]}")
        else:
            raise ValueError(f"Could not parse evaluation JSON:\n{raw[:300]}")

    return data, usage


def select_best(variants: list[dict]) -> int:
    best_idx = 0
    best_score = float("-inf")

    for i, v in enumerate(variants):
        score = v.get("score", 0)
        if score > best_score:
            best_score = score
            best_idx = i
        elif score == best_score:
            if len(v["icebreaker_line"]) < len(variants[best_idx]["icebreaker_line"]):
                best_idx = i

    return best_idx
