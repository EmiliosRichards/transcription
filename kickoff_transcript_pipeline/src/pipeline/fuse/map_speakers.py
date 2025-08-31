from typing import List, Dict, Any
from collections import Counter


def _normalize_name(name: str) -> str:
    if not name:
        return ""
    name = name.strip()
    if name.startswith("<v ") and name.endswith(">"):
        name = name[3:-1].strip()
    return name


def map_speakers_via_alignment(
    krisp_segments: List[Dict[str, Any]], aligned_items: List[Dict[str, Any]], window_required: int = 3
) -> List[Dict[str, Any]]:
    """Assign real names to Krisp speakers using aligned Teams speakers by majority vote.

    aligned_items are the {k, t[], c[]} entries for the same krisp_segments order.
    """
    name_by_krisp_speaker: Dict[str, str] = {}

    # Build votes per Krisp speaker (nearest Teams name only)
    votes: Dict[str, Counter] = {}
    for item in aligned_items:
        k = item.get("k", {})
        k_speaker = str(k.get("speaker", "")).strip()
        t_list = item.get("t", [])
        if not t_list:
            continue
        # Find nearest Teams cue by mid time
        kt = int(k.get("t_start") or 0)
        best_name = ""
        best_d = 10**9
        for t in t_list:
            name = _normalize_name(str(t.get("speaker", "")))
            if not name:
                continue
            ts = int(t.get("t_start") or 0)
            te_val = t.get("t_end")
            te = int(te_val) if te_val is not None else ts
            mid = (ts + te) // 2
            d = abs(kt - mid)
            if d < best_d:
                best_d = d
                best_name = name
        if best_name:
            votes.setdefault(k_speaker, Counter()).update([best_name])

    # Primary assignment: top vote per Krisp speaker
    for k_spk, counter in votes.items():
        if counter:
            best, _ = counter.most_common(1)[0]
            name_by_krisp_speaker[k_spk] = best

    # If multiple Krisp speakers map to the same name, try to separate by second choice
    used = set()
    for k_spk in list(name_by_krisp_speaker.keys()):
        name = name_by_krisp_speaker[k_spk]
        if name in used:
            counter = votes.get(k_spk, Counter())
            for cand, _ in counter.most_common():
                if cand not in used:
                    name_by_krisp_speaker[k_spk] = cand
                    break
        used.add(name_by_krisp_speaker[k_spk])

    # Rewrite Krisp speakers where we have a mapping
    remapped: List[Dict[str, Any]] = []
    for seg in krisp_segments:
        spk = str(seg.get("speaker", "")).strip()
        new = dict(seg)
        if spk in name_by_krisp_speaker:
            new["speaker"] = name_by_krisp_speaker[spk]
        remapped.append(new)

    return remapped
