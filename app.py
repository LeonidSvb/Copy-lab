import sys
import io
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")

from db import (init_schema, get_runs, get_run_results,
                get_source_files, get_source_file_content,
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
    log_container = st.empty()

    def log_fn(msg):
        log_lines.append(str(msg))
        log_container.code("\n".join(log_lines[-50:]))

    with st.spinner(f"{label}..."):
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
            )
            st.session_state["results"] = results
            st.session_state["results_label"] = label
            st.session_state["results_filename"] = filename
        except Exception as e:
            st.error(f"Pipeline error: {e}")


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

        # save to DB immediately on upload
        try:
            sf_id = save_source_file_from_content(uploaded_file.name, csv_content)
            st.session_state["csv_content"]  = csv_content
            st.session_state["csv_filename"] = uploaded_file.name
        except Exception as e:
            st.warning(f"Could not save to DB: {e}")
            st.session_state["csv_content"]  = csv_content
            st.session_state["csv_filename"] = uploaded_file.name

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

            if st.button("Load this batch", type="primary"):
                try:
                    fname, content = get_source_file_content(selected_batch_id)
                    st.session_state["csv_content"]  = content
                    st.session_state["csv_filename"] = fname
                    st.session_state["results"]      = None
                    st.success(f"Loaded **{fname}** — switch to Run tab.")
                except Exception as e:
                    st.error(f"Could not load batch: {e}")

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
