from src.pipeline.qa.score_confidence import score_confidence


def test_confidence_tuning_overrides():
    lines = [
        {"text": "short", "sim_kt": 0.9, "sim_kc": 0.9},
        {"text": "long enough content", "sim_kt": 0.1, "sim_kc": 0.1},
    ]
    weights = {
        "add_kt_high": 0.3,
        "add_kc_high": 0.3,
        "penalize_kt_low": -0.2,
        "penalize_short": -0.1,
    }
    thresholds = {
        "kt_high": 0.8,
        "kc_high": 0.8,
        "kt_low": 0.2,
        "short_tokens": 4,
    }
    out = score_confidence(lines, weights=weights, thresholds=thresholds)
    for l in out:
        assert 0.0 <= l["conf"] <= 1.0
