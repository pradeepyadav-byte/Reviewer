from pathlib import Path
from io import BytesIO
from typing import Optional

import pandas as pd
import streamlit as st


RATING_COLUMNS = {
    "context_relevance_rating": "Context & Relevance",
    "emotionx_usage_rating": "EmotionX Usage",
    "language_alignment_rating": "Language Alignment",
    "safety_alignment_rating": "Safety Alignment",
}
RATING_MEANINGS = {1: "Very poor", 2: "Poor", 3: "Average", 4: "Good", 5: "Excellent"}

REVIEW_COLUMNS = [
    "review_choice",
    "final_response",
    *RATING_COLUMNS.keys(),
    "reviewer_notes",
    "reviewed_status",
]
COLUMN_MAPPING_VERSION = 2


def display_text(value) -> str:
    """Render empty pandas cells as blank text instead of 'nan'."""
    if pd.isna(value):
        return ""
    return str(value)


def rating_from_feedback(value) -> Optional[int]:
    """Convert Streamlit's zero-based star selection to a persisted 1–5 rating."""
    if value is None or value == "":
        return None
    return int(value) + 1


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
    """Add review columns and keep text and numeric ratings in suitable dtypes."""
    for col in REVIEW_COLUMNS:
        if col in RATING_COLUMNS:
            if col not in df.columns:
                df[col] = pd.Series(pd.NA, index=df.index, dtype="Int64")
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
            continue
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].map(display_text)
        df[col] = df[col].astype("object")
    return df


def clear_review_widget_state() -> None:
    """Clear per-row review widget state when a new upload is loaded."""
    prefixes = (
        "choice_",
        "notes_",
        "final_",
        "context_",
        "emotionx_",
        "language_",
        "safety_",
        "select_response_col_",
        "response_display_name_",
    )
    for key in list(st.session_state.keys()):
        if key.startswith(prefixes):
            del st.session_state[key]
    for key in (
        "select_prompt_col",
        "select_category_col",
    ):
        st.session_state.pop(key, None)
    st.session_state.response_column_count = 2
    st.session_state.response_columns = []
    st.session_state.response_display_names = {}
    st.session_state.columns_confirmed = False
    st.session_state.column_mapping_version = COLUMN_MAPPING_VERSION
    st.session_state.pop("jump_to_row", None)


def reset_column_confirmation() -> None:
    """Require reconfirmation after a mapped column name changes."""
    st.session_state.columns_confirmed = False


def navigate_to_row(row_index: int, max_index: int) -> None:
    """Keep navigation buttons and the jump slider on the same row."""
    new_index = min(max(int(row_index), 0), max_index)
    st.session_state.current_index = new_index
    st.session_state.jump_to_row = new_index


def apply_jump_to_row() -> None:
    """Apply the jump slider value to the active review row."""
    st.session_state.current_index = int(st.session_state.jump_to_row)


