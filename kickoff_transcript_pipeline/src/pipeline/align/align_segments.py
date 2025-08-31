from typing import List, Dict, Any


def _within_window_using_end(t_ref: int, t_start: int, t_end: int | None, window_sec: int) -> bool:
    if t_end is not None:
        return (t_start - window_sec) <= t_ref <= (t_end + window_sec)
    return abs(int(t_ref) - int(t_start)) <= window_sec


def _within_window(t_ref: int, t_other: int, window_sec: int) -> bool:
    return abs(int(t_ref) - int(t_other)) <= window_sec


def align_segments(
    krisp: List[Dict[str, Any]],
    teams: List[Dict[str, Any]],
    charla: List[Dict[str, Any]],
    *,
    window_sec: int = 3,
) -> List[Dict[str, Any]]:
    """Naive time-window alignment.

    For each Krisp line, collect nearest Teams/Charla lines within +/- window seconds.
    Returns a list of aligned items: {k, t[], c[]}. Order follows Krisp.
    """
    # Index teams/charla by time for cheap scans
    t_sorted = sorted(teams, key=lambda x: int(x.get("t_start") or x.get("t") or 0))
    c_sorted = sorted(charla, key=lambda x: int(x.get("t_start") or x.get("t") or 0))

    aligned: List[Dict[str, Any]] = []
    ti = 0
    ci = 0

    for k in sorted(krisp, key=lambda x: int(x.get("t_start") or x.get("t") or 0)):
        kt = int(k.get("t_start") or k.get("t") or 0)
        # advance cursors close to window start
        while ti < len(t_sorted) and int(t_sorted[ti].get("t_start") or 0) < kt - window_sec:
            ti += 1
        while ci < len(c_sorted) and int(c_sorted[ci].get("t_start") or 0) < kt - window_sec:
            ci += 1

        # collect candidates in window
        t_matches: List[Dict[str, Any]] = []
        cj = ci
        tj = ti
        while tj < len(t_sorted):
            t_item = t_sorted[tj]
            tt = int(t_item.get("t_start") or 0)
            te = t_item.get("t_end")
            if tt > kt + window_sec and (te is None or te > kt + window_sec):
                break
            if _within_window_using_end(kt, tt, (int(te) if te is not None else None), window_sec):
                t_matches.append(t_item)
            tj += 1
        c_matches: List[Dict[str, Any]] = []
        while cj < len(c_sorted):
            c_item = c_sorted[cj]
            ct = int(c_item.get("t_start") or 0)
            if ct > kt + window_sec:
                break
            if _within_window(kt, ct, window_sec):
                c_matches.append(c_item)
            cj += 1

        aligned.append({"k": k, "t": t_matches, "c": c_matches})

    return aligned
