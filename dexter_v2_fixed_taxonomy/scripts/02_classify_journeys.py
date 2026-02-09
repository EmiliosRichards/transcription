import argparse
import csv
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
    load_dotenv(find_dotenv(usecwd=True))
except Exception:
    pass


UNREACHABLE_HINTS = [
    "anrufbeantworter",
    "mailbox",
    "sprachbox",
    "voicemail",
    "nicht erreichbar",
]

KNOWN_SYSTEM_VARIANTS: List[Tuple[str, List[str]]] = [
    ("medifox", ["medifox", "medifoks", "medefoks", "medefolks", "medi fox"]),
    ("connext vivendi", ["connext vivendi", "connex vivendi", "konnext vivendi", "connext", "vivendi"]),
    ("dahn", ["dahn"]),
    ("sinfonie", ["sinfonie", "synfonie"]),
    ("snap", ["snap"]),
    ("mikos", ["mikos"]),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Classify each journey into a fixed GK/DM category list.")
    p.add_argument("--in", dest="inp", required=True, help="Input grouped JSONL (calls_grouped.jsonl)")
    p.add_argument("--taxonomy", required=True, help="categories.json produced by 00_extract_categories_from_excel.py")
    p.add_argument("--out-jsonl", required=True, help="Output JSONL classifications")
    p.add_argument("--out-csv", required=True, help="Output CSV classifications")
    p.add_argument("--model", default=os.environ.get("DEXTER_V2_MODEL", "gpt-4o-mini"), help="OpenAI model")
    p.add_argument("--max-workers", type=int, default=4, help="Parallel workers")
    p.add_argument(
        "--max-journeys",
        type=int,
        default=None,
        help="Optional cap on number of journeys to classify (cost control). Applies after reading input order.",
    )
    p.add_argument("--min-journey-words", type=int, default=15, help="Minimum total words required to send a journey to the LLM")
    p.add_argument("--max-context-words", type=int, default=20000, help="Max words of transcript text to send (most-recent calls first)")
    p.add_argument("--max-calls", type=int, default=999999, help="Max most-recent calls to include before word cap applies")
    p.add_argument("--temperature", type=float, default=0.0, help="Temperature (keep 0 for deterministic)")
    p.add_argument(
        "--disable-shortcuts",
        action="store_true",
        help="Disable early shortcuts for empty/unreachable journeys (forces LLM call). Useful for token/cost analysis.",
    )
    p.add_argument(
        "--heuristic",
        action="store_true",
        help="Run without OpenAI calls (local heuristic match against taxonomy quotes). Useful for smoke tests.",
    )
    return p.parse_args()


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def _word_count(text: str) -> int:
    return len([w for w in (text or "").split() if w])


def is_unreachable(text: str) -> bool:
    t = (text or "").lower()
    return any(h in t for h in UNREACHABLE_HINTS)


def build_context(calls: List[Dict[str, Any]], *, max_words: int, max_calls: int) -> Tuple[str, int, int]:
    """
    Build context by prioritizing MOST RECENT calls while keeping total transcript words <= max_words.
    Selected calls are stitched together in CHRONOLOGICAL order.

    Returns: (context_text, selected_calls_count, selected_words_count)
    """
    calls_sorted = sorted(calls, key=lambda c: str(c.get("started") or ""))  # chronological
    recent = calls_sorted[-max(1, int(max_calls or 1)) :]

    selected_rev: List[Dict[str, Any]] = []
    total_words = 0
    # pick from the end (most recent) backwards
    for c in reversed(recent):
        txt = str(c.get("transcript_text") or "")
        wc = _word_count(txt)
        # Always allow at least one call (even if it exceeds max_words)
        if selected_rev and max_words > 0 and (total_words + wc) > max_words:
            break
        selected_rev.append(c)
        total_words += wc
        if max_words > 0 and total_words >= max_words:
            break

    selected = list(reversed(selected_rev))  # back to chronological
    lines: List[str] = []
    for i, c in enumerate(selected, start=1):
        started = str(c.get("started") or "")
        audio_id = str(c.get("audio_id") or "")
        txt = str(c.get("transcript_text") or "")
        lines.append(f"[Call {i}/{len(selected)} started={started} audio_id={audio_id}]\n{txt}\n")
    ctx = "\n".join(lines).strip()
    return ctx, len(selected), total_words


def parse_taxonomy_labels(taxonomy: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    gk = [str(x.get("label") or "").strip() for x in (taxonomy.get("gatekeeper") or [])]
    dm = [str(x.get("label") or "").strip() for x in (taxonomy.get("decision_maker") or [])]
    gk = [x for x in gk if x]
    dm = [x for x in dm if x]
    return gk, dm


def parse_taxonomy_items(taxonomy: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    gk = list(taxonomy.get("gatekeeper") or [])
    dm = list(taxonomy.get("decision_maker") or [])
    return gk, dm


def build_label_to_id(items: List[Dict[str, Any]], prefix: str) -> Dict[str, str]:
    m: Dict[str, str] = {}
    for it in items:
        label = str(it.get("label") or "").strip()
        cid = str(it.get("id") or "").strip()
        if label and cid:
            m[label] = cid
    # Ensure a stable fallback for Other/Unclear
    m.setdefault("Other/Unclear", f"{prefix}00")
    return m


def strict_choice(value: str, allowed: List[str]) -> str:
    v = (value or "").strip()
    if v in allowed:
        return v
    return "Other/Unclear"


def _evidence_in_context(evidence: str, calls: List[Dict[str, Any]]) -> bool:
    ev = (evidence or "").strip()
    if not ev:
        return True
    joined = "\n".join(str(c.get("transcript_text") or "") for c in calls)
    return ev in joined


def _norm(s: str) -> str:
    # light normalization for matching
    t = (s or "").lower()
    t = re.sub(r"\s+", " ", t).strip()
    return t


def canonicalize_system_name(name: str) -> str:
    n = _norm(name)
    if not n or n in {"unknown", "unk", "n/a"}:
        return "unknown"
    for canonical, variants in KNOWN_SYSTEM_VARIANTS:
        for v in variants:
            vv = _norm(v)
            if vv and vv in n:
                return canonical
    # Keep original if it doesn't map to our known list (supports novel systems)
    return (name or "").strip() or "unknown"


def detect_known_system_from_calls(calls: List[Dict[str, Any]]) -> Tuple[str, str]:
    # Try to detect known system mentions even if the LLM misses / typos exist.
    joined = "\n".join(str(c.get("transcript_text") or "") for c in calls)
    lower = joined.lower()
    for canonical, variants in KNOWN_SYSTEM_VARIANTS:
        for v in variants:
            vv = (v or "").strip().lower()
            if not vv:
                continue
            idx = lower.find(vv)
            if idx >= 0:
                # Grab a short snippet around the hit as evidence.
                start = max(0, idx - 40)
                end = min(len(joined), idx + len(vv) + 40)
                snippet = joined[start:end].replace("\n", " ").strip()
                return canonical, snippet
    return "unknown", ""


def _quote_score(context_norm: str, quote: str) -> float:
    q = _norm(quote)
    if not q:
        return 0.0
    # simple word coverage score
    words = [w for w in re.findall(r"\w+", q, flags=re.UNICODE) if len(w) >= 3]
    if not words:
        return 0.0
    hit = sum(1 for w in words if w in context_norm)
    return hit / max(1, len(words))


def heuristic_classify(
    *,
    calls: List[Dict[str, Any]],
    context: str,
    gk_items: List[Dict[str, Any]],
    dm_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    context_norm = _norm(context)

    def best(items: List[Dict[str, Any]]) -> Tuple[str, float, str]:
        best_label = "Other/Unclear"
        best_score = 0.0
        best_quote = ""
        for it in items:
            label = str(it.get("label") or "").strip()
            quotes = it.get("quotes") or []
            for q in quotes:
                sc = _quote_score(context_norm, str(q))
                if sc > best_score:
                    best_score = sc
                    best_label = label or best_label
                    best_quote = str(q).strip()
        return best_label, best_score, best_quote

    gk_label, gk_sc, gk_q = best(gk_items)
    dm_label, dm_sc, dm_q = best(dm_items)

    if max(gk_sc, dm_sc) < 0.30:
        role = "UNKNOWN"
        label = "Other/Unclear"
        ev = ""
        conf = max(gk_sc, dm_sc)
    else:
        if gk_sc >= dm_sc:
            role = "GK"
            label = gk_label
            ev = gk_q
            conf = gk_sc
        else:
            role = "DM"
            label = dm_label
            ev = dm_q
            conf = dm_sc

    # crude system detection
    joined = _norm("\n".join(str(c.get("transcript_text") or "") for c in calls))
    systems = [
        "medifox",
        "vivendi",
        "sinfonie",
        "snap",
        "mikos",
        "dokumentation",
        "tourenplanung",
    ]
    sys_found = "unknown"
    for s in systems:
        if s in joined:
            sys_found = s
            break

    return {
        "role": role,
        "category_label": label,
        "category_confidence": round(float(conf), 4),
        "evidence_quote": ev,
        "system_in_use": sys_found,
        "system_evidence_quote": "",
        "notes": "heuristic_mode",
    }


def _usage_to_dict(usage: Any) -> Dict[str, Any]:
    if usage is None:
        return {}
    # openai-python returns pydantic models in many cases
    try:
        d = usage.model_dump()  # type: ignore[attr-defined]
        return d if isinstance(d, dict) else {}
    except Exception:
        pass
    # fallback: common attributes
    out: Dict[str, Any] = {}
    for k in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_tokens_details", "completion_tokens_details"):
        if hasattr(usage, k):
            v = getattr(usage, k)
            try:
                out[k] = v.model_dump()  # type: ignore[attr-defined]
            except Exception:
                out[k] = v
    return out


def _usage_get(usage: Dict[str, Any], path: str, default: int = 0) -> int:
    cur: Any = usage
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur.get(part)
    try:
        return int(cur or 0)
    except Exception:
        return default


def call_openai_json(model: str, system_prompt: str, user_prompt: str, temperature: float) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    from openai import OpenAI  # lazy import

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY not set")

    client = OpenAI()
    # basic backoff for transient errors
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
            )
            content = resp.choices[0].message.content or "{}"
            return json.loads(content), _usage_to_dict(getattr(resp, "usage", None))
        except Exception as e:
            s = str(e).lower()
            transient = ("429" in s) or ("rate" in s) or ("timeout" in s) or ("server" in s) or ("unavailable" in s)
            if attempt >= 2 or not transient:
                raise
            time.sleep(0.5 * (2**attempt) + 0.05)
    return {}, {}


SYSTEM_PROMPT = (
    "You are classifying a cold-call journey (multiple calls) into a FIXED taxonomy.\n"
    "Return valid JSON only.\n"
)


def build_user_prompt(context: str, gk_labels: List[str], dm_labels: List[str]) -> str:
    gk_list = "\n".join([f"- {x}" for x in gk_labels])
    dm_list = "\n".join([f"- {x}" for x in dm_labels])

    return f"""
You will read German call transcripts (a journey = multiple calls to the same contact).
The journey context below contains MULTIPLE calls, stitched together in CHRONOLOGICAL order.
We prioritized the MOST RECENT calls first, and included as many calls as possible up to a word cap.

Task:
1) Decide who we reached overall: "GK" (gatekeeper) or "DM" (decision maker) or "UNKNOWN".
2) Choose ONE category_label from the correct fixed list:
   - If role = GK, choose from GK list
   - If role = DM, choose from DM list
   - If role = UNKNOWN, set category_label = "Other/Unclear"
3) Extract the current system/vendor they use if mentioned (e.g., Medifox, Vivendi, etc.) else "unknown".
4) Provide an evidence quote (verbatim substring) from the transcript for category + for system if possible.

Hard rules:
- category_label MUST be exactly one of the provided labels, or "Other/Unclear".
- Keep temperature low and be consistent. Do not invent new labels.
- evidence_quote must be a short German substring from the transcript.
- evidence_quote and system_evidence_quote MUST be exact substrings that appear in the provided context.

GK labels:
{gk_list}

DM labels:
{dm_list}

Return JSON with EXACT keys:
role, category_label, category_confidence, evidence_quote, system_in_use, system_evidence_quote, notes

Context:
{context}
""".strip()


def main() -> None:
    args = parse_args()
    in_path = Path(args.inp)
    tax_path = Path(args.taxonomy)
    out_jsonl = Path(args.out_jsonl)
    out_csv = Path(args.out_csv)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    if not in_path.exists():
        raise SystemExit(f"Input not found: {in_path}")
    if not tax_path.exists():
        raise SystemExit(f"Taxonomy not found: {tax_path}")

    journeys = load_jsonl(in_path)
    if args.max_journeys is not None and args.max_journeys > 0:
        journeys = journeys[: int(args.max_journeys)]
    taxonomy = json.loads(tax_path.read_text(encoding="utf-8"))
    gk_labels, dm_labels = parse_taxonomy_labels(taxonomy)
    gk_items, dm_items = parse_taxonomy_items(taxonomy)
    gk_label_to_id = build_label_to_id(gk_items, "GK")
    dm_label_to_id = build_label_to_id(dm_items, "DM")

    # Add explicit fallback
    if "Other/Unclear" not in gk_labels:
        gk_labels = gk_labels + ["Other/Unclear"]
    if "Other/Unclear" not in dm_labels:
        dm_labels = dm_labels + ["Other/Unclear"]

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def process_one(idx: int, j: Dict[str, Any]) -> Dict[str, Any]:
        phone = str(j.get("phone") or "")
        campaign = str(j.get("campaign_name") or "")
        calls = j.get("calls") or []
        context, selected_calls, selected_words = build_context(calls, max_words=int(args.max_context_words or 0), max_calls=int(args.max_calls or 1))

        # Shortcut: if empty/unreachable-ish, mark Other/Unclear deterministically (unless disabled)
        joined_text = "\n".join(str(c.get("transcript_text") or "") for c in calls)
        if (not args.disable_shortcuts) and (not context.strip() or is_unreachable(joined_text)):
            return {
                "input_index": idx,
                "phone": phone,
                "campaign_name": campaign,
                "num_calls": int(j.get("num_calls") or len(calls)),
                "role": "UNKNOWN",
                "category_id": "UNK00",
                "category_label": "Other/Unclear",
                "category_confidence": 0.2,
                "evidence_quote": "",
                "system_in_use": "unknown",
                "system_evidence_quote": "",
                "notes": "empty_or_unreachable",
                "_evidence_mismatch": 0,
                "_system_evidence_mismatch": 0,
                "model": args.model,
                "run_ts": datetime.now(timezone.utc).isoformat(),
            }

        if (not args.disable_shortcuts) and int(args.min_journey_words or 0) > 0 and selected_words < int(args.min_journey_words):
            return {
                "input_index": idx,
                "phone": phone,
                "campaign_name": campaign,
                "num_calls": int(j.get("num_calls") or len(calls)),
                "role": "UNKNOWN",
                "category_id": "UNK00",
                "category_label": "Other/Unclear",
                "category_confidence": 0.2,
                "evidence_quote": "",
                "system_in_use": "unknown",
                "system_evidence_quote": "",
                "notes": f"too_short<{int(args.min_journey_words)}w",
                "_evidence_mismatch": 0,
                "_system_evidence_mismatch": 0,
                "model": args.model,
                "run_ts": datetime.now(timezone.utc).isoformat(),
            }

        usage: Dict[str, Any] = {}
        if args.heuristic:
            data = heuristic_classify(calls=calls, context=context, gk_items=gk_items, dm_items=dm_items)
        else:
            user_prompt = build_user_prompt(context, gk_labels, dm_labels)
            data, usage = call_openai_json(args.model, SYSTEM_PROMPT, user_prompt, args.temperature)

        role = str(data.get("role") or "").strip().upper()
        if role not in {"GK", "DM", "UNKNOWN"}:
            role = "UNKNOWN"

        label = str(data.get("category_label") or "").strip()
        allowed = gk_labels if role == "GK" else (dm_labels if role == "DM" else ["Other/Unclear"])
        label = strict_choice(label, allowed)
        if role == "GK":
            category_id = gk_label_to_id.get(label, "GK00")
        elif role == "DM":
            category_id = dm_label_to_id.get(label, "DM00")
        else:
            category_id = "UNK00"

        try:
            conf = float(data.get("category_confidence", 0.0) or 0.0)
        except Exception:
            conf = 0.0
        conf = max(0.0, min(1.0, conf))

        ev = str(data.get("evidence_quote") or "").strip()
        sysname = canonicalize_system_name(str(data.get("system_in_use") or "unknown").strip() or "unknown")
        sysev = str(data.get("system_evidence_quote") or "").strip()

        # If system is unknown (or missing evidence), try local detection from the transcript text.
        if sysname in {"unknown", "", "unk", "n/a"} or (sysname != "unknown" and (not sysev or not _evidence_in_context(sysev, calls))):
            det_sys, det_ev = detect_known_system_from_calls(calls)
            if det_sys != "unknown":
                sysname = det_sys
                if det_ev:
                    sysev = det_ev

        ev_mis = 0 if _evidence_in_context(ev, calls) else 1
        sys_mis = 0 if _evidence_in_context(sysev, calls) else 1

        notes = str(data.get("notes") or "").strip()

        usage_prompt = int(usage.get("prompt_tokens") or 0) if usage else 0
        usage_completion = int(usage.get("completion_tokens") or 0) if usage else 0
        usage_total = int(usage.get("total_tokens") or 0) if usage else 0
        usage_cached = _usage_get(usage, "prompt_tokens_details.cached_tokens", 0) if usage else 0
        usage_reasoning = _usage_get(usage, "completion_tokens_details.reasoning_tokens", 0) if usage else 0

        return {
            "input_index": idx,
            "phone": phone,
            "campaign_name": campaign,
            "num_calls": int(j.get("num_calls") or len(calls)),
            "context_selected_calls": int(selected_calls),
            "context_selected_words": int(selected_words),
            "role": role,
            "category_id": category_id,
            "category_label": label,
            "category_confidence": conf,
            "evidence_quote": ev,
            "system_in_use": sysname,
            "system_evidence_quote": sysev,
            "notes": notes,
            "_evidence_mismatch": ev_mis,
            "_system_evidence_mismatch": sys_mis,
            "usage_prompt_tokens": usage_prompt,
            "usage_completion_tokens": usage_completion,
            "usage_total_tokens": usage_total,
            "usage_cached_tokens": usage_cached,
            "usage_reasoning_tokens": usage_reasoning,
            "model": args.model,
            "run_ts": datetime.now(timezone.utc).isoformat(),
        }

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as ex:
        futs = {ex.submit(process_one, i, j): i for i, j in enumerate(journeys)}
        for fut in as_completed(futs):
            results.append(fut.result())

    results.sort(key=lambda r: int(r.get("input_index", 0)))

    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    fieldnames = [
        "input_index",
        "phone",
        "campaign_name",
        "num_calls",
        "context_selected_calls",
        "context_selected_words",
        "role",
        "category_id",
        "category_label",
        "category_confidence",
        "evidence_quote",
        "system_in_use",
        "system_evidence_quote",
        "notes",
        "_evidence_mismatch",
        "_system_evidence_mismatch",
        "usage_prompt_tokens",
        "usage_completion_tokens",
        "usage_total_tokens",
        "usage_cached_tokens",
        "usage_reasoning_tokens",
        "model",
        "run_ts",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as g:
        w = csv.DictWriter(g, fieldnames=fieldnames)
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in fieldnames} for r in results])

    print("Wrote:", out_jsonl)
    print("Wrote:", out_csv)
    mism = sum(int(r.get("_evidence_mismatch") or 0) for r in results)
    print(f"Evidence mismatches: {mism}/{len(results)}")
    tok_prompt = sum(int(r.get("usage_prompt_tokens") or 0) for r in results)
    tok_comp = sum(int(r.get("usage_completion_tokens") or 0) for r in results)
    tok_total = sum(int(r.get("usage_total_tokens") or 0) for r in results)
    tok_cached = sum(int(r.get("usage_cached_tokens") or 0) for r in results)
    tok_reason = sum(int(r.get("usage_reasoning_tokens") or 0) for r in results)
    if tok_total:
        avg = round(tok_total / max(1, len(results)), 2)
        print(
            "Token usage: "
            f"prompt={tok_prompt} completion={tok_comp} total={tok_total} "
            f"cached={tok_cached} reasoning={tok_reason} avg_total_per_journey={avg}"
        )


if __name__ == "__main__":
    main()

