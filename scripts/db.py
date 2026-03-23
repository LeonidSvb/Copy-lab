import hashlib
import json
import os
import glob
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")


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

    migration_files = sorted(glob.glob(str(ROOT / "migrations/*.sql")))
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


# ── source files ─────────────────────────────────────────────────────────────

def _count_csv_rows(content: str) -> int:
    import csv, io
    try:
        return sum(1 for _ in csv.reader(io.StringIO(content))) - 1  # minus header
    except Exception:
        return max(content.count("\n") - 1, 0)


def save_source_file(filepath: str) -> int:
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    content   = _normalize_csv(content)
    file_hash = hashlib.md5(content.encode()).hexdigest()
    row_count = _count_csv_rows(content)
    file_size = len(content.encode())
    filename = Path(filepath).name

    conn = get_conn()
    cur = conn.cursor()

    # return existing if same file already uploaded
    cur.execute("SELECT id FROM source_files WHERE file_hash = %s", (file_hash,))
    existing = cur.fetchone()
    if existing:
        cur.close()
        conn.close()
        print(f"  source file already stored (id={existing[0]})")
        return existing[0]

    cur.execute("""
        INSERT INTO source_files (filename, content, file_hash, row_count, file_size)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
    """, (filename, content, file_hash, row_count, file_size))
    sf_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    print(f"  source file stored: {filename} ({row_count} rows, id={sf_id})")
    return sf_id


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

def create_run(config_id: int, source: str, source_file_id: int = None,
               source_type: str = "cli") -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO runs (config_id, source, source_file_id, source_type) VALUES (%s, %s, %s, %s) RETURNING id",
        (config_id, source, source_file_id, source_type)
    )
    run_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return run_id


def update_run_stats(run_id: int, tokens_in: int, tokens_out: int,
                     cost_usd: float | None, model: str,
                     duration_sec: float, errors: list) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE runs SET
            completed_at = NOW(),
            duration_sec = %s,
            model        = %s,
            tokens_in    = %s,
            tokens_out   = %s,
            cost_usd     = %s,
            errors_json  = %s
        WHERE id = %s
    """, (
        round(duration_sec, 2),
        model,
        tokens_in,
        tokens_out,
        round(cost_usd, 6) if cost_usd is not None else None,
        json.dumps(errors),
        run_id,
    ))
    conn.commit()
    cur.close()
    conn.close()


def update_input_stats(input_id: int, tokens_in: int, tokens_out: int,
                       duration_sec: float) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE inputs SET tokens_in=%s, tokens_out=%s, duration_sec=%s WHERE id=%s",
        (tokens_in, tokens_out, round(duration_sec, 2), input_id)
    )
    conn.commit()
    cur.close()
    conn.close()


def get_source_files(limit: int = 30) -> list:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, filename, row_count, file_size, created_at
        FROM source_files
        ORDER BY created_at DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"id": r[0], "filename": r[1], "row_count": r[2],
         "file_size": r[3], "created_at": str(r[4])}
        for r in rows
    ]


def get_source_file_content(sf_id: int) -> tuple[str, str]:
    """Returns (filename, csv_content)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT filename, content FROM source_files WHERE id=%s", (sf_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise ValueError(f"Source file {sf_id} not found")
    return row[0], row[1]


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


def _normalize_csv(content: str) -> str:
    """Strip BOM and normalize line endings so same-data files hash identically."""
    return content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


def save_source_file_from_content(filename: str, content: str) -> int:
    content   = _normalize_csv(content)
    file_hash = hashlib.md5(content.encode()).hexdigest()
    row_count = _count_csv_rows(content)
    file_size = len(content.encode())

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT id FROM source_files WHERE file_hash = %s", (file_hash,))
    existing = cur.fetchone()
    if existing:
        cur.close()
        conn.close()
        return existing[0]

    cur.execute("""
        INSERT INTO source_files (filename, content, file_hash, row_count, file_size)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
    """, (filename, content, file_hash, row_count, file_size))
    sf_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return sf_id