def find_likely_column(
    df: pd.DataFrame,
    candidates: list[str],
    excluded: Optional[set[str]] = None,
) -> str:
    """Return the first likely uploaded column name for an editable mapping input."""
    excluded = excluded or set()
    columns_by_name = {str(column).strip().lower(): str(column) for column in df.columns}
    for candidate in candidates:
        match = columns_by_name.get(candidate.lower())
        if match and match not in excluded:
            return match
    return ""


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
    context_key: str,
    emotionx_key: str,
    language_key: str,
    safety_key: str,
    response_values: Optional[dict[str, str]] = None,
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

    default_responses = dict(response_values or {})
    default_responses["All responses are bad"] = ""
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
    criteria_keys = {
        "context_relevance_rating": context_key,
        "emotionx_usage_rating": emotionx_key,
        "language_alignment_rating": language_key,
        "safety_alignment_rating": safety_key,
    }
    for column, key in criteria_keys.items():
        rating = rating_from_feedback(st.session_state.get(key))
        df_review.at[row_index, column] = rating if rating is not None else pd.NA

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

    if "df_review" not in st.session_state:
        st.session_state.df_review = None
    if "df_original" not in st.session_state:
        st.session_state.df_original = None

    if "current_index" not in st.session_state:
        st.session_state.current_index = 0

    if "col_prompt" not in st.session_state:
        st.session_state.col_prompt = None
    if "response_columns" not in st.session_state:
        st.session_state.response_columns = []
    if "response_display_names" not in st.session_state:
        st.session_state.response_display_names = {}
    if "response_column_count" not in st.session_state:
        st.session_state.response_column_count = 2
    if "columns_confirmed" not in st.session_state:
        st.session_state.columns_confirmed = False
    if st.session_state.get("column_mapping_version") != COLUMN_MAPPING_VERSION:
        for key in list(st.session_state.keys()):
            if key.startswith(("select_response_col_", "response_display_name_")):
                del st.session_state[key]
        for key in ("select_prompt_col", "select_category_col"):
            st.session_state.pop(key, None)
        st.session_state.response_column_count = 2
        st.session_state.response_columns = []
        st.session_state.response_display_names = {}
        st.session_state.columns_confirmed = False
        st.session_state.column_mapping_version = COLUMN_MAPPING_VERSION
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

    st.title("Evaluation" if st.session_state.columns_confirmed else "Response Review Dashboard")

    # ------------------ Upload ------------------
    uploaded = None
    if not st.session_state.columns_confirmed:
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
    if st.session_state.autosave_status and not st.session_state.columns_confirmed:
        st.caption(st.session_state.autosave_status)

    if not st.session_state.columns_confirmed:
        # ------------------ Column selection ------------------
        st.subheader("2) Map your columns")
        st.session_state.response_column_count = 2
        available_columns = list(st.session_state.df_original.columns)
        st.markdown("**Available columns in the uploaded file**")
        st.dataframe(
            pd.DataFrame({"Column name": [str(column) for column in available_columns]}),
            width="stretch",
            hide_index=True,
        )

        suggested_prompt = find_likely_column(
            st.session_state.df_original,
            ["user", "user_prompt", "prompt", "question", "instruction", "query"],
        )
        suggested_prompt_column = next(
            (column for column in available_columns if str(column) == suggested_prompt),
            None,
        )
        column_options = [None, *available_columns]
        col_prompt = st.selectbox(
            "User Prompt Column (required)",
            options=column_options,
            index=column_options.index(suggested_prompt_column),
            format_func=lambda column: "Select a column" if column is None else str(column),
            key="select_prompt_col",
            on_change=reset_column_confirmation,
        )

        suggested_response_1 = find_likely_column(
            st.session_state.df_original,
            [
                "assistant(chosen)",
                "assistant_chosen",
                "assistant",
                "chatgpt",
                "gemma",
                "response",
                "model_response",
            ],
        )
        suggested_response_2 = find_likely_column(
            st.session_state.df_original,
            [
                "assistant(rejected)",
                "assistant_rejected",
                "gemma",
                "chatgpt",
                "assistant",
                "other_response",
            ],
            excluded={suggested_response_1},
        )
        suggested_responses = [suggested_response_1, suggested_response_2]

        response_columns = []
        response_display_names = []
        for response_number in range(st.session_state.response_column_count):
            suggested_name = (
                suggested_responses[response_number]
                if response_number < len(suggested_responses)
                else ""
            )
            suggested_column = next(
                (column for column in available_columns if str(column) == suggested_name),
                None,
            )
            response_mapping_cols = st.columns(2)
            with response_mapping_cols[0]:
                response_column = st.selectbox(
                    f"Response Column {response_number + 1}",
                    options=column_options,
                    index=column_options.index(suggested_column),
                    format_func=lambda column: "Select a column" if column is None else str(column),
                    key=f"select_response_col_{response_number}",
                    on_change=reset_column_confirmation,
                )
            with response_mapping_cols[1]:
                display_name = st.text_input(
                    f"Display name for Response {response_number + 1}",
                    value=str(suggested_column) if suggested_column is not None else "",
                    key=f"response_display_name_{response_number}",
                    on_change=reset_column_confirmation,
                    placeholder="Example: Gemma Response",
                ).strip()
            response_columns.append(response_column)
            response_display_names.append(display_name)

        def validate_mapping() -> list[str]:
            errors = []
            selected_responses = [column for column in response_columns if column is not None]
            selected_display_names = [
                response_display_names[index]
                for index, column in enumerate(response_columns)
                if column is not None
            ]
            if col_prompt is None:
                errors.append("Select a User Prompt Column.")
            if len(selected_responses) < 2:
                errors.append("Select at least two response columns before starting evaluation.")
            if len(selected_responses) != len(set(selected_responses)):
                errors.append("Duplicate response column selections are not allowed.")
            if any(not name for name in selected_display_names):
                errors.append("Give every selected response column a display name.")
            if len(selected_display_names) != len(set(selected_display_names)):
                errors.append("Response display names must be unique.")
            return errors

        if st.button("Start Evaluation", type="primary"):
            mapping_errors = validate_mapping()
            if mapping_errors:
                for error in mapping_errors:
                    st.error(error)
            else:
                st.session_state.col_prompt = col_prompt
                st.session_state.response_columns = [
                    column for column in response_columns if column is not None
                ]
                st.session_state.response_display_names = {
                    column: response_display_names[index]
                    for index, column in enumerate(response_columns)
                    if column is not None
                }
                st.session_state.columns_confirmed = True
                st.rerun()

        if not st.session_state.columns_confirmed:
            st.info("Confirm the two response columns, then click Start Evaluation.")
            return

        st.success("Columns confirmed. You can continue reviewing below.")

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
    if "jump_to_row" not in st.session_state:
        st.session_state.jump_to_row = int(st.session_state.current_index)
    st.session_state.jump_to_row = min(
        max(int(st.session_state.jump_to_row), 0),
        max_index,
    )
    nav_cols = st.columns([1, 1, 1])

    with nav_cols[0]:
        st.button(
            "← Previous",
            disabled=st.session_state.current_index <= 0,
            on_click=navigate_to_row,
            args=(st.session_state.current_index - 1, max_index),
        )

    with nav_cols[1]:
        st.slider(
            "Jump to row",
            min_value=0,
            max_value=max_index,
            step=1,
            key="jump_to_row",
            on_change=apply_jump_to_row,
        )

    with nav_cols[2]:
        st.button(
            "Next →",
            disabled=st.session_state.current_index >= max_index,
            on_click=navigate_to_row,
            args=(st.session_state.current_index + 1, max_index),
        )

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
    response_values = {
        st.session_state.response_display_names.get(column, str(column)): display_text(
            df_review.iloc[idx][column]
        )
        for column in st.session_state.response_columns
    }
    # Display side-by-side responses
    st.markdown("**User prompt**")
    st.write(prompt_val)

    st.markdown("**Responses**")
    response_display_cols = st.columns(min(len(response_values), 3))
    for response_number, (column, response_value) in enumerate(response_values.items()):
        with response_display_cols[response_number % len(response_display_cols)]:
            st.markdown(f"### {column}")
            st.write(response_value)

    # ---- Inputs for selection + final response ----
    st.markdown("**Choose the better response**")

    existing_choice = display_text(df_review.iloc[idx]["review_choice"]) if "review_choice" in df_review.columns else ""
    existing_final = display_text(df_review.iloc[idx]["final_response"]) if "final_response" in df_review.columns else ""
    existing_notes = display_text(df_review.iloc[idx]["reviewer_notes"]) if "reviewer_notes" in df_review.columns else ""
    existing_criteria = {
        column: df_review.iloc[idx][column] for column in RATING_COLUMNS
    }

    choice_options = [
        *response_values.keys(),
        "All responses are bad",
        "Needs manual edit",
    ]

    # Set defaults based on existing data.
    # For rows without saved data, default to the first mapped response.
    if existing_choice in choice_options:
        default_choice = existing_choice
    else:
        default_choice = next(iter(response_values))

    # Put choice in a stable session key per index so switching rows restores state.
    choice_key = f"choice_{idx}"
    notes_key = f"notes_{idx}"
    final_key = f"final_{idx}"
    context_key = f"context_rating_{idx}"
    emotionx_key = f"emotionx_rating_{idx}"
    language_key = f"language_rating_{idx}"
    safety_key = f"safety_rating_{idx}"
    radio_key = f"{choice_key}_radio"
    row_index = df_review.index[idx]
    criteria_keys = {
        "context_relevance_rating": context_key,
        "emotionx_usage_rating": emotionx_key,
        "language_alignment_rating": language_key,
        "safety_alignment_rating": safety_key,
    }

    # Initialize widget-backed session values BEFORE widget instantiation.
    # IMPORTANT: Do not reassign these keys after the widgets are created.
    # Initialize only the widget values we need *before* widget creation.
    # Use setdefault-like logic without modifying the state dict during reruns.
    if choice_key not in st.session_state or st.session_state[choice_key] not in choice_options:
        st.session_state[choice_key] = default_choice
    if notes_key not in st.session_state:
        st.session_state[notes_key] = existing_notes
    if final_key not in st.session_state:
        if is_reviewed:
            st.session_state[final_key] = existing_final
        else:
            st.session_state[final_key] = response_values.get(default_choice, "")
    if radio_key not in st.session_state or st.session_state[radio_key] not in choice_options:
        st.session_state[radio_key] = st.session_state[choice_key]
    for column, key in criteria_keys.items():
        if key not in st.session_state:
            saved_value = existing_criteria[column]
            try:
                numeric_rating = int(saved_value)
            except (TypeError, ValueError):
                numeric_rating = 0
            st.session_state[key] = numeric_rating - 1 if 1 <= numeric_rating <= 5 else None

    draft_callback_args = (
        row_index,
        choice_key,
        final_key,
        notes_key,
        context_key,
        emotionx_key,
        language_key,
        safety_key,
        response_values,
    )


    # Radio widget (selected value returned directly; no session assignment after instantiation)
    selected_choice = st.radio(
        "Selection",
        options=choice_options,
        index=choice_options.index(st.session_state[radio_key]),
        key=radio_key,
        help="Select the best response column or indicate that manual editing is needed.",
        on_change=persist_review_draft,
        args=draft_callback_args,
    )

    final_response_text = st.text_area(
        "Final response (editable)",
        key=final_key,
        height=180,
        on_change=persist_review_draft,
        args=draft_callback_args,
    )

    st.markdown("**Review criteria**")

    def star_rating(label: str, key: str) -> Optional[int]:
        st.markdown(f"**{label}**")
        selection = st.feedback(
            "stars",
            key=key,
            on_change=persist_review_draft,
            args=draft_callback_args,
        )
        rating = rating_from_feedback(selection)
        st.caption(RATING_MEANINGS[rating] if rating is not None else "Not rated")
        return rating

    criteria_cols = st.columns(4)
    with criteria_cols[0]:
        context_relevance_rating = star_rating("Context & Relevance", context_key)
    with criteria_cols[1]:
        emotionx_usage_rating = star_rating("EmotionX Usage", emotionx_key)
    with criteria_cols[2]:
        language_alignment_rating = star_rating("Language Alignment", language_key)
    with criteria_cols[3]:
        safety_alignment_rating = star_rating("Safety Alignment", safety_key)

    reviewer_notes = st.text_area(
        "Reviewer notes (optional)",
        height=120,
        key=notes_key,
        on_change=persist_review_draft,
        args=draft_callback_args,
    )


    # Save button
    save_disabled = False
    if selected_choice != "All responses are bad" and not display_text(final_response_text).strip() and selected_choice != "Needs manual edit":
        # Empty output is valid only when all responses are rejected or a manual edit is pending.
        # But also enforce reasonable validation for automatic choices.
        save_disabled = True

    if st.button("Save current row", type="primary", disabled=save_disabled):
        # Validation
        if selected_choice not in {"All responses are bad", "Needs manual edit"} and not display_text(final_response_text).strip():
            st.error("Final response should not be empty for the selected response column.")
            return

        st.session_state.df_review.at[df_review.index[idx], "review_choice"] = selected_choice

        st.session_state.df_review.at[df_review.index[idx], "final_response"] = display_text(final_response_text)
        st.session_state.df_review.at[df_review.index[idx], "reviewer_notes"] = display_text(reviewer_notes)
        st.session_state.df_review.at[df_review.index[idx], "context_relevance_rating"] = context_relevance_rating if context_relevance_rating is not None else pd.NA
        st.session_state.df_review.at[df_review.index[idx], "emotionx_usage_rating"] = emotionx_usage_rating if emotionx_usage_rating is not None else pd.NA
        st.session_state.df_review.at[df_review.index[idx], "language_alignment_rating"] = language_alignment_rating if language_alignment_rating is not None else pd.NA
        st.session_state.df_review.at[df_review.index[idx], "safety_alignment_rating"] = safety_alignment_rating if safety_alignment_rating is not None else pd.NA
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
    cols_to_preview = [c for c in REVIEW_COLUMNS if c in df_to_download.columns]
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
