import json
import os
import sys
import time
import threading
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
load_dotenv(ROOT / ".env")

from db import (init_schema, get_or_create_config, create_run, update_run_total,
                update_run_stats, update_input_stats,
                save_source_file, save_source_file_from_content,
                save_input, save_extraction, save_generation, set_ranks)
from enrichment import run_enrichment, INSUFFICIENT_DATA as _INSUF

ANGLES = ["observation", "pain", "signal", "variant_4", "variant_5",
          "variant_6", "variant_7", "variant_8", "variant_9", "variant_10"]

# columns from original CSV row passed to generation by default
DEFAULT_CONTEXT_COLUMNS = [
    "company_name", "short_description", "website_summary", "title", "linkedin_url",
]

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


# JSON schema for extraction enrichment
_EXTRACTION_SCHEMA = [
    {"name": "dreamICP",          "type": "string", "description": "plural buyer group, casual titles"},
    {"name": "company_type",      "type": "string", "description": "specific type of client companies"},
    {"name": "subniche",          "type": "string", "description": "2-4 word recruiting specialty label"},
    {"name": "painTheySolve",     "type": "string", "description": "how buyers complain about hiring, 8-15 words lowercase"},
    {"name": "clean_company_name","type": "string", "description": "company name without legal suffixes"},
    {"name": "reasoning",         "type": "string", "description": "one sentence explaining niche choice"},
]

# JSON schema for evaluation enrichment
_EVALUATION_SCHEMA = [
    {"name": "specificity",         "type": "number", "description": "0-5"},
    {"name": "genericness_penalty", "type": "number", "description": "0-5"},
    {"name": "clarity",             "type": "number", "description": "0-5"},
    {"name": "role_confusion",      "type": "number", "description": "0 or 1"},
    {"name": "length_violation",    "type": "number", "description": "0 or 1"},
    {"name": "total_score",         "type": "number", "description": "calculated composite"},
    {"name": "issues",              "type": "array",  "description": "list of specific problems"},
    {"name": "verdict",             "type": "string", "description": "one sentence on why it wins or loses"},
]


