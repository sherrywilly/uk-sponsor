"""
csv_exporter.py — Exports scraped job data to a CSV file using Pandas.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from loguru import logger

# Column order and display names for the output CSV
_COLUMNS: list[str] = [
    "company",
    "job_title",
    "location",
    "department",
    "employment_type",
    "salary",
    "visa_sponsorship",
    "required_skills",
    "preferred_skills",
    "job_description",
    "apply_url",
]

_COLUMN_DISPLAY_NAMES: dict[str, str] = {
    "company": "Company",
    "job_title": "Job Title",
    "location": "Location",
    "department": "Department",
    "employment_type": "Employment Type",
    "salary": "Salary",
    "visa_sponsorship": "Visa Sponsorship",
    "required_skills": "Required Skills",
    "preferred_skills": "Preferred Skills",
    "job_description": "Job Description",
    "apply_url": "Apply URL",
}

_OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "output")


class CSVExporter:
    """
    Converts a list of job dicts to a clean CSV file.

    Usage::

        exporter = CSVExporter()
        path = exporter.export(jobs, company="Acme")
    """

    def __init__(self, output_dir: str = _OUTPUT_DIR) -> None:
        self._output_dir = Path(output_dir)

    def export(self, jobs: list[dict], *, company: str = "", filename: str = "jobs.csv") -> Path:
        """
        Write *jobs* to ``<output_dir>/<filename>`` and return the file path.

        Also writes a timestamped copy so historical runs are preserved.
        """
        if not jobs:
            logger.warning("No jobs to export.")
            return self._output_dir / filename

        self._output_dir.mkdir(parents=True, exist_ok=True)

        df = self._build_dataframe(jobs)

        # ── Primary output file ──────────────────────────────────────────
        primary_path = self._output_dir / filename
        df.to_csv(primary_path, index=False, encoding="utf-8-sig")
        logger.success("Exported {} job(s) to: {}", len(df), primary_path)

        # ── Timestamped backup ───────────────────────────────────────────
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        company_slug = self._slugify(company) if company else "jobs"
        backup_name = f"{company_slug}_{ts}.csv"
        backup_path = self._output_dir / backup_name
        df.to_csv(backup_path, index=False, encoding="utf-8-sig")
        logger.info("Timestamped backup saved to: {}", backup_path)

        # ── Summary printout ─────────────────────────────────────────────
        self._print_summary(df)

        return primary_path

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_dataframe(self, jobs: list[dict]) -> pd.DataFrame:
        """Build a clean, consistently-ordered DataFrame from raw job dicts."""
        # Ensure every expected column is present (fill missing with empty string)
        normalised: list[dict] = []
        for job in jobs:
            row = {col: job.get(col, "") for col in _COLUMNS}
            normalised.append(row)

        df = pd.DataFrame(normalised, columns=_COLUMNS)

        # Rename columns for human-friendly headers
        df.rename(columns=_COLUMN_DISPLAY_NAMES, inplace=True)

        # Strip leading/trailing whitespace from all string columns
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()

        # Replace literal "None" / "nan" artefacts with empty string
        df.replace({"None": "", "nan": "", "NaN": ""}, inplace=True)

        return df

    @staticmethod
    def _print_summary(df: pd.DataFrame) -> None:
        """Log a brief summary of what was exported."""
        logger.info("=== Export Summary ===")
        logger.info("Total jobs exported : {}", len(df))

        if "Location" in df.columns:
            top_locations = df["Location"].value_counts().head(5)
            logger.info("Top locations:\n{}", top_locations.to_string())

        if "Department" in df.columns:
            top_depts = df["Department"].value_counts().head(5)
            logger.info("Top departments:\n{}", top_depts.to_string())

        if "Visa Sponsorship" in df.columns:
            sponsorship_counts = df["Visa Sponsorship"].value_counts()
            logger.info("Visa sponsorship breakdown:\n{}", sponsorship_counts.to_string())

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to a safe filename slug."""
        import re

        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_-]+", "_", text)
        return text[:50]
