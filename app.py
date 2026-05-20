from pathlib import Path
from io import BytesIO
from typing import List, Optional

import pandas as pd
import streamlit as st


REVIEW_COLUMNS = ["review_choice", "final_response", "reviewer_notes", "reviewed_status"]


def display_text(value) -> str:
    """Render empty pandas cells as blank text instead of 'nan'."""
    if pd.isna(value):
        return ""
    return str(value)


def load_dataframe(uploaded_file) -> pd.DataFrame:
    """Load CSV/XLS/XLSX into a pandas DataFrame."""
    filename = uploaded_file.name.lower()

    # Read file into memory first so Streamlit's UploadedFile can be re-used
    data = uploaded_file.read()
    bio = BytesIO(data)

    if filename.endswith(".csv"):
        return pd.read_csv(bio)

    # For Excel use pandas + openpyxl for xlsx.
    # pandas will choose appropriate engine for xls/xlsx.
    return pd.read_excel(bio)


def ensure_review_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add review columns if missing and keep them writable as text."""
    for col in REVIEW_COLUMNS:
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].map(display_text)
        df[col] = df[col].astype("object")
    return df


def clear_review_widget_state() -> None:
    """Clear per-row review widget state when a new upload is loaded."""
    prefixes = ("choice_", "notes_", "final_")
    for key in list(st.session_state.keys()):
        if key.startswith(prefixes):
            del st.session_state[key]


def get_first_matching_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """Best-effort heuristic to preselect likely columns without hardcoding exact required names."""

    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def build_download_bytes(df: pd.DataFrame, fmt: str) -> bytes:
    """Create download bytes from the *current* review dataframe."""
    if fmt == "csv":
        return df.to_csv(index=False).encode("utf-8")

    if fmt == "xlsx":
        bio = BytesIO()
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            # Use an explicit sheet name for stability.
            df.to_excel(writer, index=False, sheet_name="reviewed")
        return bio.getvalue()

    raise ValueError(f"Unsupported download format: {fmt}")


def get_autosave_path(source_name: str) -> Path:
    """Return a stable autosave path for an uploaded source file."""
    stem = Path(source_name).stem or "reviewed_output"
    safe_stem = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in stem).strip()
    return Path.cwd() / f"{safe_stem or 'reviewed_output'}_autosave.xlsx"


def write_review_xlsx(df: pd.DataFrame, output_path: Path) -> None:
    """Write review data as xlsx, using a temporary file to avoid partial saves."""
    tmp_path = output_path.with_suffix(".tmp.xlsx")
    with pd.ExcelWriter(tmp_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="reviewed")
    tmp_path.replace(output_path)


def autosave_review_data(df: pd.DataFrame, source_name: str) -> Path:
    """Persist the current review state immediately beside the app."""
    output_path = get_autosave_path(source_name)
    write_review_xlsx(df, output_path)
    return output_path


def can_restore_autosave(uploaded_df: pd.DataFrame, autosave_df: pd.DataFrame) -> bool:
    """Avoid loading an autosave that belongs to a different data shape."""
    if len(uploaded_df) != len(autosave_df):
        return False

    review_cols = set(REVIEW_COLUMNS)
    uploaded_cols = [c for c in uploaded_df.columns if c not in review_cols]
    autosave_cols = set(autosave_df.columns)
    return all(c in autosave_cols for c in uploaded_cols)


def try_restore_autosave(uploaded_df: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, Optional[Path]]:
    """Load a compatible autosave if one exists, otherwise return uploaded data."""
    autosave_path = get_autosave_path(source_name)
    if not autosave_path.exists():
        return ensure_review_columns(uploaded_df.copy()), None

    autosave_df = pd.read_excel(autosave_path)
    autosave_df = ensure_review_columns(autosave_df)
    if can_restore_autosave(uploaded_df, autosave_df):
        return autosave_df, autosave_path

    return ensure_review_columns(uploaded_df.copy()), None


def save_review_file(df: pd.DataFrame, source_name: str) -> Path:
    """Write a reviewed copy beside the app using the uploaded file's extension when possible."""
    source_path = Path(source_name)
    stem = source_path.stem or "reviewed_output"
    suffix = source_path.suffix.lower()

    if suffix not in {".csv", ".xlsx", ".xls"}:
        suffix = ".xlsx"
    elif suffix == ".xls":
        suffix = ".xlsx"

    output_path = Path.cwd() / f"{stem}_reviewed{suffix}"

    if suffix == ".csv":
        df.to_csv(output_path, index=False)
    else:
        write_review_xlsx(df, output_path)

    return output_path



