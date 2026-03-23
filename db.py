import json
import os
import glob
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", 5432),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


# ── migrations ────────────────────────────────────────────────────────────────

def init_schema():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.commit()

    migration_files = sorted(glob.glob("migrations/*.sql"))
    applied = 0

    for path in migration_files:
        filename = os.path.basename(path)
        cur.execute("SELECT 1 FROM schema_migrations WHERE filename = %s", (filename,))
        if cur.fetchone():
            continue
        with open(path, "r", encoding="utf-8") as f:
            cur.execute(f.read())
        cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (filename,))
        conn.commit()
        print(f"  applied migration: {filename}")
        applied += 1

    if applied == 0:
        print("  schema up to date.")

    cur.close()
    conn.close()


# ── configs ───────────────────────────────────────────────────────────────────

def get_or_create_config(name: str, params: dict) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM configs WHERE name = %s", (name,))
    row = cur.fetchone()
    if row:
        cur.close()
        conn.close()
        return row[0]
    cur.execute(
        "INSERT INTO configs (name, params_json) VALUES (%s, %s) RETURNING id",
        (name, json.dumps(params))
    )
    config_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return config_id


# ── runs ──────────────────────────────────────────────────────────────────────

def create_run(config_id: int, source: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO runs (config_id, source) VALUES (%s, %s) RETURNING id",
        (config_id, source)
    )
    run_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return run_id


def update_run_total(run_id: int, total: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE runs SET total_inputs = %s WHERE id = %s", (total, run_id))
    conn.commit()
    cur.close()
    conn.close()


# ── inputs ────────────────────────────────────────────────────────────────────

def save_input(run_id: int, row: dict) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO inputs
            (run_id, first_name, last_name, email, company_name,
             website, website_summary, short_description, title, linkedin_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        run_id,
        row.get("first_name"),
        row.get("last_name"),
        row.get("email"),
        row.get("company_name"),
        row.get("website"),
        row.get("website_summary"),
        row.get("short_description"),
        row.get("title"),
        row.get("linkedin_url"),
    ))
    input_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return input_id


# ── extractions ───────────────────────────────────────────────────────────────

def save_extraction(input_id: int, run_id: int, data: dict) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO extractions (input_id, run_id, data_json) VALUES (%s, %s, %s) RETURNING id",
        (input_id, run_id, json.dumps(data))
    )
    extraction_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return extraction_id


# ── generations ───────────────────────────────────────────────────────────────

def save_generation(input_id: int, run_id: int, extraction_id: int, config_id: int,
                    variant_index: int, angle: str,
                    icebreaker_line: str, full_email: str,
                    score, eval_data: dict) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO generations
            (input_id, run_id, extraction_id, config_id,
             variant_index, angle,
             icebreaker_line, full_email,
             score, evaluation_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        input_id, run_id, extraction_id, config_id,
        variant_index, angle,
        icebreaker_line, full_email,
        score, json.dumps(eval_data),
    ))
    gen_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return gen_id


def set_ranks(gen_ids_by_rank: list[int]):
    """gen_ids_by_rank[0] = best (rank 1), [1] = rank 2, etc."""
    conn = get_conn()
    cur = conn.cursor()
    for rank, gen_id in enumerate(gen_ids_by_rank, start=1):
        cur.execute(
            "UPDATE generations SET rank = %s, is_best = %s WHERE id = %s",
            (rank, rank == 1, gen_id)
        )
    conn.commit()
    cur.close()
    conn.close()