def _load_pricing() -> dict:
    pricing_file = ROOT / "configs/model_pricing.json"
    try:
        with open(pricing_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except FileNotFoundError:
        return {}


def _calc_cost(model: str, tokens_in: int, tokens_out: int) -> float | None:
    pricing = _load_pricing()
    if model not in pricing:
        return None
    p = pricing[model]
    return (tokens_in / 1_000_000) * p["input_per_1m"] + \
           (tokens_out / 1_000_000) * p["output_per_1m"]


def _add_usage(total: dict, delta: dict) -> None:
    total["prompt_tokens"]     += delta.get("prompt_tokens", 0)
    total["completion_tokens"] += delta.get("completion_tokens", 0)


def load_config(config_file: str) -> dict:
    path = Path(config_file) if Path(config_file).is_absolute() else ROOT / config_file
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_niche_context(niche: str) -> str:
    niche_file = ROOT / f"niches/{niche}.txt"
    try:
        with open(str(niche_file), "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def process_generate(row: dict, run_id: int, config_id: int, niche: str,
                     log_fn=print,
                     prompt_text: str = None,
                     batch_prompt_file: str = None,
                     context_columns: list = None,
                     variant_count: int = 3,
                     temperature_generation: float = 0.6) -> tuple[dict, dict]:
    lead_start = time.monotonic()
    usage = {"prompt_tokens": 0, "completion_tokens": 0}

    # ── Step 1: Extraction ────────────────────────────────────────────────────
    company_info = "\n\n".join(filter(None, [
        row.get("company_name", ""),
        row.get("short_description", ""),
        row.get("website_summary", ""),
    ]))
    niche_context = _load_niche_context(niche)

    log_fn(f"  extracting...")
    with open(ROOT / "prompts/extraction.txt", "r", encoding="utf-8") as f:
        extraction_prompt = f.read()

    extraction, ext_usage = run_enrichment(
        prompt_text=extraction_prompt,
        context_vars={
            "niche_context": niche_context,
            "company_info":  company_info,
        },
        output_type="json",
        json_schema=_EXTRACTION_SCHEMA,
        temperature=0.2,
        max_tokens=1024,
    )
    _add_usage(usage, ext_usage)
    log_fn(f"  -> {extraction.get('dreamICP')} | {extraction.get('subniche')}")

    input_id = save_input(run_id, row)
    extraction_id = save_extraction(input_id, run_id, extraction)

    # ── Step 2: Build context for generation ─────────────────────────────────
    cols = context_columns if context_columns is not None else DEFAULT_CONTEXT_COLUMNS
    context_vars = {col: row.get(col) for col in cols if row.get(col)}
    context_vars.update({
        k: v for k, v in extraction.items()
        if k != "reasoning" and v
    })

    # resolve prompt text
    if prompt_text is None:
        if batch_prompt_file:
            with open(batch_prompt_file, "r", encoding="utf-8") as f:
                prompt_text = f.read()
        else:
            default = ROOT / "prompts/batch01_recruiting_q2_connector.txt"
            with open(default, "r", encoding="utf-8") as f:
                prompt_text = f.read()

    # ── Step 3: Generation (N variants) ──────────────────────────────────────
    log_fn(f"  generating {variant_count} variants...")
    with open(ROOT / "prompts/evaluation.txt", "r", encoding="utf-8") as f:
        eval_prompt = f.read()

    variants = []
    for i in range(variant_count):
        body, gen_usage = run_enrichment(
            prompt_text=prompt_text,
            context_vars=context_vars,
            output_type="text",
            temperature=temperature_generation,
            max_tokens=400,
            log_fn=log_fn,
        )
        _add_usage(usage, gen_usage)

        full_email = f"Hey {row.get('first_name', 'there')},\n\n{body}"
        icebreaker_line = body.split("\n")[0].strip() if body != _INSUF else _INSUF
        angle = ANGLES[i] if i < len(ANGLES) else f"variant_{i+1}"

        # ── Step 4: Evaluate each variant ────────────────────────────────────
        if body == _INSUF:
            log_fn(f"  variant {i+1} ({angle}): INSUFFICIENT_DATA — skipping evaluation")
            eval_result = {"total_score": 0, "note": "insufficient_data"}
            score = 0
        else:
            log_fn(f"  evaluating variant {i+1} ({angle})...")
            eval_result, eval_usage = run_enrichment(
                prompt_text=eval_prompt,
                context_vars={"full_email": full_email},
                output_type="json",
                json_schema=_EVALUATION_SCHEMA,
                temperature=0.1,
                max_tokens=1024,
            )
            _add_usage(usage, eval_usage)
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

    # ── Step 5: Select best ───────────────────────────────────────────────────
    ranked = sorted(range(len(variants)), key=lambda i: (-variants[i]["score"],
                                                          len(variants[i]["icebreaker_line"])))
    set_ranks([variants[i]["gen_id"] for i in ranked])
    best_idx = ranked[0]
    best = variants[best_idx]
    log_fn(f"  best: {ANGLES[best_idx]} (score {best['score']})")

    update_input_stats(input_id, usage["prompt_tokens"], usage["completion_tokens"],
                       time.monotonic() - lead_start)

    result = {
        "first_name":      row.get("first_name"),
        "last_name":       row.get("last_name"),
        "email":           row.get("email"),
        "company_name":    row.get("company_name"),
        "best_angle":      ANGLES[best_idx] if best_idx < len(ANGLES) else "",
        "best_score":      best["score"],
        "best_full_email": best["full_email"],
    }
    for i, v in enumerate(variants):
        result[f"variant_{i+1}_email"] = v["full_email"]

    return result, usage


def run(
    input_csv: str = None,
    output_csv: str = "output.csv",
    config_file: str = "configs/recruiting_v1.json",
    limit: int = None,
    log_fn=print,
    df: pd.DataFrame = None,
    csv_filename: str = None,
    csv_content: str = None,
    prompt_text: str = None,
    batch_prompt_file: str = None,
    context_columns: list = None,
    variant_count: int = 3,
    temperature_generation: float = 0.6,
    source_type: str = "cli",
    max_workers: int = 1,
    progress_fn=None,
) -> list:
    init_schema()

    config = load_config(config_file)
    config_id = get_or_create_config(config["name"], config)
    niche = config.get("niche", "recruiting")
    model = os.getenv("DEFAULT_MODEL", "openai/gpt-oss-120b")

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
    run_id = create_run(config_id, source_label, source_file_id, source_type=source_type)
    update_run_total(run_id, len(df))

    log_fn(f"run_id={run_id} | source={source_type} | workers={max_workers} | {len(df)} leads\n")

    log_lock = threading.Lock()
    def safe_log(msg):
        with log_lock:
            log_fn(msg)

    total_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    usage_lock = threading.Lock()
    errors = []
    started_at = time.monotonic()

    rows = [(idx, row.to_dict()) for idx, row in df.iterrows()]
    total = len(rows)
    results = [None] * total

    progress_counter = {"done": 0}

    def process_one(pos: int, idx: int, row: dict):
        try:
            name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
            safe_log(f"[{pos+1}/{total}] {name} — {row.get('company_name', '')}")
            result, usage = process_generate(
                row, run_id, config_id, niche, safe_log,
                prompt_text=prompt_text,
                batch_prompt_file=batch_prompt_file,
                context_columns=context_columns,
                variant_count=variant_count,
                temperature_generation=temperature_generation,
            )
            with usage_lock:
                _add_usage(total_usage, usage)
                progress_counter["done"] += 1
                if progress_fn:
                    progress_fn(progress_counter["done"], total)
            return pos, result, None
        except Exception as e:
            import traceback
            err = {
                "email":     row.get("email", ""),
                "company":   row.get("company_name", ""),
                "step":      mode,
                "message":   str(e),
                "traceback": traceback.format_exc(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            safe_log(f"  ERROR [{row.get('company_name', '')}]: {e}")
            with usage_lock:
                progress_counter["done"] += 1
                if progress_fn:
                    progress_fn(progress_counter["done"], total)
            return pos, {"email": row.get("email"), "company_name": row.get("company_name"),
                         "error": str(e)}, err

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_one, pos, idx, row): pos
            for pos, (idx, row) in enumerate(rows)
        }
        for future in as_completed(futures):
            pos, result, err = future.result()
            results[pos] = result
            if err:
                errors.append(err)

    duration_sec = time.monotonic() - started_at
    cost_usd = _calc_cost(model, total_usage["prompt_tokens"], total_usage["completion_tokens"])

    update_run_stats(
        run_id=run_id,
        tokens_in=total_usage["prompt_tokens"],
        tokens_out=total_usage["completion_tokens"],
        cost_usd=cost_usd,
        model=model,
        duration_sec=duration_sec,
        errors=errors,
    )

    cost_str = f"${cost_usd:.4f}" if cost_usd is not None else "cost unknown"
    log_fn(
        f"\nDone. {total} leads | {duration_sec:.1f}s | "
        f"{total_usage['prompt_tokens']}in/{total_usage['completion_tokens']}out tokens | {cost_str}"
    )

    if output_csv:
        pd.DataFrame(results).to_csv(output_csv, index=False)
        log_fn(f"Output: {output_csv}  (run_id={run_id})")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="output.csv")
    parser.add_argument("--config", default="configs/recruiting_v1.json")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    run(args.input, args.output, args.config, args.limit,
        source_type="cli", max_workers=args.workers)