def compute_progress(reviewed_series: pd.Series) -> tuple[int, int, float]:
    total = len(reviewed_series)
    reviewed = int((reviewed_series == "Reviewed").sum())
    pct = (reviewed / total * 100.0) if total else 0.0
    return reviewed, total, pct


def persist_review_draft(
    row_index,
    choice_key: str,
    final_key: str,
    notes_key: str,
    assistant_val: str = "",
    gemma_val: str = "",
) -> None:
    """Keep in-progress edits when Streamlit reruns or the user switches rows."""
    df_review = st.session_state.get("df_review")
    if df_review is None or row_index not in df_review.index:
        return
    df_review = ensure_review_columns(df_review)
    st.session_state.df_review = df_review

    radio_key = f"{choice_key}_radio"
    previous_choice = st.session_state.get(choice_key, "")
    selected_choice = st.session_state.get(radio_key, st.session_state.get(choice_key, ""))
    final_response = display_text(st.session_state.get(final_key, ""))

    default_responses = {
        "Assistant is better": display_text(assistant_val),
        "Gemma is better": display_text(gemma_val),
        "Both are bad": "",
    }
    previous_default = default_responses.get(previous_choice)
    if selected_choice != previous_choice and (
        not final_response.strip() or final_response == previous_default
    ):
        final_response = default_responses.get(selected_choice, final_response)
        st.session_state[final_key] = final_response

    st.session_state[choice_key] = selected_choice

    df_review.at[row_index, "review_choice"] = str(selected_choice)
    df_review.at[row_index, "final_response"] = final_response
    df_review.at[row_index, "reviewer_notes"] = display_text(st.session_state.get(notes_key, ""))

    source_name = st.session_state.get("loaded_file_name")
    if source_name:
        try:
            autosave_path = autosave_review_data(df_review, source_name)
        except Exception as e:
            st.session_state.autosave_status = f"Autosave failed: {e}"
        else:
            st.session_state.autosave_status = f"Autosaved to {autosave_path.name}"


