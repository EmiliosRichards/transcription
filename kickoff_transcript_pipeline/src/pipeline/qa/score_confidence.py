from typing import List, Dict, Any


def _token_count(text: str) -> int:
    return len(text.split()) if text else 0


def score_confidence(lines: List[Dict[str, Any]], *, weights: Dict[str, float] | None = None,
                     thresholds: Dict[str, float] | None = None) -> List[Dict[str, Any]]:
    weights = weights or {
        "add_kt_high": 0.25,
        "add_kc_high": 0.25,
        "penalize_kt_low": -0.10,
        "penalize_short": -0.05,
    }
    thresholds = thresholds or {
        "kt_high": 0.65,
        "kc_high": 0.65,
        "kt_low": 0.40,
        "short_tokens": 4,
    }
    scored: List[Dict[str, Any]] = []
    for line in lines:
        sim_kt = float(line.get("sim_kt", 0.0))  # Krisp-Teams
        sim_kc = float(line.get("sim_kc", 0.0))  # Krisp-Charla
        text = line.get("text", "")
        conf = 0.0
        if sim_kt >= thresholds["kt_high"]:
            conf += weights["add_kt_high"]
        if sim_kc >= thresholds["kc_high"]:
            conf += weights["add_kc_high"]
        if sim_kt < thresholds["kt_low"]:
            conf += weights["penalize_kt_low"]
        if _token_count(text) <= thresholds["short_tokens"]:
            conf += weights["penalize_short"]
        conf = max(0.0, min(1.0, conf))
        new_line = dict(line)
        new_line["conf"] = conf
        scored.append(new_line)
    return scored
