import json, os, argparse, csv
from pathlib import Path
from collections import Counter
from datetime import datetime


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize a Phase A discovery run")
    parser.add_argument("--src", required=True, help="Path to raw/dexter_free_extraction.jsonl")
    parser.add_argument("--out", required=True, help="Path to reports/run_summary.txt")
    parser.add_argument("--model", default=os.environ.get("FREE_EXTRACTION_MODEL", "gpt-5-mini-2025-08-07"))
    parser.add_argument("--prompt-ver", default=os.environ.get("FREE_PROMPT_VER", "v3"))
    parser.add_argument("--write-top", action="store_true", help="Also write top reasons CSV to reports/top_reasons.csv")
    parser.add_argument("--top-out", default=None, help="Optional explicit path for top reasons CSV")
    args = parser.parse_args()

    src_path = Path(args.src)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = 0
    unk = 0
    mis = 0
    who = Counter()
    reasons = Counter()

    with src_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            rows += 1
            reason = (o.get("reason_free_text") or "").strip().lower()
            who_val = (o.get("who_reached") or "").strip().lower() or "unknown"
            who[who_val] += 1
            if reason == "unknown" or not reason:
                unk += 1
            else:
                reasons[reason] += 1
            mis += int(o.get("_evidence_mismatch", 0) or 0)

    # Prepare one-line summary
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    src_name = src_path.name
    unk_pct = (unk / max(1, rows))
    who_str = f"who={{dm:{who.get('decision_maker',0)},gk:{who.get('gatekeeper',0)},unk:{who.get('unknown',0)}}}"
    line = (
        f"{ts} | {src_name} | model={args.model} | rows={rows} | "
        f"unknown={unk} ({unk_pct:.1%}) | evidence_mismatch={mis} | {who_str} | prompt_ver={args.prompt_ver}\n"
    )

    # Append to run_summary.txt and print to stdout
    with out_path.open("a", encoding="utf-8") as g:
        g.write(line)
    print(line.strip())

    # Optionally write top reasons CSV
    if args.write_top:
        top_path = Path(args.top_out) if args.top_out else out_path.parent / "top_reasons.csv"
        top_path.parent.mkdir(parents=True, exist_ok=True)
        with top_path.open("w", newline="", encoding="utf-8") as g:
            w = csv.writer(g)
            w.writerow(["reason", "count"])
            for reason, count in reasons.most_common(25):
                w.writerow([reason, count])


if __name__ == "__main__":
    main()
