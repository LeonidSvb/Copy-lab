import os
import sys
import json
import argparse
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
load_dotenv(ROOT / ".env")

from db import (init_schema, get_or_create_config, create_run, update_run_total,
                save_source_file, save_source_file_from_content,
                save_input, save_extraction, save_generation, set_ranks)
from extract import extract
from generate import generate_variants, assemble_email
from evaluate import evaluate, select_best

ANGLES = ["observation", "pain", "signal", "variant_4", "variant_5",
          "variant_6", "variant_7", "variant_8", "variant_9", "variant_10"]

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
    "Personalisation": "baseline_1",
    "Personalisation2": "baseline_2",
    "Personalisation3": "baseline_3",
}

BASELINE_BODY_SUFFIX = (
    "\n\nMost recruiting agencies hit Q2 with a thin pipeline after a busy Q1. "
    "I connect agencies to companies that are mid-search right now - no cold BD, just warm intros.\n\n"
    "Worth a quick chat to see if there's a fit?"
)


def build_baseline_email(first_name: str, icebreaker: str) -> str:
    greeting = f"Hey {first_name},\n\n"
    if "\n\n" in icebreaker or len(icebreaker) > 200:
        return greeting + icebreaker.strip()
    return greeting + icebreaker.strip() + BASELINE_BODY_SUFFIX


def load_config(config_file: str) -> dict:
    path = Path(config_file) if Path(config_file).is_absolute() else ROOT / config_file
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def process_baseline(row: dict, run_id: int, config_id: int, log_fn=print) -> dict:
    input_id = save_input(run_id, row)

    variants = []
    for i in range(1, 4):
        icebreaker = row.get(f"baseline_{i}", "")
        if not icebreaker or str(icebreaker).strip().lower() in ("", "nan"):
            continue

        icebreaker = str(icebreaker).strip()
        full_email = build_baseline_email(row.get("first_name", "there"), icebreaker)

        log_fn(f"  evaluating baseline_{i}...")
        eval_result = evaluate(full_email)
        score = eval_result.get("total_score", 0)

        gen_id = save_generation(
            input_id=input_id,
            run_id=run_id,
            extraction_id=None,
            config_id=config_id,
            variant_index=i,
            angle=f"baseline_{i}",
            icebreaker_line=icebreaker,
            full_email=full_email,
            score=score,
            eval_data=eval_result,
        )
        variants.append({"gen_id": gen_id, "score": score, "full_email": full_email})

    if variants:
        ranked = sorted(range(len(variants)), key=lambda i: -variants[i]["score"])
        set_ranks([variants[i]["gen_id"] for i in ranked])
        best = variants[ranked[0]]
        log_fn(f"  best baseline score: {best['score']}")

    return {
        "first_name": row.get("first_name"),
        "last_name": row.get("last_name"),
        "email": row.get("email"),
        "company_name": row.get("company_name"),
        "baseline_1_score": variants[0]["score"] if len(variants) > 0 else None,
        "baseline_2_score": variants[1]["score"] if len(variants) > 1 else None,
        "baseline_3_score": variants[2]["score"] if len(variants) > 2 else None,
    }


