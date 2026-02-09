from __future__ import annotations

from pathlib import Path


def _default_rubric_file() -> Path:
    # Resolve relative to this package so it works regardless of CWD.
    return (Path(__file__).resolve().parent / "rubrics" / "manuav_rubric_v4_en.md").resolve()


def load_rubric_text(rubric_file: str | None) -> tuple[str, str]:
    """Returns (rubric_path_str, rubric_text)."""
    path = Path(rubric_file).resolve() if rubric_file else _default_rubric_file()
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Rubric file is empty: {path}")
    return str(path), text

