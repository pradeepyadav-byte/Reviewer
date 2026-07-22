from io import BytesIO
from pathlib import Path
import tempfile
from typing import Optional
from urllib.parse import urlparse

import pandas as pd


RATING_COLUMNS = {
    "context_relevance_rating": "Context & Relevance",
    "emotionx_usage_rating": "EmotionX Usage",
    "language_alignment_rating": "Language Alignment",
    "safety_alignment_rating": "Safety Alignment",
}
RATING_MEANINGS = {
    1: "Very poor",
    2: "Poor",
    3: "Average",
    4: "Good",
    5: "Excellent",
}
REVIEW_COLUMNS = [
    "review_choice",
    "final_response",
    "reviewer_notes",
    "reviewed_status",
]


class MemoryUpload(BytesIO):
    """UploadedFile-compatible in-memory file fetched from Google Drive."""

    def __init__(self, data: bytes, name: str):
        super().__init__(data)
        self.name = name
        self.size = len(data)


def display_text(value) -> str:
    """Render empty pandas cells as blank text instead of 'nan'."""
    return "" if pd.isna(value) else str(value)


def rating_from_scale(value) -> Optional[int]:
    """Return a valid numeric 1–5 rating from the scale widget."""
    if value is None or value == "":
        return None
    rating = int(value)
    return rating if 1 <= rating <= 5 else None


def dynamic_rating_column(source_column, rating_column: str) -> str:
    """Build a rating output column tied to one selected source column."""
    return f"{source_column}_{rating_column}"


def ensure_dynamic_rating_columns(
    df: pd.DataFrame,
    source_columns: list,
) -> pd.DataFrame:
    """Add numeric rating columns for every criteria-enabled source column."""
    for source_column in source_columns:
        for rating_column in RATING_COLUMNS:
            output_column = dynamic_rating_column(source_column, rating_column)
            if output_column not in df.columns:
                df[output_column] = pd.Series(pd.NA, index=df.index, dtype="Int64")
            else:
                df[output_column] = pd.to_numeric(
                    df[output_column],
                    errors="coerce",
                ).astype("Int64")
    return df


def load_dataframe(uploaded_file) -> pd.DataFrame:
    """Load a CSV, XLS, or XLSX upload into a DataFrame."""
    filename = uploaded_file.name.lower()
    buffer = BytesIO(uploaded_file.read())
    if filename.endswith(".csv"):
        return pd.read_csv(buffer)
    return pd.read_excel(buffer)


def fetch_google_drive_file(shared_url: str) -> MemoryUpload:
    """Download a public Google Drive spreadsheet used by a Colab workflow."""
    parsed_url = urlparse(shared_url.strip())
    allowed_hosts = {"drive.google.com", "docs.google.com"}
    if parsed_url.scheme != "https" or parsed_url.hostname not in allowed_hosts:
        raise ValueError("Enter a valid HTTPS Google Drive or Google Sheets link.")
    try:
        import gdown
    except ImportError as exc:
        raise RuntimeError(
            "Google Drive support requires the `gdown` package."
        ) from exc

    with tempfile.TemporaryDirectory() as temp_dir:
        downloaded_path = gdown.download(
            url=shared_url,
            output=f"{temp_dir}/",
            quiet=True,
            fuzzy=True,
        )
        if not downloaded_path:
            raise ValueError(
                "Could not download the file. Ensure the Drive link is shared "
                "with anyone who has the link."
            )
        path = Path(downloaded_path)
        if path.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
            raise ValueError("Google Drive file must be a CSV, XLSX, or XLS file.")
        return MemoryUpload(path.read_bytes(), path.name)


def ensure_review_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add review columns and normalize their text and numeric dtypes."""
    deprecated = [
        column for column in df.columns if str(column).endswith("_overall_rating")
    ]
    if deprecated:
        df = df.drop(columns=deprecated)
    for column in REVIEW_COLUMNS:
        if column not in df.columns:
            df[column] = ""
        else:
            df[column] = df[column].map(display_text)
        df[column] = df[column].astype("object")
    return df