def process_generate(
    row: dict, run_id: int, config_id: int, niche: str, log_fn=print,
    batch_prompt_file: str = None, variant_count: int = 3, temperature_generation: float = 0.6,
) -> dict:
    company_info = "\n\n".join(filter(None, [
        row.get("company_name", ""),
        row.get("short_description", ""),
        row.get("website_summary", ""),
    ]))

    log_fn(f"  extracting...")
    extraction = extract(company_info, niche=niche)
    log_fn(f"  -> {extraction.get('dreamICP')} | {extraction.get('subniche')}")

    input_id = save_input(run_id, row)
    extraction_id = save_extraction(input_id, run_id, extraction)

    log_fn(f"  generating {variant_count} variants...")
    email_bodies = generate_variants(
        extraction,
        batch_prompt_file=batch_prompt_file,
        variant_count=variant_count,
        temperature=temperature_generation,
    )

    variants = []
    for i, body in enumerate(email_bodies):
        full_email = assemble_email(first_name=row.get("first_name", "there"), email_body=body)
        icebreaker_line = body.split("\n")[0].strip()
        angle = ANGLES[i] if i < len(ANGLES) else f"variant_{i+1}"

        log_fn(f"  evaluating variant {i+1} ({angle})...")
        eval_result = evaluate(full_email)
        score = eval_result.get("total_score", 0)

        gen_id = save_generation(
            input_id=input_id, run_id=run_id,
            extraction_id=extraction_id, config_id=config_id,
            variant_index=i + 1, angle=angle,
            icebreaker_line=icebreaker_line, full_email=full_email,
            score=score, eval_data=eval_result,
        )
        variants.append({"gen_id": gen_id, "icebreaker_line": icebreaker_line,
                         "full_email": full_email, "score": score})

    best_idx = select_best(variants)
    ranked = sorted(range(len(variants)), key=lambda i: (-variants[i]["score"],
                                                          len(variants[i]["icebreaker_line"])))
    set_ranks([variants[i]["gen_id"] for i in ranked])
    best = variants[best_idx]
    log_fn(f"  best: {ANGLES[best_idx]} (score {best['score']})")

    result = {
        "first_name": row.get("first_name"),
        "last_name": row.get("last_name"),
        "email": row.get("email"),
        "company_name": row.get("company_name"),
        "best_angle": ANGLES[best_idx] if best_idx < len(ANGLES) else "",
        "best_score": best["score"],
        "best_full_email": best["full_email"],
    }
    for i, v in enumerate(variants):
        result[f"variant_{i+1}_email"] = v["full_email"]
    return result


def run(
    input_csv: str = None,
    output_csv: str = "output.csv",
    config_file: str = "configs/recruiting_v1.json",
    mode: str = "generate",
    limit: int = None,
    log_fn=print,
    df: pd.DataFrame = None,
    csv_filename: str = None,
    csv_content: str = None,
    batch_prompt_file: str = None,
    variant_count: int = 3,
    temperature_generation: float = 0.6,
) -> list:
    init_schema()

    config = load_config(config_file)
    config_id = get_or_create_config(config["name"], config)
    niche = config.get("niche", "recruiting")

    if df is None:
        df = pd.read_csv(input_csv)
    df = df.rename(columns=COLUMN_MAP)
    if limit:
        df = df.head(limit)

    if csv_content is not None:
        source_file_id = save_source_file_from_content(csv_filename or "upload.csv", csv_content)
    elif input_csv is not None:
        source_file_id = save_source_file(input_csv)
    else:
        source_file_id = None

    source_label = csv_filename or (os.path.basename(input_csv) if input_csv else "upload")
    run_id = create_run(config_id, source_label, source_file_id)
    update_run_total(run_id, len(df))

    log_fn(f"run_id={run_id} | mode={mode} | {len(df)} leads\n")

    results = []
    for idx, row in df.iterrows():
        name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
        log_fn(f"[{idx+1}/{len(df)}] {name} — {row.get('company_name', '')}")
        try:
            if mode == "baseline":
                result = process_baseline(row.to_dict(), run_id, config_id, log_fn)
            else:
                result = process_generate(
                    row.to_dict(), run_id, config_id, niche, log_fn,
                    batch_prompt_file=batch_prompt_file,
                    variant_count=variant_count,
                    temperature_generation=temperature_generation,
                )
            results.append(result)
        except Exception as e:
            log_fn(f"  ERROR: {e}")
            results.append({"email": row.get("email"), "company_name": row.get("company_name"),
                            "error": str(e)})

    if output_csv:
        pd.DataFrame(results).to_csv(output_csv, index=False)
        log_fn(f"\nDone. {len(results)} leads -> {output_csv}  (run_id={run_id})")
    else:
        log_fn(f"\nDone. {len(results)} leads processed  (run_id={run_id})")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="output.csv")
    parser.add_argument("--config", default="configs/recruiting_v1.json")
    parser.add_argument("--mode", default="generate", choices=["generate", "baseline"],
                        help="baseline: evaluate existing icebreakers from CSV | generate: full pipeline")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    run(args.input, args.output, args.config, args.mode, args.limit)
