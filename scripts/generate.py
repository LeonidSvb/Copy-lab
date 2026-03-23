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


def generate_variants(
    extraction: dict,
    batch_prompt_file: str = None,
    variant_count: int = DEFAULT_VARIANT_COUNT,
    temperature: float = DEFAULT_TEMPERATURE,
) -> list[str]:
    prompt_path = Path(batch_prompt_file) if batch_prompt_file else (
        ROOT / os.getenv("BATCH_PROMPT", "prompts/batch01_recruiting_q2_connector.txt")
    )
    with open(prompt_path, "r", encoding="utf-8") as f:
        batch_prompt = f.read()

    dream_icp = extraction.get("dreamICP", "")
    job_titles = dream_icp.split(" at ")[0].split(" in ")[0].strip()

    prompt = (
        batch_prompt
        .replace("{job_titles}", job_titles)
        .replace("{company_type}", extraction.get("company_type", ""))
        .replace("{recruiting_subniche}", extraction.get("subniche", ""))
    )

    variants = []
    for _ in range(variant_count):
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=300,
        )
        body = response.choices[0].message.content.strip()
        variants.append(body)

    return variants


def assemble_email(first_name: str, email_body: str) -> str:
    return f"Hey {first_name},\n\n{email_body}"
