import json
from pathlib import Path

from src.pipeline.ingest.read_krisp import read_krisp_txt
from src.pipeline.ingest.read_charla import read_charla_txt
from src.pipeline.ingest.read_teams import read_teams_docx


def test_read_krisp(tmp_path: Path):
    p = Path("data_in/krisp.txt").resolve()
    segs = read_krisp_txt(p)
    assert len(segs) >= 10
    assert segs[0]["source"] == "krisp"
    assert segs[0]["t_start"] == 0


def test_read_charla(tmp_path: Path):
    p = Path("data_in/charla.txt").resolve()
    segs = read_charla_txt(p)
    assert len(segs) >= 10
    assert segs[0]["source"] == "charla"
    assert segs[0]["t_start"] == 0


def test_read_teams(tmp_path: Path):
    p = Path("data_in/teams.docx").resolve()
    segs = read_teams_docx(p)
    assert len(segs) >= 10
    assert segs[0]["source"] == "teams"
    assert segs[0]["t_start"] == 0
