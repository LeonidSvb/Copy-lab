import sys
import io
import time
import threading
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")

import hashlib

from db import (init_schema, get_runs, get_run_results,
                get_source_files, get_source_file_content,
                get_runs_for_source_file,
                find_source_file_by_hash, find_source_files_by_name,
                save_source_file_from_content)
from main import run, load_config, COLUMN_MAP

# init DB schema once on startup
try:
    init_schema()
except Exception:
    pass

st.set_page_config(page_title="IceGen", layout="wide")
st.title("IceGen")

# ── Sidebar ────────────────────────────────────────────────────────────────────

st.sidebar.header("Settings")

config_files = sorted(ROOT.glob("configs/*.json"))
if not config_files:
    st.error("No configs found in configs/")
    st.stop()

config_names = [f.stem for f in config_files if f.stem != "model_pricing"]
selected_config_name = st.sidebar.selectbox("Config", config_names)
selected_config_path = str(ROOT / "configs" / f"{selected_config_name}.json")

config_data = load_config(selected_config_path)
with st.sidebar.expander("Config details"):
    st.json(config_data)

mode = st.sidebar.radio("Mode", ["generate", "baseline"])

st.sidebar.divider()
st.sidebar.subheader("Generation settings")

prompt_files = sorted((ROOT / "prompts").glob("*.txt"))
generation_prompts = [
    f for f in prompt_files
    if f.name not in ("extraction.txt", "evaluation.txt", "blocks.txt")
]
prompt_names = [f.stem for f in generation_prompts]
default_prompt = next(
    (i for i, f in enumerate(generation_prompts) if "batch01" in f.name), 0
)
selected_prompt_name = st.sidebar.selectbox(
    "Generation prompt", prompt_names, index=default_prompt,
    disabled=(mode == "baseline"),
)
selected_prompt_path = str(ROOT / "prompts" / f"{selected_prompt_name}.txt")

with st.sidebar.expander("Preview prompt"):
    try:
        st.code(open(selected_prompt_path).read(), language=None)
    except Exception:
        st.warning("Could not read prompt file.")

variant_count = st.sidebar.slider(
    "Variants per lead", min_value=1, max_value=6, value=3,
    disabled=(mode == "baseline"),
)
temperature = st.sidebar.slider(
    "Generation temperature", min_value=0.0, max_value=1.0, value=0.6, step=0.05,
    disabled=(mode == "baseline"),
)
max_workers = st.sidebar.slider(
    "Parallel workers", min_value=1, max_value=10, value=1,
    help="1 = sequential. 5-10 for large batches. Watch Groq rate limits.",
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _run_pipeline(csv_content: str, filename: str, limit: int | None, label: str):
    log_lines = []
    log_lock  = threading.Lock()

    # shared state between background thread and main polling loop
    shared = {"done": 0, "total": 0, "results": None, "error": None}

    # figure out actual lead count for progress bar
    df_temp = pd.read_csv(io.StringIO(csv_content))
    shared["total"] = min(limit, len(df_temp)) if limit else len(df_temp)

    def log_fn(msg):
        with log_lock:
            log_lines.append(str(msg))

    def progress_fn(done, total):
        shared["done"] = done

    def run_thread():
        try:
            results = run(
                df=pd.read_csv(io.StringIO(csv_content)),
                config_file=selected_config_path,
                mode=mode,
                limit=limit,
                log_fn=log_fn,
                csv_filename=filename,
                csv_content=csv_content,
                output_csv=None,
                batch_prompt_file=selected_prompt_path,
                variant_count=variant_count,
                temperature_generation=temperature,
                source_type="streamlit",
                max_workers=max_workers,
                progress_fn=progress_fn,
            )
            shared["results"] = results
        except Exception as e:
            import traceback
            shared["error"] = f"{e}\n\n{traceback.format_exc()}"

    # start background thread
    t = threading.Thread(target=run_thread, daemon=True)
    t.start()
    started_at = time.time()

    # ── progress UI (main thread polls every 0.5s) ─────────────────────────────
    st.markdown(f"**{label}**")
    progress_bar  = st.progress(0.0)
    cols          = st.columns(4)
    ui_processed  = cols[0].empty()
    ui_remaining  = cols[1].empty()
    ui_elapsed    = cols[2].empty()
    ui_eta        = cols[3].empty()

    while t.is_alive():
        done    = shared["done"]
        total   = shared["total"]
        elapsed = time.time() - started_at
        remain  = total - done
        rate    = done / elapsed if elapsed > 0 and done > 0 else 0
        eta_sec = remain / rate if rate > 0 else 0

        progress_bar.progress(done / total if total else 0)
        ui_processed.metric("Processed",  f"{done} / {total}")
        ui_remaining.metric("Remaining",  remain)
        ui_elapsed.metric("Elapsed",      f"{elapsed:.0f}s")
        ui_eta.metric("ETA",              f"{eta_sec:.0f}s" if eta_sec > 0 else "—")
        time.sleep(0.5)

    t.join()

    # final state
    elapsed = time.time() - started_at
    total   = shared["total"]
    progress_bar.progress(1.0 if total else 0)
    ui_processed.metric("Processed",  f"{total} / {total}")
    ui_remaining.metric("Remaining",  0)
    ui_elapsed.metric("Elapsed",      f"{elapsed:.0f}s")
    ui_eta.metric("ETA",              "Done")
    # ──────────────────────────────────────────────────────────────────────────

    if shared["error"]:
        st.error(f"Pipeline error: {shared['error']}")
    elif shared["results"] is not None:
        st.session_state["results"]          = shared["results"]
        st.session_state["results_label"]    = label
        st.session_state["results_filename"] = filename

    if log_lines:
        with st.expander("Run log", expanded=bool(shared["error"])):
            st.code("\n".join(log_lines))


def _show_results():
    results = st.session_state.get("results")
    if not results:
        return
    label    = st.session_state.get("results_label", "Run")
    filename = st.session_state.get("results_filename", "output")

    st.success(f"{label} — {len(results)} leads processed.")
    results_df = pd.DataFrame(results)
    st.dataframe(results_df, use_container_width=True)

    csv_out = results_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download results CSV", csv_out,
        file_name=f"output_{filename}", mime="text/csv", key="dl_results",
    )

