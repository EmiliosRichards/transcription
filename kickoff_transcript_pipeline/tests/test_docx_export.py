from pathlib import Path
from src.pipeline.export.write_master_docx import write_master_docx


def test_write_master_docx(tmp_path: Path):
    lines = [
        {"t": 0, "speaker": "A", "text": "hello"},
        {"t": 65, "speaker": "B", "text": "world"},
        {"t": 320, "speaker": "A", "text": "next chapter"},
    ]
    out_path = tmp_path / "master.docx"
    write_master_docx(lines, out_path, chapter_minutes=5)
    assert out_path.exists()
    assert out_path.stat().st_size > 0
