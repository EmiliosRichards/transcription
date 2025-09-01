from typing import List, Dict, Any

_FILLER_WORDS = {
    # English
    "yeah", "okay", "ok", "um", "uh", "right", "hmm", "mh", "mhm",
    # German
    "ja", "okay", "ok", "äh", "uh", "hm", "hmm", "jo", "nee", "mh"
}


def filter_fillers_and_duplicates(lines: List[Dict[str, Any]], filler_max_tokens: int, duplicate_window_sec: int) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    last_by_speaker: Dict[str, Dict[str, Any]] = {}
    for line in lines:
        text = line.get("text", "")
        tokens = text.split()
        # Remove short fillers only if composed of known (en/de) filler words
        if len(tokens) <= filler_max_tokens:
            lowered = [t.lower().strip(",.!?;:") for t in tokens]
            if lowered and all(t in _FILLER_WORDS for t in lowered):
                continue
        speaker = line.get("speaker", "")
        t = line.get("t") or line.get("t_start") or 0
        prev = last_by_speaker.get(speaker)
        if prev is not None:
            prev_t = prev.get("t") or prev.get("t_start") or 0
            if abs((t or 0) - (prev_t or 0)) <= duplicate_window_sec and text.strip().lower() == prev.get("text", "").strip().lower():
                # Collapse duplicate: skip this one
                continue
        filtered.append(line)
        last_by_speaker[speaker] = line
    return filtered