def find_source_file_by_hash(file_hash: str) -> dict | None:
    """Returns existing source_file record if hash matches, else None."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, filename, row_count, file_size, created_at
        FROM source_files WHERE file_hash = %s
    """, (file_hash,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "filename": row[1], "row_count": row[2],
            "file_size": row[3], "created_at": str(row[4])}


def find_source_files_by_name(filename: str) -> list:
    """Returns all source_file records with this filename (different content)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, filename, row_count, file_size, created_at
        FROM source_files WHERE filename = %s
        ORDER BY created_at DESC
    """, (filename,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": r[0], "filename": r[1], "row_count": r[2],
             "file_size": r[3], "created_at": str(r[4])} for r in rows]


def get_runs(limit: int = 20) -> list:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT r.id, r.source, r.total_inputs, r.created_at, c.name as config_name,
               r.source_type, r.duration_sec, r.cost_usd, r.model
        FROM runs r
        LEFT JOIN configs c ON c.id = r.config_id
        ORDER BY r.created_at DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"id": r[0], "source": r[1], "total_inputs": r[2], "created_at": str(r[3]),
         "config_name": r[4], "source_type": r[5], "duration_sec": r[6],
         "cost_usd": float(r[7]) if r[7] else None, "model": r[8]}
        for r in rows
    ]


def get_runs_for_source_file(sf_id: int) -> list:
    """All runs made on a given source_file, with stats."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT r.id, r.total_inputs, r.source_type, c.name as config_name,
               r.duration_sec, r.cost_usd, r.model, r.created_at, r.errors_json
        FROM runs r
        LEFT JOIN configs c ON c.id = r.config_id
        WHERE r.source_file_id = %s
        ORDER BY r.created_at DESC
    """, (sf_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"run_id": r[0], "leads": r[1], "source": r[2], "config": r[3],
         "duration_sec": r[4], "cost_usd": float(r[5]) if r[5] else None,
         "model": r[6], "created_at": str(r[7]),
         "errors": len(r[8]) if r[8] else 0}
        for r in rows
    ]


def get_run_results(run_id: int) -> list:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT i.first_name, i.last_name, i.email, i.company_name,
               g.angle, g.score, g.icebreaker_line, g.full_email, g.evaluation_json
        FROM generations g
        JOIN inputs i ON i.id = g.input_id
        WHERE g.run_id = %s AND g.is_best = true
        ORDER BY i.id
    """, (run_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "first_name": r[0], "last_name": r[1], "email": r[2], "company_name": r[3],
            "angle": r[4], "score": r[5], "icebreaker_line": r[6],
            "full_email": r[7], "evaluation_json": r[8],
        }
        for r in rows
    ]


# ── prompts ───────────────────────────────────────────────────────────────────

def get_prompts(prompt_type: str = None) -> list:
    conn = get_conn()
    cur = conn.cursor()
    if prompt_type:
        cur.execute("""
            SELECT id, name, type, content, notes, created_at,
                   output_type, output_column, json_schema
            FROM prompts WHERE deleted_at IS NULL AND type = %s
            ORDER BY created_at DESC
        """, (prompt_type,))
    else:
        cur.execute("""
            SELECT id, name, type, content, notes, created_at,
                   output_type, output_column, json_schema
            FROM prompts WHERE deleted_at IS NULL
            ORDER BY created_at DESC
        """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "type": r[2],
         "content": r[3], "notes": r[4], "created_at": str(r[5]),
         "output_type": r[6] or "text", "output_column": r[7],
         "json_schema": r[8]}
        for r in rows
    ]


def save_prompt(name: str, prompt_type: str, content: str, notes: str = None,
                output_type: str = "text", output_column: str = None,
                json_schema: list = None) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO prompts (name, type, content, notes, output_type, output_column, json_schema)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
    """, (name, prompt_type, content, notes, output_type, output_column,
          json.dumps(json_schema) if json_schema else None))
    pid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return pid


def delete_prompt(prompt_id: int) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE prompts SET deleted_at = NOW() WHERE id = %s",
        (prompt_id,)
    )
    conn.commit()
    cur.close()
    conn.close()
