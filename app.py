from pathlib import Path
from io import BytesIO
from html import escape
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from textwrap import dedent
from typing import Optional

import pandas as pd
import streamlit as st

from mira_data import (
    RATING_COLUMNS,
    RATING_MEANINGS,
    REVIEW_COLUMNS,
    display_text,
    dynamic_rating_column,
    ensure_dynamic_rating_columns,
    ensure_review_columns,
    fetch_google_drive_file,
    load_dataframe,
    rating_from_scale,
)
from mira_theme import inject_app_theme, inject_dark_mode_theme


COLUMN_MAPPING_VERSION = 6
ORIGINAL_DATA_FILE = "original.json.gz"
REVIEW_DATA_FILE = "review.json.gz"
COLUMN_MAPPING_PAGE = None
LLM_REVIEW_PAGE = None
HOME_PAGE = None
REVIEW_PAGE = None
PROJECTS_PAGE = None
ABOUT_PAGE = None
ACCOUNT_PAGE = None
LOGOUT_PAGE = None


def render_safe_html(markup: str) -> None:
    """Render HTML without allowing Markdown to expose indented source code."""
    compact_markup = "".join(
        line.strip() for line in dedent(str(markup)).splitlines()
    )
    st.markdown(compact_markup, unsafe_allow_html=True)


def render_native_navigation(signed_in: bool, active_page: str = "") -> None:
    """Render reliable native multipage links with MIRA header styling."""
    review_destination = REVIEW_PAGE if signed_in else ACCOUNT_PAGE
    with st.container(horizontal=True, vertical_alignment="center", key="native_site_nav"):
        st.page_link(HOME_PAGE, label="MIRA", icon=":material/cloud:")
        if active_page != "about":
            st.page_link(ABOUT_PAGE, label="About", icon=":material/info:")
        st.link_button(
            "Parent Website",
            "https://www.hyperneuronai.com/",
            icon=":material/open_in_new:",
        )
        if active_page != "review" and not (active_page == "account" and not signed_in):
            st.page_link(review_destination, label="Review Workspace", icon=":material/arrow_forward:")
        if signed_in and active_page != "projects":
            st.page_link(PROJECTS_PAGE, label="Projects", icon=":material/folder_open:")
        if active_page != "account":
            st.page_link(ACCOUNT_PAGE, label="Account", icon=":material/account_circle:")


def render_page_header(evaluation_started: bool) -> None:
    """Render a contextual hero for setup and evaluation modes."""
    if evaluation_started:
        return

    auth_ready = google_auth_configured()
    signed_in = auth_ready and bool(getattr(st.user, "is_logged_in", False))
    review_href = "/review" if signed_in else "/account"
    render_native_navigation(signed_in, "home")

    # Static presentation markup; no database query is constructed here.
    landing_markup = dedent(
        """
        <main class="mira-story">
            <section class="depth-collage-hero">
                <div class="evaluation-particles" aria-hidden="true"><i class="particle-swarm one"></i><i class="particle-swarm two"></i></div>
                <div class="depth-hero-copy"><h1>The hidden depths of model evaluation</h1><p>A fluent response is only the visible surface. Beneath it lies context, language, relevance, safety and the human judgment that makes AI trustworthy.</p></div>
                <div class="depth-scroll">Scroll to evaluate deeper</div>
                <div class="depth-tag context">context</div><div class="depth-tag tone">language + tone</div><div class="depth-tag safety">safety</div><div class="depth-tag relevance">relevance</div>
            </section>
            <section class="mira-quick-pitch">
                <h2 class="quick-pitch-title">One row. Multiple responses. <span>Human signal in minutes.</span></h2>
                <div class="quick-pitch-copy"><p>Replace scattered spreadsheets with one evaluation space that keeps prompts, model outputs and human decisions connected.</p><div class="pitch-actions"><a class="pitch-link" href="#capabilities">Explore capabilities</a><a class="pitch-link primary" href="__REVIEW_HREF__"><i>→</i> Start evaluation</a></div></div>
            </section>
            <section id="evaluation-depth" class="story-section story-intro">
                <div class="story-intro-copy"><div class="story-index">01 · Beneath the output</div><h2>Fluent is not the same as <em>right.</em></h2><p class="story-copy">A response can read beautifully and still miss intent, context or cultural nuance. MIRA separates the visible answer from the signals underneath, so reviewers can turn instinct into structured evidence.</p><div class="story-proof"><span>Compare responses</span><span>Expose hidden signals</span><span>Capture human judgment</span></div></div>
                <div class="response-xray" aria-hidden="true">
                    <div class="xray-orbit"></div>
                    <div class="xray-card back"><small>Layer 03 · Decision</small>Which response genuinely serves the user?</div>
                    <div class="xray-card middle"><small>Layer 02 · Human signal</small>Intent, language, relevance and safety become reviewable evidence.</div>
                    <div class="xray-card front"><small>Layer 01 · Visible response</small><div class="xray-line medium"></div><div class="xray-line"></div><div class="xray-line short"></div><div class="xray-score"><span>Reveal evaluation depth</span><b><i></i><i></i><i></i><i></i></b></div></div>
                </div>
            </section>
            <section id="signals" class="story-section" style="padding-top:0;background:#e2f0f2;">
                <div class="evaluation-collage">
                    <div class="collage-copy"><div><small>Human review makes quality visible</small><h2>Look past the polished answer.</h2></div><p>Two responses can sound equally fluent while carrying very different levels of intent, relevance and risk. MIRA gives reviewers a place to inspect the evidence, compare alternatives and preserve the judgment behind every final choice.</p></div>
                    <div class="collage-visual" role="img" aria-label="Editorial collage of a human reviewer comparing AI model responses">
                        <span class="collage-note intent">inspect intent</span><span class="collage-note compare">compare evidence</span><span class="collage-note decide">record the decision</span>
                    </div>
                </div>
            </section>
            <section id="capabilities" class="mira-bento">
                <div class="bento-head"><h2>Everything a reviewer needs. Nothing they don’t.</h2><p>MIRA keeps the interface focused while preserving the depth required for serious model evaluation.</p></div>
                <div class="bento-grid">
                    <article class="bento-card wide"><h3>Compare every response in context</h3><p>See multiple model outputs together, select the strongest answer and preserve an editable final response.</p><div class="bento-response-stack"><div class="bento-response"><b>Response A</b>Clear intent, relevant context, natural language.</div><div class="bento-response"><b>Response B · Selected</b>Stronger alignment with the user’s actual request.</div><div class="bento-response"><b>Final response</b>Reviewer-refined and ready for export.</div></div></article>
                    <article class="bento-card"><h3>Configurable human signals</h3><p>Apply the review dimensions selected for the current evaluation project.</p><div class="rating-orbit"><i>•</i><i>•</i><i>•</i><i>•</i><i>•</i></div></article>
                    <article class="bento-card"><h3>Export-ready evidence</h3><p>Move from reviewed rows to clean data without rebuilding your work.</p><div class="export-flow"><span>Reviewed rows</span><i>→</i><span>CSV · XLSX</span></div></article>
                </div>
            </section>
            <section class="story-section story-closing">
                <div class="story-index">MIRA · Built for human signal</div>
                <h2>Make the invisible quality of a response visible.</h2>
                <a class="story-cta" href="__REVIEW_HREF__">Enter the Review Workspace →</a>
            </section>
        </main>
        """
    ).strip().replace("__REVIEW_HREF__", review_href)
    # Streamlit's Markdown parser can interpret indented HTML as a code block on
    # some mobile browsers. A compact string keeps the landing page valid HTML.
    landing_markup = "".join(line.strip() for line in landing_markup.splitlines())
    render_safe_html(landing_markup)


