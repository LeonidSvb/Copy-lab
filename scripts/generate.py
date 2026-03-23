import os
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
DEFAULT_VARIANT_COUNT = 3
DEFAULT_TEMPERATURE = 0.6

INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

# Match at START of response only — avoids false positives like "I can't help but notice..."
_REFUSAL_STARTS = (
    "i'm sorry,",
    "i'm sorry but",
    "i cannot fulfill",
    "i can't fulfill",
    "i am unable to fulfill",
    "i'm unable to fulfill",
    "i cannot complete",
    "i can't complete",
)

# Unambiguous model error patterns — match anywhere
_REFUSAL_CONTAINS = (
    "isn't one of the allowed",
    "not in the allowed list",
    "don't match the required format",
    "doesn't match the required format",
    "variables you provided don't match",
    "variables you provided doesn't match",
)


def _is_refusal(text: str) -> bool:
    low = text.lower().strip()
    if any(low.startswith(m) for m in _REFUSAL_STARTS):
        return True
    if any(m in low for m in _REFUSAL_CONTAINS):
        return True
    return False


def generate_variants(
    prompt_text: str,
    context_vars: dict,
    variant_count: int = DEFAULT_VARIANT_COUNT,
    temperature: float = DEFAULT_TEMPERATURE,
) -> tuple[list[str], dict]:
    """
    Context-driven generation — no rigid template.

    prompt_text : full prompt (instructions + style + examples)
    context_vars: {column_name: value} — passed as a context block appended to prompt
    """
    context_lines = [
        f"{k}: {v}"
        for k, v in context_vars.items()
        if v and str(v).strip() and str(v).strip().lower() not in ("nan", "none", "")
    ]
    context_block = "\n".join(context_lines)
    full_prompt = f"{prompt_text.strip()}\n\n---\n{context_block}\n---"

    variants = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    for _ in range(variant_count):
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": full_prompt}],
            temperature=temperature,
            max_tokens=400,
        )
        usage["prompt_tokens"]     += response.usage.prompt_tokens
        usage["completion_tokens"] += response.usage.completion_tokens
        text = response.choices[0].message.content.strip()
        if not text:
            print(f"  [generate] empty response from model")
            text = INSUFFICIENT_DATA
        elif _is_refusal(text):
            print(f"  [generate] refusal detected: {text[:120]!r}")
            text = INSUFFICIENT_DATA
        variants.append(text)

    return variants, usage


def assemble_email(first_name: str, email_body: str) -> str:
    return f"Hey {first_name},\n\n{email_body}"
