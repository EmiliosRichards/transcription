from src.pipeline.fuse.filter_fillers import filter_fillers_and_duplicates

from src.pipeline.qa.score_confidence import score_confidence


def test_filter_fillers_and_duplicates():
    lines = [
        {"t": 0, "speaker": "A", "text": "yeah"},
        {"t": 1, "speaker": "A", "text": "yeah"},
        {"t": 10, "speaker": "A", "text": "meaningful content here"},
        {"t": 12, "speaker": "A", "text": "meaningful content here"},
    ]
    out = filter_fillers_and_duplicates(lines, filler_max_tokens=3, duplicate_window_sec=5)
    # removes both short fillers and second duplicate within window
    assert len(out) == 1
    assert out[0]["text"] == "meaningful content here"


def test_score_confidence():
    lines = [
        {"text": "short", "sim_kt": 0.7, "sim_kc": 0.7},
        {"text": "long enough content", "sim_kt": 0.3, "sim_kc": 0.2},
    ]
    out = score_confidence(lines)
    assert 0.0 <= out[0]["conf"] <= 1.0
    assert 0.0 <= out[1]["conf"] <= 1.0
