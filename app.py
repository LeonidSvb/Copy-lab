import sys
import io
import json
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")

from db import init_schema, get_runs, get_run_results
from main import run, load_config, COLUMN_MAP

st.set_page_config(page_title="IceGen", layout="wide")
st.title("IceGen")

# ── Sidebar ────────────────────────────────────────────────────────────────────

st.sidebar.header("Settings")

config_files = sorted(ROOT.glob("configs/*.json"))
if not config_files:
    st.error("No configs found in configs/")
    st.stop()

config_names = [f.stem for f in config_files]
selected_config_name = st.sidebar.selectbox("Config", config_names)
selected_config_path = str(ROOT / "configs" / f"{selected_config_name}.json")

config_data = load_config(selected_config_path)
with st.sidebar.expander("Config details"):
    st.json(config_data)

mode = st.sidebar.radio("Mode", ["generate", "baseline"])
limit_val = st.sidebar.number_input("Limit leads (0 = all)", min_value=0, value=0, step=1)
limit = int(limit_val) if limit_val > 0 else None

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

# ── Run tab ────────────────────────────────────────────────────────────────────

tab_run, tab_history = st.tabs(["Run", "History"])

with tab_run:
    st.subheader("Upload CSV and run pipeline")
    uploaded_file = st.file_uploader("CSV file", type=["csv"])

    if uploaded_file:
        csv_bytes = uploaded_file.read()
        csv_content = csv_bytes.decode("utf-8", errors="replace")
        df_preview = pd.read_csv(io.StringIO(csv_content))

        st.write(f"{len(df_preview)} leads — **{uploaded_file.name}**")
        with st.expander("Preview (first 5 rows)"):
            st.dataframe(df_preview.head(5), use_container_width=True)

        if st.button("Run pipeline", type="primary"):
            log_lines = []
            log_container = st.empty()

            def log_fn(msg):
                log_lines.append(str(msg))
                log_container.code("\n".join(log_lines[-40:]))

            with st.spinner("Processing..."):
                try:
                    results = run(
                        df=pd.read_csv(io.StringIO(csv_content)),
                        config_file=selected_config_path,
                        mode=mode,
                        limit=limit,
                        log_fn=log_fn,
                        csv_filename=uploaded_file.name,
                        csv_content=csv_content,
                        output_csv=None,
                        batch_prompt_file=selected_prompt_path,
                        variant_count=variant_count,
                        temperature_generation=temperature,
                    )

                    st.success(f"Done. {len(results)} leads processed.")
                    results_df = pd.DataFrame(results)

                    st.dataframe(results_df, use_container_width=True)

                    csv_out = results_df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "Download results CSV",
                        csv_out,
                        file_name=f"output_{uploaded_file.name}",
                        mime="text/csv",
                    )
                    st.session_state["last_results"] = results

                except Exception as e:
                    st.error(f"Pipeline error: {e}")

# ── History tab ────────────────────────────────────────────────────────────────

with tab_history:
    st.subheader("Previous runs")

    if st.button("Refresh"):
        st.rerun()

    try:
        runs = get_runs(limit=30)
        if not runs:
            st.info("No runs yet.")
        else:
            runs_df = pd.DataFrame(runs)[["id", "source", "config_name", "total_inputs", "created_at"]]
            st.dataframe(runs_df, use_container_width=True)

            selected_run_id = st.selectbox(
                "View best results for run",
                options=[r["id"] for r in runs],
                format_func=lambda rid: next(
                    f"#{rid} — {r['source']} ({r['total_inputs']} leads)"
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
