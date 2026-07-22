from io import BytesIO
import unittest

import pandas as pd

from mira_data import (
    MemoryUpload,
    dynamic_rating_column,
    ensure_dynamic_rating_columns,
    ensure_review_columns,
    fetch_google_drive_file,
    load_dataframe,
    rating_from_scale,
)


class MiraDataTests(unittest.TestCase):
    def test_csv_upload_and_review_columns(self):
        upload = MemoryUpload(b"prompt,response\nhello,world\n", "sample.csv")
        frame = ensure_review_columns(load_dataframe(upload))
        self.assertEqual(frame.loc[0, "prompt"], "hello")
        self.assertIn("reviewer_notes", frame.columns)

    def test_excel_upload(self):
        buffer = BytesIO()
        pd.DataFrame({"prompt": ["hello"]}).to_excel(buffer, index=False)
        upload = MemoryUpload(buffer.getvalue(), "sample.xlsx")
        self.assertEqual(load_dataframe(upload).loc[0, "prompt"], "hello")

    def test_dynamic_ratings_are_nullable_integers(self):
        frame = ensure_dynamic_rating_columns(pd.DataFrame({"answer": ["a"]}), ["answer"])
        column = dynamic_rating_column("answer", "context_relevance_rating")
        self.assertEqual(str(frame[column].dtype), "Int64")
        self.assertTrue(pd.isna(frame.loc[0, column]))

    def test_scale_validation(self):
        self.assertIsNone(rating_from_scale(""))
        self.assertIsNone(rating_from_scale(6))
        self.assertEqual(rating_from_scale("4"), 4)

    def test_drive_download_rejects_untrusted_hosts(self):
        with self.assertRaises(ValueError):
            fetch_google_drive_file("https://example.com/private.xlsx")


if __name__ == "__main__":
    unittest.main()