# ── Tabs ───────────────────────────────────────────────────────────────────────

tab_run, tab_batches, tab_history = st.tabs(["Run", "Batches", "History"])

# ── Run tab ────────────────────────────────────────────────────────────────────

with tab_run:
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"])

    if uploaded_file:
        csv_bytes   = uploaded_file.read()
        csv_content = csv_bytes.decode("utf-8", errors="replace")
        df_full     = pd.read_csv(io.StringIO(csv_content))
        file_hash   = hashlib.md5(csv_content.encode()).hexdigest()

        st.session_state["csv_content"]  = csv_content
        st.session_state["csv_filename"] = uploaded_file.name

        # ── duplicate / name-collision check ──────────────────────────────────
        try:
            existing = find_source_file_by_hash(file_hash)
            if existing:
                prev_runs = get_runs_for_source_file(existing["id"])
                run_word  = "ран" if len(prev_runs) == 1 else "ранов"
                st.info(
                    f"Этот файл уже загружен "
                    f"({existing['created_at'][:10]}, {existing['row_count']} лидов). "
                    f"По нему сделано **{len(prev_runs)} {run_word}**. "
                    f"Можно запустить снова — будет новый ран в истории."
                )
            else:
                # check same name, different content
                same_name = find_source_files_by_name(uploaded_file.name)
                if same_name:
                    st.warning(
                        f"Файл с именем **{uploaded_file.name}** уже есть в базе "
                        f"({same_name[0]['created_at'][:10]}), но содержимое другое. "
                        f"Будет сохранён как новый батч."
                    )
                save_source_file_from_content(uploaded_file.name, csv_content)
        except Exception as e:
            st.warning(f"Could not check DB: {e}")
        # ──────────────────────────────────────────────────────────────────────

        st.write(f"**{len(df_full)} leads** — `{uploaded_file.name}`")
        with st.expander("Preview (first 5 rows)"):
            st.dataframe(df_full.head(5), use_container_width=True)

    csv_content = st.session_state.get("csv_content")
    csv_filename = st.session_state.get("csv_filename", "upload.csv")

    if csv_content:
        df_info = pd.read_csv(io.StringIO(csv_content))
        total   = len(df_info)

        st.divider()

        test_size = st.number_input(
            "Test run size", min_value=1, max_value=total,
            value=min(10, total), step=1,
        )

        col_test, col_full = st.columns([1, 1])
        with col_test:
            if st.button(f"Test run — first {test_size} leads", use_container_width=True):
                _run_pipeline(csv_content, csv_filename, int(test_size),
                              f"Test run ({test_size} leads)")
        with col_full:
            if st.button(f"Full run — all {total} leads", type="primary",
                         use_container_width=True):
                _run_pipeline(csv_content, csv_filename, None,
                              f"Full run ({total} leads)")

        st.divider()
        _show_results()

