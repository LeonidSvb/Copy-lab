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
                save_source_file_from_content,
                get_prompts, save_prompt, update_prompt, delete_prompt)
from main import run, load_config, COLUMN_MAP, DEFAULT_CONTEXT_COLUMNS

# init DB schema once on startup
try:
    init_schema()
except Exception as e:
    st.warning(f"DB schema init error: {e}")

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

# active prompt text — resolved in Run tab when CSV is loaded
selected_prompt_text = None  # set below in Run tab prompt editor

# ── Helpers ────────────────────────────────────────────────────────────────────

def _run_pipeline(csv_content: str, filename: str, limit: int | None, label: str,
                  prompt_text: str = None, context_columns: list = None):
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
                prompt_text=prompt_text,
                context_columns=context_columns,
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

    # show error if any — but don't block results from displaying
    if shared["error"]:
        st.error(f"Pipeline error:\n\n```\n{shared['error']}\n```")

    # save results regardless — run may have partially or fully succeeded
    if shared["results"] is not None:
        st.session_state["results"]          = shared["results"]
        st.session_state["results_label"]    = label
        st.session_state["results_filename"] = filename
        st.session_state["results_elapsed"]  = elapsed
        st.session_state["results_total"]    = total

    if log_lines:
        log_text = "\n".join(log_lines)
        with st.expander("Run log", expanded=bool(shared["error"])):
            st.text_area("", log_text, height=300, key="log_display")
            st.download_button(
                "Download log as .txt",
                log_text.encode("utf-8"),
                file_name=f"log_{filename}.txt",
                mime="text/plain",
                key="dl_log",
            )


def _show_results():
    results  = st.session_state.get("results")
    if not results:
        return
    label    = st.session_state.get("results_label", "Run")
    filename = st.session_state.get("results_filename", "output")
    elapsed  = st.session_state.get("results_elapsed")
    total    = st.session_state.get("results_total", len(results))

    st.success(f"{label} — {len(results)} leads processed.")

    # ── run stats ─────────────────────────────────────────────────────────────
    results_df = pd.DataFrame(results)
    failed = results_df["best_full_email"].str.contains("INSUFFICIENT_DATA", na=False).sum() \
        if "best_full_email" in results_df.columns else 0
    good   = total - failed

    mc = st.columns(4)
    mc[0].metric("Total leads", total)
    mc[1].metric("Generated OK", good)
    mc[2].metric("Failed (INSUFFICIENT_DATA)", failed)
    mc[3].metric("Duration", f"{elapsed:.0f}s" if elapsed else "—")

    if "best_score" in results_df.columns:
        sc = st.columns(3)
        valid_scores = results_df[results_df["best_score"] > 0]["best_score"]
        sc[0].metric("Avg score (all)", f"{results_df['best_score'].mean():.1f}")
        sc[1].metric("Avg score (non-zero)", f"{valid_scores.mean():.1f}" if len(valid_scores) else "—")
        sc[2].metric("Leads score > 5", f"{(results_df['best_score'] > 5).sum()} / {total}")

    # ── column visibility ─────────────────────────────────────────────────────
    all_cols = list(results_df.columns)
    default_visible = [c for c in ["first_name", "email", "company_name",
                                   "best_angle", "best_score", "best_full_email"]
                       if c in all_cols]
    visible_cols = st.multiselect(
        "Visible columns", all_cols, default=default_visible, key="visible_cols",
    )
    display_df = results_df[visible_cols] if visible_cols else results_df

    # ── table + actions ───────────────────────────────────────────────────────
    st.dataframe(display_df, use_container_width=True)

    col_dl, col_regen = st.columns([1, 1])
    with col_dl:
        csv_out = results_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download results CSV", csv_out,
            file_name=f"output_{filename}", mime="text/csv", key="dl_results",
        )
    with col_regen:
        if failed > 0:
            if st.button(f"Regenerate {failed} failed leads", use_container_width=True):
                csv_content  = st.session_state.get("csv_content")
                csv_filename = st.session_state.get("csv_filename", filename)
                if csv_content:
                    # filter only leads that failed
                    failed_emails = results_df[
                        results_df.get("best_full_email", pd.Series()).str.contains(
                            "INSUFFICIENT_DATA", na=False
                        )
                    ]["email"].tolist() if "email" in results_df.columns else []

                    df_all  = pd.read_csv(io.StringIO(csv_content))
                    df_all  = df_all.rename(columns=COLUMN_MAP)
                    if failed_emails:
                        df_failed = df_all[df_all["email"].isin(failed_emails)]
                    else:
                        df_failed = df_all

                    failed_csv = df_failed.rename(
                        columns={v: k for k, v in COLUMN_MAP.items()}
                    ).to_csv(index=False)
                    _run_pipeline(
                        failed_csv, csv_filename,
                        None, f"Regenerate ({len(df_failed)} failed leads)"
                    )
                else:
                    st.warning("Original CSV not in session — upload it again first.")

