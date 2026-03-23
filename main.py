import os
import json
import argparse
import pandas as pd
from dotenv import load_dotenv

from db import (init_schema, get_or_create_config, create_run, update_run_total,
                save_input, save_extraction, save_generation, set_ranks)
from extract import extract
from generate import generate_variants, assemble_email
from evaluate import evaluate, select_best

load_dotenv()

ANGLES = ["observation", "pain", "signal"]

COLUMN_MAP = {
    "First Name": "first_name",
    "Last Name": "last_name",
    "Company Name": "company_name",
    "Email": "email",
    "Company Website": "website",
    "Website Summary": "website_summary",
    "Company Short Description": "short_description",
    "Title": "title",
    "LinkedIn": "linkedin_url",
}


def load_config(config_file: str) -> dict:
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def process_lead(row: dict, run_id: int, config_id: int, niche: str) -> dict:
    company_info = "\n\n".join(filter(None, [
        row.get("company_name", ""),
        row.get("short_description", ""),
        row.get("website_summary", ""),
    ]))

    print(f"  extracting...")
    extraction = extract(company_info, niche=niche)
    print(f"  -> {extraction.get('dreamICP')} | {extraction.get('subniche')}")

    input_id = save_input(run_id, row)
    extraction_id = save_extraction(input_id, run_id, extraction)

    # ── generate 3 variants ──────────────────────────────────────────────────
    print(f"  generating 3 variants...")
    email_bodies = generate_variants(extraction)

    variants = []
    for i, body in enumerate(email_bodies):
        full_email = assemble_email(
            first_name=row.get("first_name", "there"),
            email_body=body,
        )
        icebreaker_line = body.split("\n")[0].strip()
        angle = ANGLES[i] if i < len(ANGLES) else f"variant_{i+1}"

        print(f"  evaluating variant {i+1} ({angle})...")
        eval_result = evaluate(full_email)
        score = eval_result.get("total_score", 0)

        gen_id = save_generation(
            input_id=input_id,
            run_id=run_id,
            extraction_id=extraction_id,
            config_id=config_id,
            variant_index=i + 1,
            angle=angle,
            icebreaker_line=icebreaker_line,
            full_email=full_email,
            score=score,
            eval_data=eval_result,
        )

        variants.append({
            "gen_id": gen_id,
            "icebreaker_line": icebreaker_line,
            "full_email": full_email,
            "score": score,
            "eval": eval_result,
        })

    # ── rank & select ────────────────────────────────────────────────────────
    best_idx = select_best(variants)
    ranked = sorted(range(len(variants)), key=lambda i: (
        -variants[i]["score"],
        len(variants[i]["icebreaker_line"])
    ))
    set_ranks([variants[i]["gen_id"] for i in ranked])

    best = variants[best_idx]
    print(f"  best: {ANGLES[best_idx]} (score {best['score']})")

    return {
        "first_name": row.get("first_name"),
        "last_name": row.get("last_name"),
        "email": row.get("email"),
        "company_name": row.get("company_name"),
        "best_angle": ANGLES[best_idx] if best_idx < len(ANGLES) else "",
        "best_score": best["score"],
        "best_full_email": best["full_email"],
        "variant_1_email": variants[0]["full_email"] if len(variants) > 0 else "",
        "variant_2_email": variants[1]["full_email"] if len(variants) > 1 else "",
        "variant_3_email": variants[2]["full_email"] if len(variants) > 2 else "",
    }


def run(input_csv: str, output_csv: str, config_file: str, limit: int = None):
    init_schema()

    config = load_config(config_file)
    config_id = get_or_create_config(config["name"], config)
    niche = config.get("niche", "recruiting")

    df = pd.read_csv(input_csv)
    df = df.rename(columns=COLUMN_MAP)
    if limit:
        df = df.head(limit)

    source_name = os.path.basename(input_csv)
    run_id = create_run(config_id, source_name)
    update_run_total(run_id, len(df))

    results = []
    total = len(df)

    for idx, row in df.iterrows():
        name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
        print(f"\n[{idx+1}/{total}] {name} — {row.get('company_name', '')}")
        try:
            result = process_lead(row.to_dict(), run_id, config_id, niche)
            results.append(result)
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "first_name": row.get("first_name"),
                "last_name": row.get("last_name"),
                "email": row.get("email"),
                "company_name": row.get("company_name"),
                "best_angle": "ERROR",
                "best_score": None,
                "best_full_email": str(e),
                "variant_1_email": "",
                "variant_2_email": "",
                "variant_3_email": "",
            })

    out_df = pd.DataFrame(results)
    out_df.to_csv(output_csv, index=False)
    print(f"\nDone. {len(results)} leads -> {output_csv}  (run_id={run_id})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="output.csv")
    parser.add_argument("--config", default="configs/recruiting_v1.json")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    run(args.input, args.output, args.config, args.limit)