def render_parent_brand_portal() -> None:
    """Render a compact, clickable parent-company brand experience."""
    render_safe_html(
        """
        <div class="parent-brand-card hn-network-card">
            <div class="parent-brand-copy">
                <div class="parent-brand-kicker">A HyperNeuron AI workspace</div>
                <div class="parent-brand-name">Intelligence that speaks Bharat</div>
                <div class="parent-brand-line">Human insight connected to multilingual models, voice and evaluation.</div>
            </div>
            <div class="hn-signal-network" aria-hidden="true">
                <svg class="hn-connection-map" viewBox="0 0 640 130" preserveAspectRatio="none">
                    <path d="M55 66 C125 15 145 116 218 66 S340 15 410 66 S525 116 590 66" />
                    <circle cx="145" cy="66" r="5"/><circle cx="345" cy="66" r="5"/><circle cx="525" cy="66" r="5"/>
                </svg>
                <div class="hn-node n1"><div class="hn-node-icon">अ</div><div class="hn-node-copy"><b>22+ Languages</b><span>India-first linguistic intelligence</span></div></div>
                <div class="hn-node n2"><div class="hn-node-icon">◈</div><div class="hn-node-copy"><b>Model Output</b><span>Business LLM response signals</span></div></div>
                <div class="hn-node n3"><div class="hn-node-icon">✓</div><div class="hn-node-copy"><b>Human Review</b><span>Context, language and quality</span></div></div>
                <div class="hn-node n4"><div class="hn-node-icon">≡</div><div class="hn-node-copy"><b>Voice AI</b><span>Natural speech and expression</span></div></div>
                <div class="hn-live-signal"><i></i> Live evaluation signal network</div>
            </div>
            <div class="parent-brand-cta">Explore HyperNeuron <span>↗</span></div>
            <a class="parent-brand-hit-area" href="https://www.hyperneuronai.com/"
               target="_blank" rel="noopener noreferrer" aria-label="Visit HyperNeuron AI"></a>
        </div>
        """
    )


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
        "column_display_name_",
        "uploaded_column_",
        "criteria_rating_",
        "criteria_scale_",
    )
    for key in list(st.session_state.keys()):
        if key.startswith(prefixes):
            del st.session_state[key]
    for key in (
        "select_prompt_col",
        "select_category_col",
        "criteria_target_columns_widget",
    ):
        st.session_state.pop(key, None)
    st.session_state.response_column_count = 2
    st.session_state.response_columns = []
    st.session_state.evaluation_column_slots = []
    st.session_state.evaluation_column_defaults = {}
    st.session_state.response_display_names = {}
    st.session_state.column_display_names = {}
    st.session_state.criteria_target_columns = []
    st.session_state.columns_confirmed = False
    st.session_state.column_mapping_version = COLUMN_MAPPING_VERSION
    st.session_state.pop("jump_to_row", None)
    st.session_state.pop("pending_row_navigation", None)


def user_state_directory() -> Path:
    """Return the private state root for the current signed-in reviewer."""
    identity = str(getattr(st.user, "email", None) or "local-reviewer").strip().lower()
    user_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    directory = Path.cwd() / ".mira_state" / user_key
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def project_id_for(source_name: str, source_size: int) -> str:
    identity = f"{source_name.strip().lower()}::{int(source_size)}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def project_directory(project_id: str) -> Path:
    if len(project_id) != 20 or any(character not in "0123456789abcdef" for character in project_id):
        raise ValueError("Invalid project identifier.")
    directory = user_state_directory() / "projects" / project_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def active_dataset_directory() -> Path:
    """Return the active project's directory, including legacy-state support."""
    root = user_state_directory()
    pointer = root / "active_project.txt"
    if pointer.exists():
        project_id = pointer.read_text(encoding="utf-8").strip()
        if len(project_id) == 20 and all(character in "0123456789abcdef" for character in project_id):
            return project_directory(project_id)
    return root


def persist_active_dataset(
    original_df: pd.DataFrame,
    review_df: pd.DataFrame,
    source_name: str,
    source_size: int,
) -> None:
    """Persist the active upload so a browser refresh can restore its mapping page."""
    project_id = project_id_for(source_name, source_size)
    directory = project_directory(project_id)
    original_tmp = directory / "original.tmp.json.gz"
    review_tmp = directory / "review.tmp.json.gz"
    metadata_tmp = directory / "metadata.tmp.json"
    original_df.to_json(original_tmp, orient="table", compression="gzip", index=False)
    review_df.to_json(review_tmp, orient="table", compression="gzip", index=False)
    metadata = {
        "project_id": project_id,
        "source_name": source_name,
        "source_size": int(source_size),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "current_index": int(st.session_state.get("current_index", 0)),
        "col_prompt": st.session_state.get("col_prompt"),
        "response_columns": st.session_state.get("response_columns", []),
        "response_display_names": st.session_state.get("response_display_names", {}),
        "column_display_names": st.session_state.get("column_display_names", {}),
        "criteria_target_columns": st.session_state.get("criteria_target_columns", []),
        "columns_confirmed": bool(st.session_state.get("columns_confirmed", False)),
        "evaluation_column_slots": st.session_state.get("evaluation_column_slots", []),
        "evaluation_column_defaults": st.session_state.get("evaluation_column_defaults", {}),
    }
    metadata_tmp.write_text(json.dumps(metadata, default=str), encoding="utf-8")
    original_tmp.replace(directory / ORIGINAL_DATA_FILE)
    review_tmp.replace(directory / REVIEW_DATA_FILE)
    metadata_tmp.replace(directory / "metadata.json")
    (user_state_directory() / "active_project.txt").write_text(project_id, encoding="utf-8")