# ── Batches tab ────────────────────────────────────────────────────────────────

with tab_batches:
    st.subheader("Uploaded batches")

    if st.button("Refresh", key="refresh_batches"):
        st.rerun()

    try:
        batches = get_source_files(limit=30)
        if not batches:
            st.info("No batches uploaded yet.")
        else:
            batches_df = pd.DataFrame(batches)[
                ["id", "filename", "row_count", "file_size", "created_at"]
            ]
            batches_df["file_size"] = batches_df["file_size"].apply(
                lambda x: f"{x/1024:.1f} KB" if x else ""
            )
            st.dataframe(batches_df, use_container_width=True)

            st.divider()
            selected_batch_id = st.selectbox(
                "Load batch to Run tab",
                options=[b["id"] for b in batches],
                format_func=lambda bid: next(
                    f"#{bid} — {b['filename']} ({b['row_count']} leads, {b['created_at'][:10]})"
                    for b in batches if b["id"] == bid
                ),
            )

            col_load, col_gap = st.columns([1, 2])
            with col_load:
                if st.button("Load this batch into Run tab", type="primary"):
                    try:
                        fname, content = get_source_file_content(selected_batch_id)
                        st.session_state["csv_content"]  = content
                        st.session_state["csv_filename"] = fname
                        st.session_state["results"]      = None
                        st.success(f"Loaded **{fname}** — switch to Run tab.")
                    except Exception as e:
                        st.error(f"Could not load batch: {e}")

            # runs history for this batch
            st.divider()
            st.markdown("**Runs on this batch:**")
            try:
                batch_runs = get_runs_for_source_file(selected_batch_id)
                if not batch_runs:
                    st.info("No runs yet for this batch.")
                else:
                    for r in batch_runs:
                        dur  = f"{r['duration_sec']:.0f}s" if r["duration_sec"] else "—"
                        cost = f"${r['cost_usd']:.4f}" if r["cost_usd"] else "—"
                        errs = f"  ⚠ {r['errors']} errors" if r["errors"] else ""
                        st.markdown(
                            f"**Run #{r['run_id']}** — {r['leads']} leads — "
                            f"`{r['config']}` — `{r['source']}` — "
                            f"{dur} — {cost}{errs} — "
                            f"_{r['created_at'][:16]}_"
                        )
            except Exception as e:
                st.warning(f"Could not load run history: {e}")

    except Exception as e:
        st.warning(f"Could not connect to DB: {e}")

# ── History tab ────────────────────────────────────────────────────────────────

with tab_history:
    st.subheader("Previous runs")

    if st.button("Refresh", key="refresh_history"):
        st.rerun()

    try:
        runs = get_runs(limit=30)
        if not runs:
            st.info("No runs yet.")
        else:
            runs_df = pd.DataFrame(runs)[
                ["id", "source", "config_name", "total_inputs", "created_at"]
            ]
            st.dataframe(runs_df, use_container_width=True)

            selected_run_id = st.selectbox(
                "View best results for run",
                options=[r["id"] for r in runs],
                format_func=lambda rid: next(
                    f"#{rid} — {r['source']} ({r['total_inputs']} leads, {r['created_at'][:10]})"
                    for r in runs if r["id"] == rid
                ),
            )

            if selected_run_id:
                run_results = get_run_results(selected_run_id)
                if run_results:
                    display_df = pd.DataFrame(run_results).drop(
                        columns=["evaluation_json"], errors="ignore"
                    )
                    st.dataframe(display_df, use_container_width=True)

                    csv_out = display_df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        f"Download run #{selected_run_id} CSV",
                        csv_out,
                        file_name=f"run_{selected_run_id}_results.csv",
                        mime="text/csv",
                    )
                else:
                    st.info("No results for this run.")

    except Exception as e:
        st.warning(f"Could not connect to DB: {e}")
