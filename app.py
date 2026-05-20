import io
from pathlib import Path
from io import BytesIO
from typing import List, Optional, Tuple

import pandas as pd
import streamlit as st



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
    """Add review columns if missing."""
    for col in ["review_choice", "final_response", "reviewer_notes", "reviewed_status"]:
        if col not in df.columns:
            df[col] = ""
    return df


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


def save_review_file(df: pd.DataFrame, source_name: str) -> Path:
    """Write a reviewed copy beside the app using the uploaded file's extension when possible."""
    source_path = Path(source_name)
    stem = source_path.stem or "reviewed_output"
    suffix = source_path.suffix.lower()

    if suffix not in {".csv", ".xlsx", ".xls"}:
        suffix = ".xlsx"

    output_path = Path.cwd() / f"{stem}_reviewed{suffix}"

    if suffix == ".csv":
        df.to_csv(output_path, index=False)
    else:
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="reviewed")

    return output_path



def compute_progress(reviewed_series: pd.Series) -> tuple[int, int, float]:
    total = len(reviewed_series)
    reviewed = int((reviewed_series == "Reviewed").sum())
    pct = (reviewed / total * 100.0) if total else 0.0
    return reviewed, total, pct


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

            st.session_state.df_original = df.copy()
            st.session_state.df_review = ensure_review_columns(df.copy())
            st.session_state.current_index = 0
            st.session_state.rows_loaded = True
            st.session_state.loaded_file_name = current_file_name
            st.session_state.loaded_file_size = current_file_size

            st.success(f"Loaded {len(df)} rows and {len(df.columns)} columns.")

            st.subheader("Preview")
            st.dataframe(df.head(50), width="stretch", hide_index=True)
        else:
            st.caption(f"Continuing review for `{current_file_name}`.")


    # If no data loaded yet, stop here.
    if not st.session_state.rows_loaded or st.session_state.df_review is None:
        st.info("Upload a file to start reviewing.")
        return

    df_review = st.session_state.df_review

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
        ["gaming", "gemma", "gemma_response", "gaming_response", "other_response"],
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
        "Gaming/Gemma response column (required)",
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
    reviewed_status = str(df_review.iloc[idx]["reviewed_status"]) if "reviewed_status" in df_review.columns else ""
    is_reviewed = reviewed_status == "Reviewed"

    st.write(f"Row **{row_num_display} / {total_rows}**")
    if is_reviewed:
        st.success("This row is already reviewed.")
    else:
        st.info("This row is not reviewed yet.")

    # Retrieve row content
    prompt_val = str(df_review.iloc[idx][st.session_state.col_prompt])
    assistant_val = str(df_review.iloc[idx][st.session_state.col_assistant])
    gemma_val = str(df_review.iloc[idx][st.session_state.col_gemma])
    category_val = None
    if st.session_state.col_category is not None:
        category_val = df_review.iloc[idx][st.session_state.col_category]

    # Display side-by-side responses
    st.markdown("**User prompt**")
    st.write(prompt_val)

    if category_val is not None:
        st.markdown("**Problem/Category**")
        st.write(str(category_val))

    st.markdown("**Responses**")
    resp_cols = st.columns(2)
    with resp_cols[0]:
        st.markdown("### Assistant")
        st.write(assistant_val)

    with resp_cols[1]:
        st.markdown("### Gaming/Gemma")
        st.write(gemma_val)

    # ---- Inputs for selection + final response ----
    st.markdown("**Choose the better response**")

    existing_choice = str(df_review.iloc[idx]["review_choice"]) if "review_choice" in df_review.columns else ""
    existing_final = str(df_review.iloc[idx]["final_response"]) if "final_response" in df_review.columns else ""
    existing_notes = str(df_review.iloc[idx]["reviewer_notes"]) if "reviewer_notes" in df_review.columns else ""

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


    # Radio widget (selected value returned directly; no session assignment after instantiation)
    selected_choice = st.radio(
        "Selection",
        options=choice_options,
        index=choice_options.index(st.session_state[choice_key]),
        key=choice_key + "_radio",
        help="Select which response is better or if manual editing is needed.",
    )

    # Prefill logic happens BEFORE creating the widget.
    # (Do not mutate st.session_state[final_key] after st.text_area is instantiated.)
    if not is_reviewed:
        if selected_choice == "Assistant is better" and not str(existing_final).strip():
            st.session_state[final_key] = assistant_val
        elif selected_choice == "Gemma is better" and not str(existing_final).strip():
            st.session_state[final_key] = gemma_val
        elif selected_choice == "Both are bad" and not str(existing_final).strip():
            st.session_state[final_key] = ""

    final_response_text = st.text_area(
        "Final response (editable)",
        key=final_key,
        height=180,
    )


    reviewer_notes = st.text_area(
        "Reviewer notes (optional)",
        value=st.session_state[notes_key],
        height=120,
        key=notes_key,
    )


    # Save button
    save_disabled = False
    if selected_choice != "Both are bad" and not str(final_response_text).strip() and selected_choice != "Needs manual edit":
        # Requirement only explicitly forbids empty when saving for Both are bad.
        # But also enforce reasonable validation for automatic choices.
        save_disabled = True

    if st.button("Save current row", type="primary", disabled=save_disabled):
        # Validation
        if selected_choice != "Both are bad" and not str(final_response_text).strip():
            st.error("Final response should not be empty for the selected option (except 'Both are bad').")
            return

        st.session_state.df_review.at[df_review.index[idx], "review_choice"] = selected_choice

        st.session_state.df_review.at[df_review.index[idx], "final_response"] = str(final_response_text)
        st.session_state.df_review.at[df_review.index[idx], "reviewer_notes"] = str(reviewer_notes)
        st.session_state.df_review.at[df_review.index[idx], "reviewed_status"] = "Reviewed"

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
