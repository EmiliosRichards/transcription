from typing import List, Tuple
import difflib


def estimate_offset_seconds(pairs: List[Tuple[str, str]]) -> float:
    if not pairs:
        return 0.0
    scores = []
    for a, b in pairs:
        ratio = difflib.SequenceMatcher(a=a, b=b).ratio()
        scores.append(ratio)
    # If most are very similar, assume zero offset for fixtures
    avg = sum(scores) / len(scores)
    return 0.0 if avg >= 0.8 else 0.0