def list_review_projects() -> list[dict]:
    """Return saved project summaries for the signed-in reviewer."""
    projects = []
    projects_root = user_state_directory() / "projects"
    if not projects_root.exists():
        return projects
    for metadata_path in projects_root.glob("*/metadata.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            review_df = pd.read_json(
                metadata_path.parent / REVIEW_DATA_FILE,
                orient="table",
                compression="gzip",
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        reviewed, total, pct = compute_progress(ensure_review_columns(review_df)["reviewed_status"])
        metadata.update({"reviewed": reviewed, "total": total, "progress": pct})
        metadata["project_id"] = metadata.get("project_id") or metadata_path.parent.name
        projects.append(metadata)
    return sorted(projects, key=lambda item: item.get("updated_at", ""), reverse=True)


def restore_project(project_id: str) -> bool:
    """Restore a selected saved project and make it the active review."""
    directory = project_directory(project_id)
    original_path = directory / ORIGINAL_DATA_FILE
    review_path = directory / REVIEW_DATA_FILE
    metadata_path = directory / "metadata.json"
    if not all(path.exists() for path in (original_path, review_path, metadata_path)):
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        original_df = pd.read_json(original_path, orient="table", compression="gzip")
        review_df = pd.read_json(review_path, orient="table", compression="gzip")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    clear_review_widget_state()
    st.session_state.df_original = original_df
    st.session_state.df_review = ensure_review_columns(review_df)
    max_index = max(len(review_df) - 1, 0)
    st.session_state.current_index = min(max(int(metadata.get("current_index") or 0), 0), max_index)
    st.session_state.rows_loaded = True
    st.session_state.loaded_file_name = str(metadata.get("source_name") or "Uploaded dataset")
    st.session_state.loaded_file_size = int(metadata.get("source_size") or 0)
    st.session_state.autosave_path = get_autosave_path(st.session_state.loaded_file_name)
    st.session_state.col_prompt = metadata.get("col_prompt")
    st.session_state.response_columns = list(metadata.get("response_columns") or [])
    st.session_state.response_display_names = dict(metadata.get("response_display_names") or {})
    st.session_state.column_display_names = dict(metadata.get("column_display_names") or {})
    st.session_state.criteria_target_columns = list(metadata.get("criteria_target_columns") or [])
    st.session_state.columns_confirmed = bool(metadata.get("columns_confirmed", False))
    st.session_state.evaluation_column_slots = list(metadata.get("evaluation_column_slots") or [])
    st.session_state.evaluation_column_defaults = {
        int(key): value for key, value in dict(metadata.get("evaluation_column_defaults") or {}).items()
    }
    (user_state_directory() / "active_project.txt").write_text(project_id, encoding="utf-8")
    return True


def restore_active_dataset() -> bool:
    """Restore the last active upload for the signed-in user after a refresh."""
    directory = active_dataset_directory()
    original_path = directory / ORIGINAL_DATA_FILE
    review_path = directory / REVIEW_DATA_FILE
    metadata_path = directory / "metadata.json"
    if not all(path.exists() for path in (original_path, review_path, metadata_path)):
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        original_df = pd.read_json(original_path, orient="table", compression="gzip")
        review_df = pd.read_json(review_path, orient="table", compression="gzip")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    project_id = metadata.get("project_id")
    if project_id:
        return restore_project(str(project_id))
    # Legacy single-project recovery.
    st.session_state.df_original = original_df
    st.session_state.df_review = ensure_review_columns(review_df)
    st.session_state.current_index = min(max(int(metadata.get("current_index") or 0), 0), max(len(review_df) - 1, 0))
    st.session_state.rows_loaded = True
    st.session_state.loaded_file_name = str(metadata.get("source_name") or "Uploaded dataset")
    st.session_state.loaded_file_size = int(metadata.get("source_size") or 0)
    st.session_state.col_prompt = metadata.get("col_prompt")
    st.session_state.response_columns = list(metadata.get("response_columns") or [])
    st.session_state.response_display_names = dict(metadata.get("response_display_names") or {})
    st.session_state.column_display_names = dict(metadata.get("column_display_names") or {})
    st.session_state.criteria_target_columns = list(metadata.get("criteria_target_columns") or [])
    st.session_state.columns_confirmed = bool(metadata.get("columns_confirmed", False))
    return True


def persist_active_review_state() -> None:
    """Persist data, mapping, progress, and the active row for refresh recovery."""
    original_df = st.session_state.get("df_original")
    review_df = st.session_state.get("df_review")
    source_name = st.session_state.get("loaded_file_name")
    if original_df is None or review_df is None or not source_name:
        return
    persist_active_dataset(
        original_df,
        review_df,
        str(source_name),
        int(st.session_state.get("loaded_file_size") or 0),
    )


def reset_column_confirmation() -> None:
    """Require reconfirmation after a mapped column name changes."""
    st.session_state.columns_confirmed = False


def remove_evaluation_column(slot_id: int) -> None:
    """Remove one mapped evaluation column before evaluation starts."""
    removed_column = st.session_state.get(f"select_response_col_{slot_id}")
    st.session_state.evaluation_column_slots = [
        slot
        for slot in st.session_state.evaluation_column_slots
        if slot != slot_id
    ]
    if "criteria_target_columns_widget" in st.session_state:
        st.session_state.criteria_target_columns_widget = [
            column
            for column in st.session_state.criteria_target_columns_widget
            if column != removed_column
        ]
    st.session_state.pop(f"select_response_col_{slot_id}", None)
    st.session_state.columns_confirmed = False


def navigate_to_row(row_index: int, max_index: int) -> None:
    """Keep navigation buttons and the jump slider on the same row."""
    new_index = min(max(int(row_index), 0), max_index)
    st.session_state.current_index = new_index
    st.session_state.jump_to_row = new_index
    persist_active_review_state()


def apply_jump_to_row() -> None:
    """Apply the jump slider value to the active review row."""
    st.session_state.current_index = int(st.session_state.jump_to_row)
    persist_active_review_state()


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


def prepare_download_dataframe(
    df: pd.DataFrame,
    criteria_target_columns: list,
) -> tuple[pd.DataFrame, list[str]]:
    """Add readable overall ratings to downloads without changing review UI."""
    result = df.copy(deep=True)
    overall_rating_columns = []
    for source_column in criteria_target_columns:
        source_rating_columns = [
            dynamic_rating_column(source_column, rating_column)
            for rating_column in RATING_COLUMNS
            if dynamic_rating_column(source_column, rating_column) in result.columns
        ]
        if not source_rating_columns:
            continue
        output_column = f"{source_column} Overall Rating"
        numeric_ratings = result[source_rating_columns].apply(
            pd.to_numeric, errors="coerce"
        )
        result[output_column] = numeric_ratings.mean(axis=1).round(2).astype("Float64")
        overall_rating_columns.append(output_column)
    return result, overall_rating_columns


def get_autosave_path(source_name: str) -> Path:
    """Return a stable autosave path for an uploaded source file."""
    stem = Path(source_name).stem or "reviewed_output"
    safe_stem = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in stem).strip()
    return Path.cwd() / f"{safe_stem or 'reviewed_output'}_autosave.xlsx"


