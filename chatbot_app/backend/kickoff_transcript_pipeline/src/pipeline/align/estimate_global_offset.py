from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional
import re
import difflib


_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[\.,!?:;·•—\-\"'()\[\]{}]")


def _normalize_text(s: str) -> str:
    s2 = s or ""
    s2 = s2.lower()
    s2 = _PUNCT_RE.sub(" ", s2)
    s2 = _WS_RE.sub(" ", s2).strip()
    return s2


def _tokenize(s: str) -> List[str]:
    return [t for t in _normalize_text(s).split() if t]


def _char_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _lcs_ratio(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    na, nb = len(a), len(b)
    dp = [0] * (nb + 1)
    for i in range(1, na + 1):
        prev = 0
        for j in range(1, nb + 1):
            tmp = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev + 1
            else:
                dp[j] = dp[j] if dp[j] >= dp[j - 1] else dp[j - 1]
            prev = tmp
    lcs = dp[nb]
    return lcs / float(max(na, nb))


def _content_similarity(a_text: str, b_text: str) -> float:
    a_norm = _normalize_text(a_text)
    b_norm = _normalize_text(b_text)
    if not a_norm or not b_norm:
        return 0.0
    c = _char_similarity(a_norm, b_norm)
    a_tok = a_norm.split()
    b_tok = b_norm.split()
    l = _lcs_ratio(a_tok, b_tok)
    return max(c, l)


def _regex_phrase(words: List[str]) -> Optional[re.Pattern[str]]:
    if not words:
        return None
    # word boundary and non-word gaps between tokens
    escaped = [re.escape(w) for w in words]
    pat = r"\b" + r"\W+".join(escaped) + r"\b"
    try:
        return re.compile(pat, re.IGNORECASE)
    except Exception:
        return None


@dataclass
class AnchorHit:
    teams_t: int
    teams_text: str
    target_t: int
    target_text: str
    phrase: str
    window_sec: int
    score: float
    method: str  # "exact" | "regex" | "similarity"


@dataclass
class OffsetResult:
    offset_sec: int
    begin_hit: Optional[AnchorHit]
    end_hit: Optional[AnchorHit]
    diagnostics: Dict[str, Any]


def _generate_phrases(text: str, min_tokens: int, max_tokens: int, max_variants: int = 8) -> List[str]:
    toks = _tokenize(text)
    phrases: List[str] = []
    starts = list(range(0, min(3, max(0, len(toks) - min_tokens + 1))))
    for start in starts:
        for k in range(min_tokens, min(max_tokens, len(toks) - start) + 1):
            phrases.append(" ".join(toks[start : start + k]))
            if len(phrases) >= max_variants:
                return phrases
    return phrases


def _search_horizons() -> List[int]:
    # exponential growth: 180 → 360 → 720 → 1200
    return [180, 360, 720, 1200]


def _find_anchor(
    teams_side: List[Dict[str, Any]],
    target_side: List[Dict[str, Any]],
    at_end: bool,
    min_phrase_tokens: int,
    max_phrase_tokens: int,
    similarity_threshold: float,
    expand_tokens: int,
    lines_after: int,
) -> Tuple[Optional[AnchorHit], Dict[str, Any]]:
    diag: Dict[str, Any] = {"attempts": []}
    if not teams_side or not target_side:
        return None, {"reason": "empty_inputs"}

    # pick candidate Teams segments near begin or end
    T = teams_side if not at_end else list(reversed(teams_side))
    T = T[:20]

    # pre-concatenate target texts with timestamps list for quick horizon slicing
    first_t = target_side[0]["t_start"] if target_side else 0
    last_t = target_side[-1]["t_start"] if target_side else 0

    for horizon in _search_horizons():
        # Build horizon subset
        if not at_end:
            band = [x for x in target_side if (x["t_start"] - first_t) <= horizon]
        else:
            band = [x for x in target_side if (last_t - x["t_start"]) <= horizon]
        band_texts = [str(x.get("text", "")) for x in band]
        band_norm = [ _normalize_text(s) for s in band_texts ]
        # stitched windows of subsequent lines to firm up a local hit
        def stitched_forward(i: int, lines_after: int = lines_after) -> str:
            lo = i
            hi = min(len(band), i + 1 + max(1, lines_after))
            return " ".join(band_texts[lo:hi]).strip()

        for tseg in T:
            t_text = str(tseg.get("text", ""))
            phrases = _generate_phrases(t_text, min_phrase_tokens, max_phrase_tokens)
            for phr in phrases:
                attempt = {"teams_t": tseg.get("t_start", 0), "phrase": phr, "horizon": horizon}
                diag["attempts"].append(attempt)
                # exact / regex pre-check across band
                rex = _regex_phrase(phr.split())
                # skip-1 token tolerant regex (allow one unexpected middle token)
                toks = phr.split()
                rex_skip1 = None
                if len(toks) >= 2:
                    try:
                        pat = r"\b" + re.escape(toks[0]) + r"(?:\W+\w+)?\W+" + re.escape(toks[1]) + r"\b"
                        rex_skip1 = re.compile(pat, re.IGNORECASE)
                    except Exception:
                        rex_skip1 = None
                best: Optional[AnchorHit] = None
                best_margin = 0.0
                for i, norm in enumerate(band_norm):
                    # exact substring fast check
                    if phr in norm:
                        stitched_txt = stitched_forward(i)
                        # validate with local stitched window vs equal-length Teams slice
                        teams_tokens = _tokenize(t_text)
                        target_tokens = _tokenize(stitched_txt)
                        take = min(len(target_tokens), len(teams_tokens))
                        teams_slice = " ".join(teams_tokens[:take])
                        sc = _content_similarity(teams_slice, " ".join(target_tokens[:take]))
                        if sc >= max(0.5, similarity_threshold - 0.1):
                            hit = AnchorHit(
                                teams_t=int(tseg.get("t_start", 0)),
                                teams_text=t_text,
                                target_t=int(band[i]["t_start"]),
                                target_text=stitched_txt,
                                phrase=phr,
                                window_sec=horizon,
                                score=sc,
                                method="exact",
                            )
                            best = hit
                            best_margin = sc
                            break
                    # regex
                    matched_regex = (rex and rex.search(norm)) or (rex_skip1 and rex_skip1.search(norm))
                    if matched_regex:
                        stitched_txt = stitched_forward(i)
                        teams_tokens = _tokenize(t_text)
                        target_tokens = _tokenize(stitched_txt)
                        take = min(len(target_tokens), len(teams_tokens))
                        teams_slice = " ".join(teams_tokens[:take])
                        sc = _content_similarity(teams_slice, " ".join(target_tokens[:take]))
                        if sc >= max(0.5, similarity_threshold - 0.1) and sc > best_margin + 0.05:
                            best = AnchorHit(
                                teams_t=int(tseg.get("t_start", 0)),
                                teams_text=t_text,
                                target_t=int(band[i]["t_start"]),
                                target_text=stitched_txt,
                                phrase=phr,
                                window_sec=horizon,
                                score=sc,
                                method="regex",
                            )
                            best_margin = sc
                if best:
                    return best, diag

                # similarity on stitched windows (forward few lines)
                for i in range(len(band)):
                    stitched_txt = stitched_forward(i)
                    teams_tokens = _tokenize(t_text)
                    target_tokens = _tokenize(stitched_txt)
                    take = min(len(target_tokens), len(teams_tokens))
                    teams_slice = " ".join(teams_tokens[:take])
                    sc = _content_similarity(teams_slice, " ".join(target_tokens[:take]))
                    if sc >= max(0.5, similarity_threshold - 0.05):
                        return (
                            AnchorHit(
                                teams_t=int(tseg.get("t_start", 0)),
                                teams_text=t_text,
                                target_t=int(band[i]["t_start"]),
                                target_text=stitched_txt,
                                phrase=phr,
                                window_sec=horizon,
                                score=sc,
                                method="similarity",
                            ),
                            diag,
                        )

    return None, diag


def estimate_global_offset_and_bounds(
    teams_segments: List[Dict[str, Any]],
    krisp_segments: List[Dict[str, Any]],
    gpt_segments: Optional[List[Dict[str, Any]]],
    *,
    min_phrase_tokens: int = 2,
    max_phrase_tokens: int = 5,
    similarity_threshold: float = 0.70,
    expand_tokens: int = 8,
    end_similarity_threshold: Optional[float] = None,
    begin_lines_after: int = 3,
    end_lines_after: int = 4,
) -> OffsetResult:
    # Find begin/end anchors for Krisp
    begin_hit, begin_diag = _find_anchor(
        teams_segments, krisp_segments, at_end=False,
        min_phrase_tokens=min_phrase_tokens,
        max_phrase_tokens=max_phrase_tokens,
        similarity_threshold=similarity_threshold,
        expand_tokens=expand_tokens,
        lines_after=begin_lines_after,
    )
    end_hit, end_diag = _find_anchor(
        teams_segments, krisp_segments, at_end=True,
        min_phrase_tokens=min_phrase_tokens,
        max_phrase_tokens=max_phrase_tokens,
        similarity_threshold=(end_similarity_threshold if isinstance(end_similarity_threshold, (int, float)) else similarity_threshold),
        expand_tokens=expand_tokens,
        lines_after=end_lines_after,
    )

    offset_sec = 0
    if begin_hit is not None:
        offset_sec = int(begin_hit.target_t - begin_hit.teams_t)

    diagnostics: Dict[str, Any] = {
        "begin": begin_diag,
        "end": end_diag,
        "krisp_begin": begin_hit.__dict__ if begin_hit else None,
        "krisp_end": end_hit.__dict__ if end_hit else None,
        "params": {
            "min_phrase_tokens": min_phrase_tokens,
            "max_phrase_tokens": max_phrase_tokens,
            "similarity_threshold": similarity_threshold,
            "expand_tokens": expand_tokens,
            "end_similarity_threshold": end_similarity_threshold if end_similarity_threshold is not None else similarity_threshold,
            "begin_lines_after": begin_lines_after,
            "end_lines_after": end_lines_after,
        },
    }

    # Optionally also try GPT for diagnostics (no offset derived from GPT)
    if gpt_segments:
        g_begin, g_begin_diag = _find_anchor(
            teams_segments, gpt_segments, at_end=False,
            min_phrase_tokens=min_phrase_tokens,
            max_phrase_tokens=max_phrase_tokens,
            similarity_threshold=similarity_threshold,
            expand_tokens=expand_tokens,
            lines_after=begin_lines_after,
        )
        g_end, g_end_diag = _find_anchor(
            teams_segments, gpt_segments, at_end=True,
            min_phrase_tokens=min_phrase_tokens,
            max_phrase_tokens=max_phrase_tokens,
            similarity_threshold=(end_similarity_threshold if isinstance(end_similarity_threshold, (int, float)) else similarity_threshold),
            expand_tokens=expand_tokens,
            lines_after=end_lines_after,
        )
        diagnostics["gpt_begin"] = g_begin.__dict__ if g_begin else None
        diagnostics["gpt_end"] = g_end.__dict__ if g_end else None
        diagnostics["gpt_begin_diag"] = g_begin_diag
        diagnostics["gpt_end_diag"] = g_end_diag

    return OffsetResult(offset_sec=offset_sec, begin_hit=begin_hit, end_hit=end_hit, diagnostics=diagnostics)


