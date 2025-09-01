from typing import List, Dict, Any


def is_garbled(text: str) -> bool:
    if not text:
        return False
    letters = sum(ch.isalpha() for ch in text)
    ratio = letters / max(1, len(text))
    # Heuristic: very low alphabetic ratio or contains odd fragments
    return ratio < 0.45 or any(fr in text for fr in ["Würde wert", "Ich dir.", "... ..."])  # quick signal only


def choose_text(krisp_text: str, teams_text: str | None, charla_text: str | None) -> str:
    if is_garbled(krisp_text):
        # Prefer Teams if available, else Charla
        if teams_text and not is_garbled(teams_text):
            return teams_text
        if charla_text and not is_garbled(charla_text):
            return charla_text
    return krisp_text