def main():
    st.set_page_config(page_title="Response Review Dashboard", layout="wide")
    st.title("Response Review Dashboard")

    if "df_review" not in st.session_state:
        st.session_state.df_review = None
    if "df_original" not in st.session_state:
        st.session_state.df_original = None

    if "current_index" not in st.session_state:
        st.session_state.current_index = 0

    if "col_prompt" not in st.session_state:
        st.session_state.col_prompt = None
    if "col_assistant" not in st.session_state:
        st.session_state.col_assistant = None
    if "col_gemma" not in st.session_state:
        st.session_state.col_gemma = None
    if "col_category" not in st.session_state:
        st.session_state.col_category = None

    if "rows_loaded" not in st.session_state:
        st.session_state.rows_loaded = False
    if "loaded_file_name" not in st.session_state:
        st.session_state.loaded_file_name = None
    if "loaded_file_size" not in st.session_state:
        st.session_state.loaded_file_size = None
    if "autosave_path" not in st.session_state:
        st.session_state.autosave_path = None
    if "autosave_status" not in st.session_state:
        st.session_state.autosave_status = ""

    # ------------------ Upload ------------------
    st.subheader("1) Upload data")
    uploaded = st.file_uploader(
        "Upload a CSV, XLSX, or XLS file",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=False,
    )

    if uploaded is not None:
        try:
            current_file_name = uploaded.name
            current_file_size = uploaded.size
            is_new_upload = (
                st.session_state.df_review is None
                or not st.session_state.rows_loaded
                or st.session_state.loaded_file_name != current_file_name
                or st.session_state.loaded_file_size != current_file_size
            )

            df = load_dataframe(uploaded) if is_new_upload else None
        except Exception as e:
            st.error(f"Failed to read the uploaded file: {e}")
            return

        if is_new_upload:
            if df is None or df.empty:
                st.error("Uploaded file contains no data.")
                return

            clear_review_widget_state()

            try:
                df_review, restored_path = try_restore_autosave(df, current_file_name)
            except Exception as e:
                st.warning(f"Could not restore autosave, starting from uploaded file: {e}")
                df_review = ensure_review_columns(df.copy())
                restored_path = None

            st.session_state.df_original = df.copy()
            st.session_state.df_review = df_review
            st.session_state.current_index = 0
            st.session_state.rows_loaded = True
            st.session_state.loaded_file_name = current_file_name
            st.session_state.loaded_file_size = current_file_size
            st.session_state.autosave_path = get_autosave_path(current_file_name)

            if restored_path is not None:
                st.session_state.autosave_status = f"Restored autosave from {restored_path.name}"
                st.success(f"Restored autosaved review with {len(df_review)} rows.")
            else:
                try:
                    autosave_path = autosave_review_data(df_review, current_file_name)
                except Exception as e:
                    st.session_state.autosave_status = f"Autosave failed: {e}"
                    st.warning(f"Loaded {len(df)} rows, but initial autosave failed: {e}")
                else:
                    st.session_state.autosave_status = f"Autosaved to {autosave_path.name}"
                    st.success(f"Loaded {len(df)} rows and {len(df.columns)} columns.")

            st.subheader("Preview")
            st.dataframe(df_review.head(50), width="stretch", hide_index=True)
        else:
            st.caption(f"Continuing review for `{current_file_name}`.")


    # If no data loaded yet, stop here.
    if not st.session_state.rows_loaded or st.session_state.df_review is None:
        st.info("Upload a file to start reviewing.")
        return

    df_review = st.session_state.df_review
    df_review = ensure_review_columns(df_review)
    st.session_state.df_review = df_review
    if st.session_state.autosave_status:
        st.caption(st.session_state.autosave_status)

    # ------------------ Column selection ------------------
    st.subheader("2) Map your columns")
    cols = [str(c) for c in df_review.columns]

    # Optional preselection heuristics (without requiring those names)
    pre_prompt = get_first_matching_column(
        df_review,
        ["prompt", "user_prompt", "question", "instruction", "query"],
    )
    pre_assistant = get_first_matching_column(
        df_review,
        ["assistant", "assistant_response", "response", "model_response", "final"],
    )
    pre_gemma = get_first_matching_column(
        df_review,
        ["gemma", "gemma_response", "other_response"],
    )
    pre_category = get_first_matching_column(
        df_review,
        ["problem", "category", "tag", "type", "domain"],
    )

    col_prompt = st.selectbox(
        "User prompt column (required)",
        options=cols,
        index=cols.index(pre_prompt) if pre_prompt in cols else 0,
        key="select_prompt_col",
    )

    col_assistant = st.selectbox(
        "Assistant response column (required)",
        options=cols,
        index=cols.index(pre_assistant) if pre_assistant in cols else min(1, len(cols) - 1),
        key="select_assistant_col",
    )

    col_gemma = st.selectbox(
        "Gemma response column (required)",
        options=cols,
        index=cols.index(pre_gemma) if pre_gemma in cols else min(2, len(cols) - 1),
        key="select_gemma_col",
    )

    # Ensure we don't treat it as required.
    category_options = ["(None)"] + cols
    category_default = pre_category if pre_category in cols else "(None)"
    category_index = category_options.index(category_default)

    col_category_opt = st.selectbox(
        "Problem/Category column (optional)",
        options=category_options,
        index=category_index,
        key="select_category_col",
    )
    col_category = None if col_category_opt == "(None)" else col_category_opt

    # Save selected mappings to session
    st.session_state.col_prompt = col_prompt
    st.session_state.col_assistant = col_assistant
    st.session_state.col_gemma = col_gemma
    st.session_state.col_category = col_category

    required_mapped = all([st.session_state.col_prompt, st.session_state.col_assistant, st.session_state.col_gemma])
    if not required_mapped:
        st.error("Required columns must be selected.")
        return

    # ------------------ Progress tracking ------------------
    reviewed_count, total_rows, pct = compute_progress(df_review["reviewed_status"])
    st.subheader("3) Progress")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Reviewed", f"{reviewed_count}/{total_rows}")
    with c2:
        st.metric("Total", f"{total_rows}")
    with c3:
        st.metric("Complete", f"{pct:.1f}%")
    st.progress(min(max(pct / 100.0, 0.0), 1.0))

    # ------------------ Review interface ------------------
    st.subheader("4) Review")

    # Navigation controls
    max_index = max(total_rows - 1, 0)
    nav_cols = st.columns([1, 1, 1])

    with nav_cols[0]:
        if st.button("← Previous", disabled=st.session_state.current_index <= 0):
            st.session_state.current_index = max(st.session_state.current_index - 1, 0)

    with nav_cols[1]:
        target = st.slider(
            "Jump to row",
            min_value=0,
            max_value=max_index,
            value=int(st.session_state.current_index),
            step=1,
        )
        st.session_state.current_index = target

    with nav_cols[2]:
        if st.button("Next →", disabled=st.session_state.current_index >= max_index):
            st.session_state.current_index = min(st.session_state.current_index + 1, max_index)

    idx = int(st.session_state.current_index)
    row_num_display = idx + 1
    reviewed_status = display_text(df_review.iloc[idx]["reviewed_status"]) if "reviewed_status" in df_review.columns else ""
    is_reviewed = reviewed_status == "Reviewed"

    st.write(f"Row **{row_num_display} / {total_rows}**")
    if is_reviewed:
        st.success("This row is already reviewed.")
    else:
        st.info("This row is not reviewed yet.")

    # Retrieve row content
    prompt_val = display_text(df_review.iloc[idx][st.session_state.col_prompt])
    assistant_val = display_text(df_review.iloc[idx][st.session_state.col_assistant])
    gemma_val = display_text(df_review.iloc[idx][st.session_state.col_gemma])
    category_val = None
    if st.session_state.col_category is not None:
        category_val = df_review.iloc[idx][st.session_state.col_category]

    # Display side-by-side responses
    st.markdown("**User prompt**")
    st.write(prompt_val)

    if category_val is not None:
        st.markdown("**Problem/Category**")
        st.write(display_text(category_val))

    st.markdown("**Responses**")
    resp_cols = st.columns(2)
    with resp_cols[0]:
        st.markdown("### Assistant")
        st.write(assistant_val)

    with resp_cols[1]:
        st.markdown("### Gemma")
        st.write(gemma_val)

    # ---- Inputs for selection + final response ----
    st.markdown("**Choose the better response**")

    existing_choice = display_text(df_review.iloc[idx]["review_choice"]) if "review_choice" in df_review.columns else ""
    existing_final = display_text(df_review.iloc[idx]["final_response"]) if "final_response" in df_review.columns else ""
    existing_notes = display_text(df_review.iloc[idx]["reviewer_notes"]) if "reviewer_notes" in df_review.columns else ""

    choice_options = [
        "Assistant is better",
        "Gemma is better",
        "Both are bad",
        "Needs manual edit",
    ]

    # Set defaults based on existing data.
    # For rows without saved data, default to Assistant is better with prefill.
    if existing_choice in choice_options:
        default_choice = existing_choice
    else:
        default_choice = "Assistant is better"

    # Put choice in a stable session key per index so switching rows restores state.
    choice_key = f"choice_{idx}"
    notes_key = f"notes_{idx}"
    final_key = f"final_{idx}"
    radio_key = f"{choice_key}_radio"
    row_index = df_review.index[idx]

    # Initialize widget-backed session values BEFORE widget instantiation.
    # IMPORTANT: Do not reassign these keys after the widgets are created.
    # Initialize only the widget values we need *before* widget creation.
    # Use setdefault-like logic without modifying the state dict during reruns.
    if choice_key not in st.session_state:
        st.session_state[choice_key] = default_choice
    if notes_key not in st.session_state:
        st.session_state[notes_key] = existing_notes
    if final_key not in st.session_state:
        if is_reviewed:
            st.session_state[final_key] = existing_final
        else:
            st.session_state[final_key] = gemma_val if default_choice == "Gemma is better" else assistant_val
    if radio_key not in st.session_state:
        st.session_state[radio_key] = st.session_state[choice_key]


    # Radio widget (selected value returned directly; no session assignment after instantiation)
    selected_choice = st.radio(
        "Selection",
        options=choice_options,
        index=choice_options.index(st.session_state[radio_key]),
        key=radio_key,
        help="Select which response is better or if manual editing is needed.",
        on_change=persist_review_draft,
        args=(row_index, choice_key, final_key, notes_key, assistant_val, gemma_val),
    )

    final_response_text = st.text_area(
        "Final response (editable)",
        key=final_key,
        height=180,
        on_change=persist_review_draft,
        args=(row_index, choice_key, final_key, notes_key, assistant_val, gemma_val),
    )


    reviewer_notes = st.text_area(
        "Reviewer notes (optional)",
        height=120,
        key=notes_key,
        on_change=persist_review_draft,
        args=(row_index, choice_key, final_key, notes_key, assistant_val, gemma_val),
    )


    # Save button
    save_disabled = False
    if selected_choice != "Both are bad" and not display_text(final_response_text).strip() and selected_choice != "Needs manual edit":
        # Requirement only explicitly forbids empty when saving for Both are bad.
        # But also enforce reasonable validation for automatic choices.
        save_disabled = True

    if st.button("Save current row", type="primary", disabled=save_disabled):
        # Validation
        if selected_choice != "Both are bad" and not display_text(final_response_text).strip():
            st.error("Final response should not be empty for the selected option (except 'Both are bad').")
            return

        st.session_state.df_review.at[df_review.index[idx], "review_choice"] = selected_choice

        st.session_state.df_review.at[df_review.index[idx], "final_response"] = display_text(final_response_text)
        st.session_state.df_review.at[df_review.index[idx], "reviewer_notes"] = display_text(reviewer_notes)
        st.session_state.df_review.at[df_review.index[idx], "reviewed_status"] = "Reviewed"

        try:
            autosave_path = autosave_review_data(
                st.session_state.df_review,
                st.session_state.loaded_file_name or "reviewed_output.xlsx",
            )
        except Exception as e:
            st.session_state.autosave_status = f"Autosave failed: {e}"
            st.error(f"Saved in this session, but autosave failed: {e}")
            return
        else:
            st.session_state.autosave_status = f"Autosaved to {autosave_path.name}"

        # Mark reviewed status as updated in local variables.
        st.success("Saved.")

        # Do not modify widget-backed session_state keys after widgets are created.


        # Rerun to refresh progress/status.
        st.rerun()

    # ------------------ Download ------------------
    st.subheader("5) Download reviewed data")

    # Always use the latest df_review in session_state as source of truth.
    df_to_download = st.session_state.df_review

    # Small confirmation preview of saved review columns.
    cols_to_preview = [c for c in ["review_choice", "final_response", "reviewer_notes", "reviewed_status"] if c in df_to_download.columns]
    if cols_to_preview:
        preview_cols = st.columns([1, 1])
        with preview_cols[0]:
            preview_scope = st.selectbox(
                "Preview rows",
                options=["First 20 rows", "All rows", "Reviewed rows", "Unreviewed rows"],
                key="download_preview_scope",
            )
        with preview_cols[1]:
            preview_columns = st.radio(
                "Preview columns",
                options=["Review fields only", "All columns"],
                horizontal=True,
                key="download_preview_columns",
            )

        if preview_scope == "All rows":
            df_preview = df_to_download
        elif preview_scope == "Reviewed rows":
            df_preview = df_to_download[df_to_download["reviewed_status"] == "Reviewed"]
        elif preview_scope == "Unreviewed rows":
            df_preview = df_to_download[df_to_download["reviewed_status"] != "Reviewed"]
        else:
            df_preview = df_to_download.head(20)

        if preview_columns == "Review fields only":
            df_preview = df_preview[cols_to_preview]

        st.caption(f"Preview showing {len(df_preview)} row(s). Downloads still include all {len(df_to_download)} row(s).")
        st.dataframe(df_preview, use_container_width=True, hide_index=True)

    dl_cols = st.columns(2)

    with dl_cols[0]:
        csv_bytes = build_download_bytes(df_to_download, "csv")
        st.download_button(
            label="Download CSV",
            data=csv_bytes,
            file_name="reviewed_output.csv",
            mime="text/csv",
        )

    with dl_cols[1]:
        xlsx_bytes = build_download_bytes(df_to_download, "xlsx")
        st.download_button(
            label="Download Excel (.xlsx)",
            data=xlsx_bytes,
            file_name="reviewed_output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    if st.button("Save reviewed copy in this folder"):
        try:
            output_path = save_review_file(df_to_download, st.session_state.loaded_file_name or "reviewed_output.xlsx")
        except Exception as e:
            st.error(f"Failed to save reviewed copy: {e}")
        else:
            st.success(f"Saved reviewed copy to {output_path}")


    # ------------------ Optional LLM Judge Check placeholder ------------------
    st.subheader("6) LLM Judge Check")
    st.caption("Placeholder UI only. No real API call is performed.")

    guidelines = st.text_area(
        "Guidelines for LLM Judge Check",
        value="",
        height=140,
        key="judge_guidelines",
    )

    if st.button("Check Final Response"):
        st.info("API integration can be added later.")


if __name__ == "__main__":
    main()
