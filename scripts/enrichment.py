"""
Unified enrichment runner.

All pipeline steps (extraction, generation, evaluation) use this single function.
Two output modes:
  text  — returns a single string  → one output column
  json  — returns a dict           → one column per schema field
"""
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


def _build_prompt(prompt_text: str, context_vars: dict) -> str:
    """Append context block to prompt."""
    context_lines = [
        f"{k}: {v}"
        for k, v in context_vars.items()
        if v and str(v).strip() and str(v).strip().lower() not in ("nan", "none", "")
    ]
    context_block = "\n".join(context_lines)
    return f"{prompt_text.strip()}\n\n---\n{context_block}\n---"


def _build_schema_instruction(json_schema: list) -> str:
    """
    Build instruction appended to prompt for JSON output.
    json_schema: [{"name": "field", "type": "string", "description": "..."}, ...]
    """
    fields = ", ".join(
        f'"{f["name"]}"' + (f' ({f.get("description", "")})' if f.get("description") else "")
        for f in json_schema
    )
    field_list = "\n".join(f'  "{f["name"]}": <{f.get("type", "string")}>' for f in json_schema)
    return (
        f"\nReturn a JSON object with exactly these fields:\n"
        f"{{{{\n{field_list}\n}}}}\n"
        f"No extra fields. No explanation outside the JSON."
    )


def run_enrichment(
    prompt_text: str,
    context_vars: dict,
    output_type: str = "text",
    json_schema: list = None,
    temperature: float = 0.3,
    max_tokens: int = 800,
) -> tuple:
    """
    Run a single enrichment call.

    Returns:
      output_type="text" -> (str, usage_dict)
      output_type="json" -> (dict, usage_dict)
    """
    full_prompt = _build_prompt(prompt_text, context_vars)

    if output_type == "json" and json_schema:
        full_prompt += "\n" + _build_schema_instruction(json_schema)

    kwargs = dict(
        model=MODEL,
        messages=[{"role": "user", "content": full_prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if output_type == "json":
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)

    usage = {
        "prompt_tokens":     response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
    }

    raw = response.choices[0].message.content.strip()

    if output_type == "json":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"Could not parse JSON from enrichment response:\n{raw[:300]}")
        return data, usage

    # text output
    if not raw:
        print("  [enrichment] empty response from model (raw is empty)")
        return INSUFFICIENT_DATA, usage
    if raw.strip().upper() == INSUFFICIENT_DATA:
        print("  [enrichment] model returned INSUFFICIENT_DATA literally")
        return INSUFFICIENT_DATA, usage
    if _is_refusal(raw):
        print(f"  [enrichment] refusal detected: {raw[:200]!r}")
        return INSUFFICIENT_DATA, usage
    return raw, usage
