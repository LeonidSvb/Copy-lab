import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY"),
)

MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-oss-120b")
BATCH_PROMPT_FILE = os.getenv("BATCH_PROMPT", "prompts/batch01_recruiting_q2_connector.txt")
VARIANT_COUNT = 3

with open(BATCH_PROMPT_FILE, "r", encoding="utf-8") as f:
    BATCH_PROMPT = f.read()


def generate_variants(extraction: dict) -> list[str]:
    # Extract job titles from dreamICP — e.g. "CTOs at SaaS startups" -> "CTOs"
    dream_icp = extraction.get("dreamICP", "")
    job_titles = dream_icp.split(" at ")[0].split(" in ")[0].strip()

    prompt = (
        BATCH_PROMPT
        .replace("{job_titles}", job_titles)
        .replace("{company_type}", extraction.get("company_type", ""))
        .replace("{recruiting_subniche}", extraction.get("subniche", ""))
    )

    variants = []
    for _ in range(VARIANT_COUNT):
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=300,
        )
        body = response.choices[0].message.content.strip()
        variants.append(body)

    return variants


def assemble_email(first_name: str, email_body: str) -> str:
    return f"Hey {first_name},\n\n{email_body}"