def write_review_xlsx(df: pd.DataFrame, output_path: Path) -> None:
    """Write review data as xlsx, using a temporary file to avoid partial saves."""
    with tempfile.NamedTemporaryFile(
        dir=output_path.parent,
        prefix=f".{output_path.stem}.",
        suffix=".tmp.xlsx",
        delete=False,
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        with pd.ExcelWriter(tmp_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="reviewed")
        tmp_path.replace(output_path)
    finally:
        tmp_path.unlink(missing_ok=True)


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
    criteria_widget_keys: dict[str, str],
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
    for column, key in criteria_widget_keys.items():
        rating = rating_from_scale(st.session_state.get(key))
        df_review.at[row_index, column] = rating if rating is not None else pd.NA

    source_name = st.session_state.get("loaded_file_name")
    if source_name:
        try:
            autosave_path = autosave_review_data(df_review, source_name)
        except Exception as e:
            st.session_state.autosave_status = f"Autosave failed: {e}"
        else:
            st.session_state.autosave_status = f"Autosaved to {autosave_path.name}"
    try:
        persist_active_review_state()
    except (OSError, ValueError, TypeError):
        pass


def review_workspace(force_llm: bool = False, mapping_only: bool = False):
    """Run the existing upload, mapping, and evaluation workflow."""
    st.markdown('<div class="workspace-page-marker"></div>', unsafe_allow_html=True)
    selected_model_type = str(st.session_state.get("review_model_type", "LLM")).upper()
    if not force_llm:
        st.markdown('<div class="feature-page-marker"></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="llm-upload-page-marker"></div>', unsafe_allow_html=True)

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
    if "evaluation_column_slots" not in st.session_state:
        st.session_state.evaluation_column_slots = []
    if "evaluation_column_defaults" not in st.session_state:
        st.session_state.evaluation_column_defaults = {}
    if "response_display_names" not in st.session_state:
        st.session_state.response_display_names = {}
    if "column_display_names" not in st.session_state:
        st.session_state.column_display_names = {}
    if "criteria_target_columns" not in st.session_state:
        st.session_state.criteria_target_columns = []
    if "response_column_count" not in st.session_state:
        st.session_state.response_column_count = 2
    if "columns_confirmed" not in st.session_state:
        st.session_state.columns_confirmed = False
    if st.session_state.get("column_mapping_version") != COLUMN_MAPPING_VERSION:
        for key in list(st.session_state.keys()):
            if key.startswith(
                (
                    "select_response_col_",
                    "response_display_name_",
                    "column_display_name_",
                    "uploaded_column_",
                )
            ):
                del st.session_state[key]
        for key in (
            "select_prompt_col",
            "select_category_col",
            "criteria_target_columns_widget",
        ):
            st.session_state.pop(key, None)
        st.session_state.response_column_count = 2
        st.session_state.response_columns = []
        st.session_state.evaluation_column_slots = []
        st.session_state.evaluation_column_defaults = {}
        st.session_state.response_display_names = {}
        st.session_state.column_display_names = {}
        st.session_state.criteria_target_columns = []
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

    if mapping_only and (not st.session_state.rows_loaded or st.session_state.df_review is None):
        if not restore_active_dataset():
            st.components.v1.html(
                """<script>window.parent.location.replace(window.parent.location.origin + '/llm-review');</script>""",
                height=0,
            )
            st.stop()

    if mapping_only:
        page_marker = "evaluation-page-marker" if st.session_state.columns_confirmed else "mapping-page-marker"
        st.markdown(f'<div class="{page_marker}"></div>', unsafe_allow_html=True)
    if mapping_only:
        back_href = "/llm-review"
    elif force_llm:
        back_href = "/review"
    else:
        back_href = "/"
    render_inner_navigation("review", back_href=back_href)

    # ------------------ Upload ------------------
    uploaded = None
    if not st.session_state.columns_confirmed and not mapping_only:
        if not force_llm:
            with st.container(key="feature_stage"):
                render_safe_html(
                    f"""
                    <div class="upload-section-head">
                        <div><i>✦</i><span><strong>Our review features</strong><small>Choose the evaluation workflow designed for your data.</small></span></div>
                    </div>
                    <div class="review-product-grid">
                        <a class="review-product-card" href="/llm-review?model_type=slm" target="_parent">
                            <div class="review-product-card-inner">
                                <div class="review-product-icon">◉</div>
                                <h3>SLM Data Review</h3>
                                <p>Evaluate compact and domain-focused model responses with structured human judgment.</p>
                                <ul><li>Multiple response comparison</li><li>Context, language, emotion and safety ratings</li><li>Editable final response</li><li>Reviewed dataset export</li></ul>
                                <span class="review-product-action">Open SLM Review →</span>
                            </div>
                        </a>
                        <a class="review-product-card" href="/llm-review?model_type=llm" target="_parent">
                            <div class="review-product-card-inner">
                                <div class="review-product-icon">◇</div>
                                <h3>LLM Data Review</h3>
                                <p>Compare general-purpose model outputs and preserve reviewer decisions row by row.</p>
                                <ul><li>Multiple response comparison</li><li>Configurable rating targets</li><li>Editable final response</li><li>Reviewed dataset export</li></ul>
                                <span class="review-product-action">Open LLM Review →</span>
                            </div>
                        </a>
                    </div>
                    """
                )

        if force_llm:
            with st.container(key="upload_stage"):
                render_safe_html(
                    f"""
                    <div class="upload-section-head">
                        <div><i>⇧</i><span><strong>Upload your {selected_model_type} dataset</strong><small>Choose where your evaluation data lives.</small></span></div>
                        <span class="upload-format-pills"><span>CSV</span><span>XLSX</span><span>XLS</span></span>
                    </div>
                    <div class="review-feature-note">Compare model responses, apply human ratings, edit the final answer, and export structured review data.</div>
                    """
                )
                data_source = st.radio(
                    "Choose data source",
                    options=["Local file", "Google Drive / Colab"],
                    horizontal=True,
                    key="upload_data_source",
                )
                if data_source == "Local file":
                    uploaded = st.file_uploader(
                        "Drop a CSV or spreadsheet here",
                        type=["csv", "xlsx", "xls"],
                        accept_multiple_files=False,
                        help="Maximum file size: 200 MB.",
                    )
                else:
                    drive_url = st.text_input(
                        "Google Drive share link",
                        placeholder="https://drive.google.com/file/d/.../view",
                        help="The file must be shared with anyone who has the link.",
                    ).strip()
                    if st.button("Fetch file from Google Drive", type="primary"):
                        if not drive_url:
                            st.error("Enter a Google Drive share link.")
                        else:
                            try:
                                uploaded = fetch_google_drive_file(drive_url)
                            except Exception as e:
                                st.error(f"Failed to fetch Google Drive file: {e}")
                            else:
                                st.success(f"Fetched `{uploaded.name}` from Google Drive.")
                if uploaded is None and not st.session_state.rows_loaded:
                    st.markdown(
                        '<div class="empty-review-state"><i>⇧</i><div><strong>Your review workspace is ready</strong><span>Upload a CSV or spreadsheet above to begin mapping columns and evaluating model responses.</span></div></div>',
                        unsafe_allow_html=True,
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

            try:
                persist_active_dataset(df, df_review, current_file_name, current_file_size)
            except (OSError, ValueError, TypeError) as e:
                st.session_state.autosave_status = f"Refresh recovery unavailable: {e}"

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

            if force_llm:
                if COLUMN_MAPPING_PAGE is None:
                    st.error("Column Mapping page is unavailable. Please refresh and try again.")
                    st.stop()
                st.switch_page(COLUMN_MAPPING_PAGE)

            st.subheader("Preview")
            st.dataframe(df_review.head(50), width="stretch", hide_index=True)
        else:
            st.caption(f"Continuing review for `{current_file_name}`.")


    # If no data loaded yet, stop here.
    if not st.session_state.rows_loaded or st.session_state.df_review is None:
        return

    df_review = st.session_state.df_review
    df_review = ensure_review_columns(df_review)
    st.session_state.df_review = df_review
    if st.session_state.autosave_status and not st.session_state.columns_confirmed:
        st.caption(st.session_state.autosave_status)

    if not st.session_state.columns_confirmed:
        # ------------------ Column selection ------------------
        if mapping_only:
            loaded_name = escape(str(st.session_state.loaded_file_name or "Uploaded dataset"))
            render_safe_html(
                f"""
                <div class="mapping-workbench-intro">
                    <small>Annotation setup</small>
                    <strong>Shape the workspace around your data</strong>
                    <span><b>{loaded_name}</b> is ready. Assign the prompt and response columns, refine their display names, then begin evaluation.</span>
                </div>
                """
            )
        st.subheader("Map your columns")
        available_columns = list(st.session_state.df_original.columns)
        st.markdown("**Available columns in the uploaded file**")
        st.caption("Original column names are kept internally. Edit only the display names if needed.")
        column_display_names = {}
        for column_index, column in enumerate(available_columns):
            column_name_cols = st.columns(2)
            with column_name_cols[0]:
                st.text_input(
                    "Uploaded column",
                    value=str(column),
                    key=f"uploaded_column_{column_index}",
                    disabled=True,
                    label_visibility="collapsed",
                )
            with column_name_cols[1]:
                column_display_names[column] = st.text_input(
                    f"Display name for {column}",
                    value=str(column),
                    key=f"column_display_name_{column_index}",
                    on_change=reset_column_confirmation,
                    label_visibility="collapsed",
                    placeholder="Custom display name",
                ).strip()

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

        if not st.session_state.evaluation_column_slots:
            non_prompt_columns = [
                column
                for column in available_columns
                if column != suggested_prompt_column
            ]
            excluded_response_terms = {
                "comment", "comments", "note", "notes", "review", "reviewer",
                "category", "problem", "label", "status", "id", "index",
            }
            response_terms = (
                "assistant", "response", "answer", "chosen", "rejected",
                "gemma", "chatgpt", "model", "output", "completion",
            )
            likely_response_columns = [
                column
                for column in non_prompt_columns
                if any(term in str(column).strip().lower() for term in response_terms)
                and not any(term in str(column).strip().lower() for term in excluded_response_terms)
            ]
            fallback_response_columns = [
                column
                for column in non_prompt_columns
                if not any(term in str(column).strip().lower() for term in excluded_response_terms)
            ]
            default_evaluation_columns = likely_response_columns or fallback_response_columns[:2]
            st.session_state.evaluation_column_slots = list(
                range(len(default_evaluation_columns))
            )
            st.session_state.evaluation_column_defaults = {
                slot_id: column
                for slot_id, column in enumerate(default_evaluation_columns)
            }

        response_columns = []
        response_display_names = []
        st.caption("Select only model-output columns that reviewers should compare. Comment, note, category and metadata columns are not selected automatically.")
        for column_number, slot_id in enumerate(
            st.session_state.evaluation_column_slots,
            start=1,
        ):
            default_column = st.session_state.evaluation_column_defaults.get(slot_id)
            mapping_row = st.columns([8, 1])
            with mapping_row[0]:
                response_column = st.selectbox(
                    f"Response column {column_number}",
                    options=column_options,
                    index=(
                        column_options.index(default_column)
                        if default_column in column_options
                        else 0
                    ),
                    format_func=lambda column: "Select a column" if column is None else str(column),
                    key=f"select_response_col_{slot_id}",
                    on_change=reset_column_confirmation,
                )
            with mapping_row[1]:
                st.button(
                    "✕",
                    key=f"remove_evaluation_column_{slot_id}",
                    help=f"Remove Column {column_number} from evaluation",
                    disabled=len(st.session_state.evaluation_column_slots) <= 1,
                    on_click=remove_evaluation_column,
                    args=(slot_id,),
                )
            display_name = (
                column_display_names.get(response_column, "")
                if response_column is not None
                else ""
            )
            response_columns.append(response_column)
            response_display_names.append(display_name)

        default_criteria_targets = [
            column for column in response_columns if column is not None
        ]
        criteria_target_columns = st.multiselect(
            "Apply Review Criteria to columns",
            options=default_criteria_targets,
            default=default_criteria_targets,
            format_func=str,
            key="criteria_target_columns_widget",
            on_change=reset_column_confirmation,
            help="Choose every uploaded-file column that should receive separate star ratings.",
        )
        st.caption("Beta note: review dimensions are provisional and can change as the evaluation framework is finalised.")

        def validate_mapping() -> list[str]:
            errors = []
            if any(not name for name in column_display_names.values()):
                errors.append("Every uploaded column must have a non-empty display name.")
            selected_responses = [column for column in response_columns if column is not None]
            selected_display_names = [
                response_display_names[index]
                for index, column in enumerate(response_columns)
                if column is not None
            ]
            if col_prompt is None:
                errors.append("Select a User Prompt Column.")
            if len(selected_responses) < 1:
                errors.append("Keep at least one column for evaluation.")
            if len(selected_responses) != len(set(selected_responses)):
                errors.append("Duplicate response column selections are not allowed.")
            if any(not name for name in selected_display_names):
                errors.append("Give every selected response column a display name.")
            if len(selected_display_names) != len(set(selected_display_names)):
                errors.append("Response display names must be unique.")
            return errors

        if st.button("Start Evaluation", type="primary", key="start_evaluation_button"):
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
                st.session_state.column_display_names = column_display_names
                st.session_state.criteria_target_columns = criteria_target_columns
                st.session_state.columns_confirmed = True
                persist_active_review_state()
                st.rerun()

        if not st.session_state.columns_confirmed:
            st.info("Confirm the two response columns, then click Start Evaluation.")
            return

        st.success("Columns confirmed. You can continue reviewing below.")

    df_review = ensure_dynamic_rating_columns(
        st.session_state.df_review,
        st.session_state.criteria_target_columns,
    )
    st.session_state.df_review = df_review

    render_parent_brand_portal()

    # ------------------ Progress tracking ------------------
    reviewed_count, total_rows, pct = compute_progress(df_review["reviewed_status"])
    st.subheader("Progress")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Reviewed", f"{reviewed_count}/{total_rows}")
    with c2:
        st.metric("Total", f"{total_rows}")
    with c3:
        st.metric("Complete", f"{pct:.1f}%")
    st.progress(min(max(pct / 100.0, 0.0), 1.0))

    # ------------------ Review interface ------------------
    st.subheader("Review")

    # Navigation controls
    max_index = max(total_rows - 1, 0)
    if "pending_row_navigation" in st.session_state:
        pending_index = st.session_state.pop("pending_row_navigation")
        navigate_to_row(pending_index, max_index)
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
    with st.container(border=True):
        st.markdown("#### User prompt")
        st.write(prompt_val)

    st.markdown("**Responses**")
    response_display_cols = st.columns(min(len(response_values), 3))
    for response_number, (column, response_value) in enumerate(response_values.items()):
        with response_display_cols[response_number % len(response_display_cols)]:
            with st.container(border=True):
                st.markdown(f"### {column}")
                st.write(response_value)

    # ---- Inputs for selection + final response ----
    existing_choice = display_text(df_review.iloc[idx]["review_choice"]) if "review_choice" in df_review.columns else ""
    existing_final = display_text(df_review.iloc[idx]["final_response"]) if "final_response" in df_review.columns else ""
    existing_notes = display_text(df_review.iloc[idx]["reviewer_notes"]) if "reviewer_notes" in df_review.columns else ""

    choice_options = [
        *response_values.keys(),
        "All responses are bad",
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
    show_notes_key = f"show_notes_{idx}"
    final_key = f"final_{idx}"
    radio_key = f"{choice_key}_radio"
    row_index = df_review.index[idx]
    criteria_widget_keys = {}
    for target_index, source_column in enumerate(st.session_state.criteria_target_columns):
        for rating_column in RATING_COLUMNS:
            output_column = dynamic_rating_column(source_column, rating_column)
            criteria_widget_keys[output_column] = (
                f"criteria_scale_{idx}_{target_index}_{rating_column}"
            )

    # Initialize widget-backed session values BEFORE widget instantiation.
    # IMPORTANT: Do not reassign these keys after the widgets are created.
    # Initialize only the widget values we need *before* widget creation.
    # Use setdefault-like logic without modifying the state dict during reruns.
    if choice_key not in st.session_state or st.session_state[choice_key] not in choice_options:
        st.session_state[choice_key] = default_choice
    if notes_key not in st.session_state:
        st.session_state[notes_key] = existing_notes
    if show_notes_key not in st.session_state:
        st.session_state[show_notes_key] = bool(existing_notes.strip())
    if final_key not in st.session_state:
        if is_reviewed:
            st.session_state[final_key] = existing_final
        else:
            st.session_state[final_key] = response_values.get(default_choice, "")
    if radio_key not in st.session_state or st.session_state[radio_key] not in choice_options:
        st.session_state[radio_key] = st.session_state[choice_key]
    for column, key in criteria_widget_keys.items():
        if key not in st.session_state:
            saved_value = df_review.iloc[idx][column]
            try:
                numeric_rating = int(saved_value)
            except (TypeError, ValueError):
                numeric_rating = 0
            st.session_state[key] = numeric_rating if 1 <= numeric_rating <= 5 else None

    draft_callback_args = (
        row_index,
        choice_key,
        final_key,
        notes_key,
        criteria_widget_keys,
        response_values,
    )

    rating_values = {}

    render_safe_html(
        """
        <style>
        div[data-testid="stPills"] button {
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        div[data-testid="stPills"] button:hover {
            transform: scale(1.16) translateY(-2px);
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.18);
        }
        </style>
        """
    )

    def scale_rating(label: str, key: str) -> Optional[int]:
        st.markdown(f"**{label}**")
        selection = st.pills(
            "Rating",
            options=[1, 2, 3, 4, 5],
            selection_mode="single",
            key=key,
            on_change=persist_review_draft,
            args=draft_callback_args,
            label_visibility="collapsed",
        )
        rating = rating_from_scale(selection)
        st.caption(RATING_MEANINGS[rating] if rating is not None else "Not rated")
        return rating

    if st.session_state.criteria_target_columns:
        review_columns = st.columns(
            len(st.session_state.criteria_target_columns)
        )
        for target_index, source_column in enumerate(
            st.session_state.criteria_target_columns
        ):
            display_name = st.session_state.response_display_names.get(
                source_column,
                st.session_state.column_display_names.get(source_column, str(source_column)),
            )
            with review_columns[target_index]:
                with st.container(
                    border=True,
                    key=f"criteria_paper_{target_index % 8}",
                ):
                    st.markdown(f"#### Review criteria: {display_name}")
                    for criterion_index, (rating_column, label) in enumerate(
                        RATING_COLUMNS.items()
                    ):
                        output_column = dynamic_rating_column(source_column, rating_column)
                        with st.container(
                            border=True,
                            key=f"criterion_sheet_{criterion_index % 8}_{target_index}",
                        ):
                            rating_values[output_column] = scale_rating(
                                label,
                                criteria_widget_keys[output_column],
                            )

    st.markdown("#### Select the best response")
    st.caption("Choose the response that should be copied into the editable final response field. Select ‘All responses are bad’ only when none is usable.")
    selected_choice = st.radio(
        "Response to use",
        options=choice_options,
        index=choice_options.index(st.session_state[radio_key]),
        key=radio_key,
        help="Select one mapped response, or reject all available responses.",
        on_change=persist_review_draft,
        args=draft_callback_args,
        label_visibility="collapsed",
    )

    final_response_text = st.text_area(
        "Final response (editable)",
        key=final_key,
        height=180,
        on_change=persist_review_draft,
        args=draft_callback_args,
    )

    reviewer_notes = display_text(st.session_state.get(notes_key, ""))
    add_reviewer_notes = st.checkbox(
        "Add reviewer notes (optional)",
        key=show_notes_key,
    )
    if add_reviewer_notes:
        reviewer_notes = st.text_area(
            "Reviewer notes",
            height=120,
            key=notes_key,
            on_change=persist_review_draft,
            args=draft_callback_args,
        )


    # Save button
    save_disabled = False
    if selected_choice != "All responses are bad" and not display_text(final_response_text).strip():
        # Empty output is valid only when all responses are rejected.
        save_disabled = True

    if st.button("Save current row", type="primary", disabled=save_disabled):
        # Validation
        if selected_choice != "All responses are bad" and not display_text(final_response_text).strip():
            st.error("Final response should not be empty for the selected response column.")
            return

        st.session_state.df_review.at[df_review.index[idx], "review_choice"] = selected_choice

        st.session_state.df_review.at[df_review.index[idx], "final_response"] = display_text(final_response_text)
        st.session_state.df_review.at[df_review.index[idx], "reviewer_notes"] = display_text(reviewer_notes)
        for output_column, rating in rating_values.items():
            st.session_state.df_review.at[df_review.index[idx], output_column] = (
                rating if rating is not None else pd.NA
            )
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

        try:
            persist_active_review_state()
        except (OSError, ValueError, TypeError):
            pass

        # Mark reviewed status as updated in local variables.
        st.success("Saved.")

        if idx < max_index:
            st.session_state.pending_row_navigation = idx + 1

        # Do not modify widget-backed session_state keys after widgets are created.


        # Rerun to refresh progress/status.
        st.rerun()

    # ------------------ Download ------------------
    st.subheader("Download reviewed data")

    # Force-sync the currently visible row before building download payloads.
    # This also captures edits when a download click happens before a widget
    # blur/on_change callback has completed.
    current_row_index = df_review.index[idx]
    st.session_state.df_review.at[current_row_index, "review_choice"] = selected_choice
    st.session_state.df_review.at[current_row_index, "final_response"] = display_text(
        final_response_text
    )
    st.session_state.df_review.at[current_row_index, "reviewer_notes"] = display_text(
        reviewer_notes
    )
    for output_column, rating in rating_values.items():
        st.session_state.df_review.at[current_row_index, output_column] = (
            rating if rating is not None else pd.NA
        )

    # Use an immutable snapshot so both download formats contain identical,
    # up-to-date data for this rerun.
    df_to_download, overall_rating_columns = prepare_download_dataframe(
        st.session_state.df_review,
        st.session_state.criteria_target_columns,
    )

    # Small confirmation preview of saved review columns.
    cols_to_preview = list(
        dict.fromkeys(
            [
                c
                for c in ["review_choice", "final_response"]
                if c in df_to_download.columns
            ]
            + overall_rating_columns
            + [
                c
                for c in ["reviewer_notes", "reviewed_status"]
                if c in df_to_download.columns
            ]
        )
    )
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
        st.dataframe(df_preview, width="stretch", hide_index=True)

    dl_cols = st.columns(2)
    csv_bytes = build_download_bytes(df_to_download, "csv")
    download_revision = hashlib.sha256(csv_bytes).hexdigest()[:12]

    with dl_cols[0]:
        st.download_button(
            label="Download CSV",
            data=csv_bytes,
            file_name=f"reviewed_output_{download_revision}.csv",
            mime="text/csv",
            key=f"download_csv_{download_revision}",
        )

    with dl_cols[1]:
        xlsx_bytes = build_download_bytes(df_to_download, "xlsx")
        st.download_button(
            label="Download Excel (.xlsx)",
            data=xlsx_bytes,
            file_name=f"reviewed_output_{download_revision}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_xlsx_{download_revision}",
        )

    if st.button("Save reviewed copy in this folder"):
        try:
            output_path = save_review_file(df_to_download, st.session_state.loaded_file_name or "reviewed_output.xlsx")
        except Exception as e:
            st.error(f"Failed to save reviewed copy: {e}")
        else:
            st.success(f"Saved reviewed copy to {output_path}")


    # ------------------ Optional LLM Judge Check placeholder ------------------
    st.subheader("LLM Judge Check")
    st.caption("Placeholder UI only. No real API call is performed.")

    guidelines = st.text_area(
        "Guidelines for LLM Judge Check",
        value="",
        height=140,
        key="judge_guidelines",
    )

    if st.button("Check Final Response"):
        st.info("API integration can be added later.")


def render_site_footer() -> None:
    """Render shared product footer navigation."""
    render_safe_html(
        """
        <footer class="site-footer">
            <a class="site-footer-brand" href="/" target="_parent" aria-label="Go to MIRA home"><i></i> MIRA</a>
            <div>Built for thoughtful human evaluation, not endless spreadsheets.</div>
            <div class="site-footer-links"><a href="/account" target="_parent">Account</a><a href="/about" target="_parent">About</a><a href="https://www.hyperneuronai.com/" target="_parent">HyperNeuron ↗</a></div>
        </footer>
        """
    )


def render_inner_navigation(active_page: str, back_href: str = "/") -> None:
    """Render consistent navigation across secondary product pages."""
    signed_in = google_auth_configured() and bool(getattr(st.user, "is_logged_in", False))
    render_native_navigation(signed_in, active_page)


def home_page():
    """Render the product landing page without workspace controls."""
    render_page_header(False)
    render_site_footer()


def start_new_review_project() -> None:
    """Clear only the active browser state; saved project history remains intact."""
    clear_review_widget_state()
    st.session_state.df_original = None
    st.session_state.df_review = None
    st.session_state.current_index = 0
    st.session_state.rows_loaded = False
    st.session_state.loaded_file_name = None
    st.session_state.loaded_file_size = None
    st.session_state.autosave_path = None
    st.session_state.autosave_status = ""


def projects_page():
    """Show the signed-in reviewer's saved evaluations and resume them."""
    signed_in = google_auth_configured() and bool(getattr(st.user, "is_logged_in", False))
    if not signed_in:
        st.components.v1.html(
            """<script>window.parent.location.replace(window.parent.location.origin + '/account');</script>""",
            height=0,
        )
        st.stop()
    st.markdown('<div class="projects-page-marker"></div>', unsafe_allow_html=True)
    render_inner_navigation("projects")
    render_safe_html(
        """
        <section class="projects-hero">
            <small>Saved evaluation workspace</small>
            <h1>Your review projects</h1>
            <p>Every upload keeps its mapping, ratings, edited responses, progress and last active row. Resume after a disconnect without rebuilding the evaluation.</p>
        </section>
        """
    )
    projects = list_review_projects()
    action_left, action_right = st.columns([1, 2])
    with action_left:
        if st.button("Start a new project", icon=":material/add:", width="stretch"):
            start_new_review_project()
            st.switch_page(LLM_REVIEW_PAGE)
    with action_right:
        st.caption(f"{len(projects)} saved project{'s' if len(projects) != 1 else ''} for this account")
    if not projects:
        st.info("No saved projects yet. Upload a dataset to create your first review project.")
        render_site_footer()
        return
    for row_start in range(0, len(projects), 3):
        cards = st.columns(min(3, len(projects) - row_start))
        for offset, project in enumerate(projects[row_start:row_start + 3]):
            project_id = str(project["project_id"])
            updated_raw = str(project.get("updated_at") or "")
            try:
                updated_label = datetime.fromisoformat(updated_raw).astimezone().strftime("%d %b %Y, %I:%M %p")
            except ValueError:
                updated_label = "Saved recently"
            reviewed = int(project.get("reviewed") or 0)
            total = int(project.get("total") or 0)
            progress = float(project.get("progress") or 0)
            current_row = min(int(project.get("current_index") or 0) + 1, max(total, 1))
            with cards[offset]:
                render_safe_html(
                    f"""<div class="saved-project-card"><small>Updated {escape(updated_label)}</small><h3>{escape(str(project.get('source_name') or 'Untitled review'))}</h3><p>{reviewed} of {total} rows reviewed · resume at row {current_row}</p><div class="saved-project-progress"><i style="width:{min(max(progress, 0), 100):.1f}%"></i></div></div>"""
                )
                if st.button("Resume project →", key=f"resume_project_{project_id}", width="stretch"):
                    if restore_project(project_id):
                        st.switch_page(COLUMN_MAPPING_PAGE)
                    else:
                        st.error("This project could not be restored.")
    render_site_footer()


def about_page():
    """Explain the product, workflow, and parent-company connection."""
    st.markdown('<div class="about-page-marker"></div>', unsafe_allow_html=True)
    render_inner_navigation("about")
    render_safe_html(
        """
        <section class="about-hero">
            <div class="about-hero-copy"><small>About MIRA</small><h1>Human judgment is the final layer of intelligent AI.</h1><p>MIRA, Model Inference and Response Annotation, helps teams compare model responses with context, capture structured feedback, and produce reliable evaluation datasets without losing the nuance only a human reviewer can provide.</p></div>
            <div class="about-human-loop" aria-hidden="true"><div class="about-loop-ring"></div><div class="about-loop-core"><i>✓</i><b>Human signal</b><span>structured and preserved</span></div><span class="about-loop-tag one">Prompt context</span><span class="about-loop-tag two">Response quality</span><span class="about-loop-tag three">Reviewer rationale</span></div>
        </section>
        <section class="about-manifesto"><div><small>Why MIRA exists</small><h2>Evaluation should explain, not just score.</h2></div><p>A number can tell a team which response won. It cannot explain whether the answer understood the user, sounded natural in their language, or deserved trust. MIRA keeps those human decisions attached to the data so improvement remains traceable.</p></section>
        <section class="about-domain-story"><div class="domain-story-head"><div><small>Built for language in the real world</small><h2>Nuance becomes critical where data is scarce.</h2></div><p>LLMs may sound increasingly natural while still missing domain factuality, instruction intent, cultural context and emotional expression. The gap becomes sharper in low-resource Indic languages and high-stakes domains such as BFSI, where a fluent but incorrect answer can create real risk.</p></div><div class="domain-subjects"><article class="domain-subject"><i>अ</i><h3>Indic language nuance</h3><p>Evaluate whether English, Hindi and Hinglish responses match the user’s language, register and cultural context, rather than simply checking whether the words are grammatical.</p></article><article class="domain-subject"><i>₹</i><h3>Domain-aware judgment</h3><p>Help experts look beyond confident phrasing to assess instruction adherence, contextual relevance and the appropriateness of financial claims.</p></article><article class="domain-subject"><i>H</i><h3>Human preference signal</h3><p>Capture the syntactic, semantic and naturalness judgments that automated similarity scores and model judges can overlook.</p></article></div><div class="alignment-usecases"><div class="alignment-usecase"><b>Response evaluation</b><span>Pairwise comparison and individual response review.</span></div><div class="alignment-usecase"><b>Gold datasets</b><span>Curated examples for reliable benchmarking.</span></div><div class="alignment-usecase"><b>Preference data</b><span>Structured choices suitable for DPO and quality analysis.</span></div><div class="alignment-usecase"><b>Extensible tasks</b><span>A foundation for translation, summarisation and linguistic review.</span></div></div></section>
        <section class="about-principles"><div class="about-section-heading"><div><small>What MIRA protects</small><h2>Human judgment without losing structure.</h2></div><p>Designed around the decisions reviewers actually make, from understanding intent to preserving the reasoning behind a final answer.</p></div><div class="about-grid">
            <article class="about-card"><div class="about-card-icon">◫</div><h3>Meet the data where it is</h3><p>Bring CSV or Excel files, map your own prompt and response columns, and preserve original data throughout the review.</p></article>
            <article class="about-card"><div class="about-card-icon">◎</div><h3>Make judgment consistent</h3><p>Compare multiple responses, capture column-wise criteria, select the strongest answer and refine the final response.</p></article>
            <article class="about-card"><div class="about-card-icon">↗</div><h3>Carry evidence forward</h3><p>Autosave every reviewed row and export decisions, ratings and notes for analysis or model improvement.</p></article>
        </div></section>
        <section class="about-workflow"><div class="about-section-heading"><div><small>From raw output to trusted data</small><h2>One continuous review journey.</h2></div><p>Every stage stays connected, so teams spend less time managing spreadsheets and more time improving model behavior.</p></div><div class="about-steps">
            <div class="about-step"><b>01 · Upload</b>Add the dataset you want to evaluate.</div>
            <div class="about-step"><b>02 · Map</b>Choose prompt, responses, labels, and rating targets.</div>
            <div class="about-step"><b>03 · Review</b>Compare outputs and capture human judgment.</div>
            <div class="about-step"><b>04 · Export</b>Download a structured, evaluation-ready dataset.</div>
        </div></section>
        """
    )
    render_safe_html(
        """
        <div class="about-actions">
            <div class="about-actions-copy">
                <strong>Ready to continue?</strong>
                <span>Return to the product overview or discover the company behind this workspace.</span>
            </div>
            <div class="about-action-links">
                <a class="about-home-link" href="/">← Back to Home</a>
                <a class="about-company-link" href="https://www.hyperneuronai.com/" target="_blank" rel="noopener noreferrer">Explore HyperNeuron AI ↗</a>
            </div>
        </div>
        """
    )
    render_site_footer()


def google_auth_configured() -> bool:
    """Return whether the required Google OIDC settings are available."""
    try:
        auth = st.secrets.get("auth", {})
    except (FileNotFoundError, KeyError):
        return False
    return all(
        auth.get(key)
        for key in ("redirect_uri", "cookie_secret", "client_id", "client_secret", "server_metadata_url")
    )


def account_page():
    """Provide Google OIDC sign-in and signed-in account controls."""
    configured = google_auth_configured()
    logged_in = configured and bool(getattr(st.user, "is_logged_in", False))
    st.markdown('<div class="auth-page-marker"></div>', unsafe_allow_html=True)
    render_inner_navigation("account")
    with st.container(key="account_page_shell"):
        with st.container(border=True, key="account_auth_panel"):
                auth_state = "ready" if logged_in else "secure"
                render_safe_html(f'<div class="account-auth-state {auth_state}"><i></i>{"Workspace ready" if logged_in else "Secure sign in"}</div>')
                render_safe_html(
                    f"""
                    <div class="auth-panel-marker"></div>
                    <div class="auth-panel-head">
                        <div class="google-logo-pro"><span>G</span></div>
                        <h2>{"Welcome back" if logged_in else "Sign in to MIRA"}</h2>
                        <p>{"Your secure review workspace is ready." if logged_in else "Continue with Google to access model evaluation."}</p>
                    </div>
                    """
                )
                if logged_in:
                    user_name = escape(str(getattr(st.user, "name", None) or "Google user"))
                    user_email = escape(str(getattr(st.user, "email", None) or ""))
                    initial = str(user_name).strip()[:1].upper() or "G"
                    render_safe_html(
                        f'<div class="signed-user"><div class="signed-avatar">{initial}</div><div><strong>{user_name}</strong><span>{user_email}</span></div></div>'
                    )
                    render_safe_html('<a class="auth-route-link primary" href="/review">Continue to Review Workspace →</a>')
                    st.button("Sign out", on_click=st.logout, width="stretch")
                elif configured:
                    st.button("Continue with Google", type="primary", icon=":material/login:", on_click=st.login, width="stretch")
                else:
                    st.button("Continue with Google", disabled=True, width="stretch")
                    st.warning("Google authentication has not been configured yet.")
                    st.caption("Add the Google Client ID and Client Secret to `.streamlit/secrets.toml` to activate sign-in.")
                render_safe_html('<div class="auth-trust">Protected through Google OpenID Connect.</div>')
    render_site_footer()


def protected_review_workspace():
    """Require Google authentication before rendering any evaluation data."""
    signed_in = google_auth_configured() and bool(getattr(st.user, "is_logged_in", False))
    if not signed_in:
        st.components.v1.html(
            """<script>window.parent.location.replace(window.parent.location.origin + '/account');</script>""",
            height=0,
        )
        st.info("Sign in is required. Redirecting you to the login page…")
        st.stop()
    review_workspace()


def protected_llm_review_workspace():
    """Open the dedicated SLM/LLM upload and evaluation workflow."""
    signed_in = google_auth_configured() and bool(getattr(st.user, "is_logged_in", False))
    if not signed_in:
        st.components.v1.html(
            """<script>window.parent.location.replace(window.parent.location.origin + '/account');</script>""",
            height=0,
        )
        st.info("Sign in is required. Redirecting you to the login page…")
        st.stop()
    requested_model_type = str(st.query_params.get("model_type", "")).strip().lower()
    if requested_model_type in {"slm", "llm"}:
        st.session_state.review_model_type = requested_model_type.upper()
    # This route is the step immediately before column mapping/evaluation.
    # When browser Back returns here, leave the evaluation view instead of
    # rendering the same Progress screen again. The loaded dataset, ratings,
    # autosave and current row remain intact and can be confirmed again.
    if st.session_state.get("columns_confirmed", False):
        st.session_state.columns_confirmed = False
    review_workspace(force_llm=True)


def protected_column_mapping_workspace():
    """Open the uploaded dataset on a fresh column-mapping page."""
    signed_in = google_auth_configured() and bool(getattr(st.user, "is_logged_in", False))
    if not signed_in:
        st.components.v1.html(
            """<script>window.parent.location.replace(window.parent.location.origin + '/account');</script>""",
            height=0,
        )
        st.info("Sign in is required. Redirecting you to the login page…")
        st.stop()
    review_workspace(force_llm=True, mapping_only=True)


def logout_page():
    """Sign out from Google and return to the public home page."""
    if google_auth_configured() and bool(getattr(st.user, "is_logged_in", False)):
        st.logout()
        st.stop()
    st.components.v1.html(
        """<script>window.parent.location.replace(window.parent.location.origin + '/');</script>""",
        height=0,
    )
    st.stop()


def run_app():
    """Configure and run the multipage Streamlit application."""
    global COLUMN_MAPPING_PAGE, LLM_REVIEW_PAGE
    global HOME_PAGE, REVIEW_PAGE, PROJECTS_PAGE, ABOUT_PAGE, ACCOUNT_PAGE, LOGOUT_PAGE
    st.set_page_config(page_title="MIRA · Model Inference and Response Annotation", page_icon="◉", layout="wide")
    # Load positioning CSS before creating the switch. Otherwise Streamlit can
    # briefly render it as a normal block and push the page below a blank frame.
    inject_app_theme()
    dark_mode_enabled = st.toggle(
        "Dark mode",
        key="mira_dark_mode",
        help="Switch the complete MIRA workspace between light and dark themes.",
    )
    if dark_mode_enabled:
        inject_dark_mode_theme()
    auth_ready = google_auth_configured()
    signed_in = auth_ready and bool(getattr(st.user, "is_logged_in", False))
    COLUMN_MAPPING_PAGE = st.Page(
        protected_column_mapping_workspace,
        title="Column Mapping",
        icon=":material/account_tree:" if signed_in else ":material/lock:",
        url_path="column-mapping",
    )
    LLM_REVIEW_PAGE = st.Page(
        protected_llm_review_workspace,
        title="SLM / LLM Data Review",
        icon=":material/table_view:" if signed_in else ":material/lock:",
        url_path="llm-review",
    )
    HOME_PAGE = st.Page(home_page, title="Home", icon=":material/home:", url_path="home", default=True)
    REVIEW_PAGE = st.Page(
        protected_review_workspace,
        title="Review Workspace",
        icon=":material/rate_review:" if signed_in else ":material/lock:",
        url_path="review",
    )
    PROJECTS_PAGE = st.Page(
        projects_page,
        title="Projects",
        icon=":material/folder_open:" if signed_in else ":material/lock:",
        url_path="projects",
    )
    ABOUT_PAGE = st.Page(about_page, title="About", icon=":material/info:", url_path="about")
    ACCOUNT_PAGE = st.Page(
        account_page,
        title="Account" if signed_in else "Sign in",
        icon=":material/account_circle:" if signed_in else ":material/login:",
        url_path="account",
    )
    LOGOUT_PAGE = st.Page(logout_page, title="Sign out", icon=":material/logout:", url_path="logout")
    if signed_in:
        pages = [
            HOME_PAGE,
            REVIEW_PAGE,
            LLM_REVIEW_PAGE,
            COLUMN_MAPPING_PAGE,
            PROJECTS_PAGE,
            ABOUT_PAGE,
            ACCOUNT_PAGE,
            LOGOUT_PAGE,
        ]
    else:
        pages = [
            HOME_PAGE,
            REVIEW_PAGE,
            LLM_REVIEW_PAGE,
            COLUMN_MAPPING_PAGE,
            PROJECTS_PAGE,
            ABOUT_PAGE,
            ACCOUNT_PAGE,
            LOGOUT_PAGE,
        ]
    navigation = st.navigation(pages, position="hidden")
    navigation.run()


if __name__ == "__main__":
    run_app()
