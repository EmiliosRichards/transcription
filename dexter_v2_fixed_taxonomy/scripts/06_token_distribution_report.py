import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Report token usage distribution and prompt-size estimates.")
    p.add_argument("--grouped", required=True, help="calls_grouped.jsonl (export input)")
    p.add_argument("--csv", required=False, default=None, help="journey_classifications*.csv with usage_* columns (optional)")
    p.add_argument("--head-chars", type=int, default=800)
    p.add_argument("--tail-chars", type=int, default=800)
    p.add_argument("--max-calls", type=int, default=4)
    p.add_argument("--out", default=None, help="Optional JSON output path")
    return p.parse_args()


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(json.loads(line))
    return items


def truncate_text(text: str, head: int, tail: int) -> str:
    t = text or ""
    if len(t) <= head + tail + 20:
        return t
    return t[:head] + "\n...\n" + t[-tail:]


def build_context(calls: List[Dict[str, Any]], head: int, tail: int, max_calls: int) -> str:
    calls_sorted = sorted(calls, key=lambda c: str(c.get("started") or ""))
    recent = calls_sorted[-max(1, max_calls) :]
    parts: List[str] = []
    for c in recent:
        started = str(c.get("started") or "")
        txt = str(c.get("transcript_text") or "")
        parts.append(f"[Call started={started}]\n{truncate_text(txt, head, tail)}\n")
    return "\n".join(parts).strip()


def pct(values: List[int], p: float) -> int:
    if not values:
        return 0
    xs = sorted(values)
    k = int(round((len(xs) - 1) * p))
    return int(xs[max(0, min(len(xs) - 1, k))])


def summarize(values: List[int]) -> Dict[str, Any]:
    if not values:
        return {}
    xs = sorted(values)
    return {
        "n": len(xs),
        "min": xs[0],
        "p25": pct(xs, 0.25),
        "median": pct(xs, 0.50),
        "p75": pct(xs, 0.75),
        "p90": pct(xs, 0.90),
        "p95": pct(xs, 0.95),
        "max": xs[-1],
        "mean": round(sum(xs) / max(1, len(xs)), 2),
    }


def read_usage_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_int(x: Any) -> int:
    try:
        return int(float(str(x or "").strip() or 0))
    except Exception:
        return 0


def main() -> None:
    args = parse_args()
    grouped = load_jsonl(Path(args.grouped))

    # Estimate prompt size from context only (rough proxy). Rule of thumb: ~4 chars/token for English;
    # German can be slightly different, so treat as a coarse estimate only.
    context_chars: List[int] = []
    est_tokens: List[int] = []
    calls_per: List[int] = []
    for j in grouped:
        calls = list(j.get("calls") or [])
        ctx = build_context(calls, args.head_chars, args.tail_chars, args.max_calls)
        n_chars = len(ctx)
        context_chars.append(n_chars)
        est_tokens.append(int(round(n_chars / 4.0)))
        calls_per.append(len(calls))

    report: Dict[str, Any] = {
        "journeys": len(grouped),
        "calls_per_journey": summarize(calls_per),
        "context_chars": summarize(context_chars),
        "estimated_context_tokens_chars_div4": summarize(est_tokens),
    }

    if args.csv:
        rows = read_usage_csv(Path(args.csv))
        prompt = [to_int(r.get("usage_prompt_tokens")) for r in rows if r.get("usage_total_tokens")]
        comp = [to_int(r.get("usage_completion_tokens")) for r in rows if r.get("usage_total_tokens")]
        total = [to_int(r.get("usage_total_tokens")) for r in rows if r.get("usage_total_tokens")]
        cached = [to_int(r.get("usage_cached_tokens")) for r in rows if r.get("usage_total_tokens")]
        reasoning = [to_int(r.get("usage_reasoning_tokens")) for r in rows if r.get("usage_total_tokens")]
        report["measured_usage"] = {
            "rows": len(rows),
            "prompt_tokens": summarize(prompt),
            "completion_tokens": summarize(comp),
            "total_tokens": summarize(total),
            "cached_tokens": summarize(cached),
            "reasoning_tokens": summarize(reasoning),
        }

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