# ── Tabs ───────────────────────────────────────────────────────────────────────

tab_run, tab_batches, tab_history = st.tabs(["Run", "Batches", "History"])

# ── Run tab ────────────────────────────────────────────────────────────────────

def _normalize_csv(content: str) -> str:
    return content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


with tab_run:
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"])

    if uploaded_file:
        csv_bytes   = uploaded_file.read()
        csv_content = _normalize_csv(csv_bytes.decode("utf-8", errors="replace"))
        df_full     = pd.read_csv(io.StringIO(csv_content))
        file_hash   = hashlib.md5(csv_content.encode()).hexdigest()

        st.session_state["csv_content"]       = csv_content
        st.session_state["csv_filename"]      = uploaded_file.name
        st.session_state["csv_loaded_from"]   = "upload"

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

    csv_content  = st.session_state.get("csv_content")
    csv_filename = st.session_state.get("csv_filename", "upload.csv")
    loaded_from  = st.session_state.get("csv_loaded_from", "upload")

    # banner when content was loaded from Batches tab (no file uploader)
    if csv_content and not uploaded_file:
        st.info(f"Loaded from batch: **{csv_filename}**  — switch to Run and press a button below.")
        df_preview = pd.read_csv(io.StringIO(csv_content))
        st.write(f"**{len(df_preview)} leads**")
        with st.expander("Preview (first 5 rows)"):
            st.dataframe(df_preview.head(5), use_container_width=True)

    if csv_content:
        df_info = pd.read_csv(io.StringIO(csv_content))
        total   = len(df_info)
        all_columns = list(df_info.columns)

        st.divider()

        # ── Prompt editor ──────────────────────────────────────────────────────
        if mode == "generate":
            st.subheader("Prompt")

            # load prompts from DB
            try:
                db_prompts = get_prompts(prompt_type="generation")
            except Exception:
                db_prompts = []

            prompt_options = ["— custom (paste below) —"] + [p["name"] for p in db_prompts]
            selected_prompt_option = st.selectbox(
                "Choose prompt from collection", prompt_options,
                key="prompt_selector",
            )

            # when selection changes — update text area state directly
            prev_selection = st.session_state.get("_prev_prompt_selector")
            if selected_prompt_option != prev_selection:
                st.session_state["_prev_prompt_selector"] = selected_prompt_option
                if selected_prompt_option == "— custom (paste below) —":
                    st.session_state["prompt_text_area"] = st.session_state.get("custom_prompt_text", "")
                else:
                    matched = next((p for p in db_prompts if p["name"] == selected_prompt_option), None)
                    st.session_state["prompt_text_area"] = matched["content"] if matched else ""

            prompt_text_input = st.text_area(
                "Prompt text", height=300, key="prompt_text_area",
            )
            # save custom text separately so it survives switching back
            if selected_prompt_option == "— custom (paste below) —":
                st.session_state["custom_prompt_text"] = prompt_text_input

            # show output_type info for selected prompt
            if selected_prompt_option != "— custom (paste below) —":
                matched = next((p for p in db_prompts if p["name"] == selected_prompt_option), None)
                if matched:
                    otype = matched.get("output_type", "text")
                    ocol  = matched.get("output_column")
                    schema = matched.get("json_schema")
                    if otype == "json" and schema:
                        field_names = ", ".join(f["name"] for f in schema)
                        st.caption(f"Output type: **json** — columns: `{field_names}`")
                    else:
                        st.caption(f"Output type: **text** — column: `{ocol or '—'}`")

            # save to collection
            with st.expander("Save this prompt to collection"):
                save_name  = st.text_input("Name", key="save_prompt_name")
                save_notes = st.text_area("Notes (optional)", height=60, key="save_prompt_notes")

                save_output_type = st.radio(
                    "Output type", ["text", "json"],
                    horizontal=True, key="save_output_type",
                )

                if save_output_type == "text":
                    save_output_column = st.text_input(
                        "Output column name",
                        placeholder="e.g. email_body, clean_name, pain_point",
                        key="save_output_column",
                    )
                    save_json_schema = None
                else:
                    st.caption("Define output fields — each field name becomes a column.")
                    if "schema_fields" not in st.session_state:
                        st.session_state["schema_fields"] = [{"name": "", "type": "string", "description": ""}]

                    fields = st.session_state["schema_fields"]
                    updated_fields = []
                    for fi, field in enumerate(fields):
                        c1, c2, c3, c4 = st.columns([2, 1, 3, 0.5])
                        fname = c1.text_input("Field name", value=field["name"],
                                              key=f"sf_name_{fi}", label_visibility="collapsed",
                                              placeholder="field_name")
                        ftype = c2.selectbox("Type", ["string", "number", "array"],
                                             index=["string","number","array"].index(field.get("type","string")),
                                             key=f"sf_type_{fi}", label_visibility="collapsed")
                        fdesc = c3.text_input("Description", value=field.get("description",""),
                                              key=f"sf_desc_{fi}", label_visibility="collapsed",
                                              placeholder="description")
                        if c4.button("x", key=f"sf_del_{fi}") and len(fields) > 1:
                            continue
                        updated_fields.append({"name": fname, "type": ftype, "description": fdesc})
                    st.session_state["schema_fields"] = updated_fields

                    if st.button("+ Add field", key="btn_add_field"):
                        st.session_state["schema_fields"].append({"name": "", "type": "string", "description": ""})
                        st.rerun()

                    save_output_column = None
                    save_json_schema = [f for f in updated_fields if f["name"].strip()]

                if st.button("Save prompt", key="btn_save_prompt"):
                    if save_name and prompt_text_input:
                        try:
                            save_prompt(
                                save_name, "generation", prompt_text_input,
                                save_notes or None,
                                output_type=save_output_type,
                                output_column=save_output_column or None,
                                json_schema=save_json_schema or None,
                            )
                            st.success(f"Saved: **{save_name}**")
                            st.session_state.pop("schema_fields", None)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Could not save: {e}")
                    else:
                        st.warning("Enter a name and prompt text.")

            # edit prompt
            if db_prompts:
                with st.expander("✏ Edit prompt"):
                    edit_name = st.selectbox(
                        "Select prompt to edit",
                        [p["name"] for p in db_prompts],
                        key="edit_prompt_select",
                    )
                    edit_p = next((p for p in db_prompts if p["name"] == edit_name), None)

                    # detect selection change — reload fields
                    if st.session_state.get("_prev_edit_select") != edit_name:
                        st.session_state["_prev_edit_select"] = edit_name
                        st.session_state["edit_name"]          = edit_p["name"]
                        st.session_state["edit_content"]       = edit_p["content"]
                        st.session_state["edit_notes"]         = edit_p["notes"] or ""
                        st.session_state["edit_output_type"]   = edit_p.get("output_type", "text")
                        st.session_state["edit_output_column"] = edit_p.get("output_column") or ""
                        schema = edit_p.get("json_schema")
                        st.session_state["edit_schema_fields"] = schema if schema else []

                    if edit_p:
                        e_name    = st.text_input("Name", key="edit_name")
                        e_content = st.text_area("Prompt text", height=250, key="edit_content")
                        e_notes   = st.text_input("Notes", key="edit_notes")

                        e_otype = st.radio(
                            "Output type", ["text", "json"],
                            index=0 if st.session_state.get("edit_output_type","text") == "text" else 1,
                            horizontal=True, key="edit_output_type",
                        )

                        if e_otype == "text":
                            e_ocol   = st.text_input("Output column name", key="edit_output_column")
                            e_schema = None
                        else:
                            st.caption("Schema fields — each name = output column.")
                            if not st.session_state.get("edit_schema_fields"):
                                st.session_state["edit_schema_fields"] = [{"name":"","type":"string","description":""}]

                            fields = st.session_state["edit_schema_fields"]
                            updated = []
                            for fi, field in enumerate(fields):
                                c1, c2, c3, c4 = st.columns([2, 1, 3, 0.5])
                                fname = c1.text_input("Name", value=field["name"],
                                                      key=f"esf_name_{fi}", label_visibility="collapsed",
                                                      placeholder="field_name")
                                ftype = c2.selectbox("Type", ["string","number","array"],
                                                     index=["string","number","array"].index(field.get("type","string")),
                                                     key=f"esf_type_{fi}", label_visibility="collapsed")
                                fdesc = c3.text_input("Desc", value=field.get("description",""),
                                                      key=f"esf_desc_{fi}", label_visibility="collapsed",
                                                      placeholder="description")
                                if c4.button("x", key=f"esf_del_{fi}") and len(fields) > 1:
                                    continue
                                updated.append({"name": fname, "type": ftype, "description": fdesc})
                            st.session_state["edit_schema_fields"] = updated

                            if st.button("+ Add field", key="btn_edit_add_field"):
                                st.session_state["edit_schema_fields"].append({"name":"","type":"string","description":""})
                                st.rerun()

                            e_ocol   = None
                            e_schema = [f for f in updated if f["name"].strip()]

                        if st.button("Save changes", key="btn_edit_save", type="primary"):
                            if e_name and e_content:
                                try:
                                    update_prompt(
                                        edit_p["id"], e_name, e_content,
                                        e_notes or None,
                                        output_type=e_otype,
                                        output_column=e_ocol or None,
                                        json_schema=e_schema or None,
                                    )
                                    st.success(f"Updated: **{e_name}**")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Could not update: {e}")
                            else:
                                st.warning("Name and prompt text are required.")

            # delete from collection
            if db_prompts:
                with st.expander("Delete prompt from collection"):
                    del_name = st.selectbox(
                        "Select prompt to delete",
                        [p["name"] for p in db_prompts],
                        key="del_prompt_select",
                    )
                    if st.button("Delete", key="btn_del_prompt", type="secondary"):
                        pid = next(p["id"] for p in db_prompts if p["name"] == del_name)
                        try:
                            delete_prompt(pid)
                            st.success(f"Deleted: **{del_name}**")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Could not delete: {e}")

            active_prompt_text = prompt_text_input or None

            # ── Context columns selector ───────────────────────────────────────
            st.subheader("Context columns")
            st.caption("Which columns to pass to the model alongside the prompt.")

            # auto-detect columns with long text as default
            def _is_long_col(col):
                sample = df_info[col].dropna().astype(str)
                return sample.str.len().mean() > 80 if len(sample) else False

            default_ctx = [c for c in all_columns if c in DEFAULT_CONTEXT_COLUMNS or _is_long_col(c)]
            default_ctx = list(dict.fromkeys(default_ctx))  # deduplicate, preserve order

            selected_context_cols = st.multiselect(
                "Columns", all_columns, default=default_ctx, key="context_cols",
            )
        else:
            active_prompt_text    = None
            selected_context_cols = None

        # ── Preview ────────────────────────────────────────────────────────────
        st.divider()
        with st.expander("Preview CSV (first 20 rows)"):
            st.dataframe(df_info.head(20), use_container_width=True)

        test_size = st.number_input(
            "Test run size", min_value=1, max_value=total,
            value=min(10, total), step=1,
        )

        col_test, col_full = st.columns([1, 1])
        with col_test:
            if st.button(f"Test run — first {test_size} leads", use_container_width=True):
                _run_pipeline(csv_content, csv_filename, int(test_size),
                              f"Test run ({test_size} leads)",
                              prompt_text=active_prompt_text,
                              context_columns=selected_context_cols or None)
        with col_full:
            if st.button(f"Full run — all {total} leads", type="primary",
                         use_container_width=True):
                _run_pipeline(csv_content, csv_filename, None,
                              f"Full run ({total} leads)",
                              prompt_text=active_prompt_text,
                              context_columns=selected_context_cols or None)

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
                        content = _normalize_csv(content)
                        st.session_state["csv_content"]     = content
                        st.session_state["csv_filename"]    = fname
                        st.session_state["csv_loaded_from"] = "batch"
                        st.session_state["results"]         = None
                        st.success(f"Loaded **{fname}** — перейди во вкладку Run.")
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
            for r in runs:
                dur  = f"{r['duration_sec']:.0f}s" if r["duration_sec"] else "—"
                cost = f"${r['cost_usd']:.4f}" if r["cost_usd"] else "—"
                label = (
                    f"Run #{r['id']} — {r['source']} — "
                    f"{r['total_inputs']} leads — "
                    f"{r['config_name']} — "
                    f"{dur} — {cost} — "
                    f"{r['created_at'][:16]}"
                )
                with st.expander(label):
                    # ── run summary row ────────────────────────────────────
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Leads", r["total_inputs"])
                    c2.metric("Duration", dur)
                    c3.metric("Cost", cost)
                    c4.metric("Model", r.get("model") or "—")

                    st.caption(
                        f"Config: `{r['config_name']}` | "
                        f"Source: `{r.get('source_type', '—')}` | "
                        f"Date: {r['created_at'][:16]}"
                    )

                    # ── lead results ───────────────────────────────────────
                    run_results = get_run_results(r["id"])
                    if not run_results:
                        st.info("No results stored.")
                    else:
                        display_df = pd.DataFrame(run_results).drop(
                            columns=["evaluation_json"], errors="ignore"
                        )

                        # aggregate score stats
                        if "score" in display_df.columns:
                            valid = display_df[display_df["score"] > 0]["score"]
                            col_a, col_b, col_c = st.columns(3)
                            col_a.metric("Avg score (best/lead)", f"{display_df['score'].mean():.1f}")
                            col_b.metric("Avg score (non-zero)", f"{valid.mean():.1f}" if len(valid) else "—")
                            col_c.metric("Leads with score > 0", f"{len(valid)} / {len(display_df)}")

                        st.dataframe(display_df, use_container_width=True)

                        csv_out = display_df.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            f"Download run #{r['id']} CSV",
                            csv_out,
                            file_name=f"run_{r['id']}_results.csv",
                            mime="text/csv",
                            key=f"dl_run_{r['id']}",
                        )

    except Exception as e:
        st.warning(f"Could not connect to DB: {e}")
