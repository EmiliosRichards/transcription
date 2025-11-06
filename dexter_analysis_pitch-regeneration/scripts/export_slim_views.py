import csv, os, re, json, argparse, hashlib
from pathlib import Path


def sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _normalize(text: str) -> str:
    s = (text or "").lower().strip()
    # light canonicalization for recurring phrases
    s = s.replace(" künstliche intelligenz", " ki").replace("künstliche intelligenz", "ki")
    s = s.replace(" artificial intelligence", " ai")
    s = s.replace(" head office", " hq").replace(" headquarters", " hq")
    s = re.sub(r"\s+", " ", s)
    return s


def _reason_core(reason: str) -> str:
    base = _normalize(reason or "")
    if not base:
        return ""
    parts = re.split(r"[;:–—\-|]\s*", base, maxsplit=1)
    return (parts[0] or "").strip()


def _who_code(who: str) -> str:
    w = (who or "").strip().lower()
    if w == "gatekeeper":
        return "GK"
    if w == "decision_maker":
        return "DM"
    return "OTHER"


def load_yaml_markers(config_path: str):
    try:
        import yaml  # type: ignore
    except Exception:
        return set(), 0.5
    with open(config_path, "r", encoding="utf-8") as f:
        y = yaml.safe_load(f) or {}
    markers = set((y.get("unreachable_markers") or []) or [])
    conf_min = float((y.get("confidence_min_for_view") or 0.5))
    return set(m.strip().lower() for m in markers if isinstance(m, str)), conf_min


def main() -> None:
    parser = argparse.ArgumentParser(description="Export slim CSV views from raw JSONL using YAML markers")
    parser.add_argument("--src", required=True, help="Path to raw/dexter_free_extraction.jsonl")
    parser.add_argument("--outdir", required=True, help="Directory to write slim CSVs")
    parser.add_argument("--config", required=True, help="YAML config with unreachable_markers and thresholds")
    args = parser.parse_args()

    unreachable, conf_min = load_yaml_markers(args.config)

    src = Path(args.src)
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build rows from raw JSONL
    rows = []
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            phone = (o.get("phone") or "").strip()
            campaign = (o.get("campaign_name") or "").strip()
            selected_ts = (o.get("selected_call_started") or "").strip()
            reason_raw = (o.get("reason_free_text") or "").strip()
            outcome_raw = (o.get("outcome_free_text") or "").strip()
            reason = reason_raw.lower()
            outcome = outcome_raw.lower()
            who = (o.get("who_reached") or "").strip().lower()
            conf = o.get("confidence", "")
            mis = o.get("_evidence_mismatch", 0)
            evidence_quote = (o.get("evidence_quote") or "").strip()
            rid = sha1_hex(f"{phone}|{campaign}|{selected_ts}") if phone or campaign or selected_ts else ""
            rows.append({
                "row_id": rid,
                "phone": phone,
                "campaign_name": campaign,
                "reason_free_text": reason,
                "outcome_free_text": outcome,
                "confidence": conf,
                "_evidence_mismatch": mis,
                "who_reached": who,
                # derived fields
                "reason_core": _reason_core(reason_raw),
                "evidence_json": json.dumps({"quote": evidence_quote}, ensure_ascii=False),
            })

    def is_unreachable(r):
        text = (r["reason_free_text"] + " " + r["outcome_free_text"]).lower()
        return any(m in text for m in unreachable)

    fieldnames = [
        "row_id","phone","campaign_name","reason_free_text","outcome_free_text","confidence","_evidence_mismatch"
    ]

    def write_csv(name: str, filt):
        p = out_dir / name
        wrote = 0
        with p.open("w", newline="", encoding="utf-8") as g:
            w = csv.DictWriter(g, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                if filt(r):
                    w.writerow({k: r.get(k, "") for k in fieldnames})
                    wrote += 1
        print(f"{name}: {wrote} rows")

    # ALL
    write_csv("dexter_free_extraction_slim_all.csv", lambda r: r["reason_free_text"] != "unknown")
    write_csv("dexter_free_extraction_slim_all_conf05.csv", lambda r: r["reason_free_text"] != "unknown" and float(r["confidence"] or 0) >= conf_min)

    # REACHABLE (exclude unreachable markers present in reason or outcome)
    write_csv("dexter_free_extraction_slim_reachable.csv", lambda r: r["reason_free_text"] != "unknown" and not is_unreachable(r))
    write_csv("dexter_free_extraction_slim_reachable_conf05.csv", lambda r: r["reason_free_text"] != "unknown" and not is_unreachable(r) and float(r["confidence"] or 0) >= conf_min)
    write_csv("dexter_free_extraction_slim_reachable_gk.csv", lambda r: r["reason_free_text"] != "unknown" and not is_unreachable(r) and r["who_reached"] == "gatekeeper")
    write_csv("dexter_free_extraction_slim_reachable_dm.csv", lambda r: r["reason_free_text"] != "unknown" and not is_unreachable(r) and r["who_reached"] == "decision_maker")

    # New role-aware combined and splits (v2)
    rows_reachable = [r for r in rows if r["reason_free_text"] != "unknown" and not is_unreachable(r)]

    # attach role code and ensure reason_core/evidence_json exist
    for r in rows_reachable:
        r["who_reached_role"] = _who_code(r.get("who_reached", ""))
        if "reason_core" not in r:
            r["reason_core"] = _reason_core(r.get("reason_free_text", ""))
        if "evidence_json" not in r:
            r["evidence_json"] = json.dumps({"quote": ""}, ensure_ascii=False)

    v2_fields = [
        "row_id","phone","campaign_name","who_reached_role",
        "reason_core","reason_free_text","outcome_free_text",
        "confidence","_evidence_mismatch","evidence_json",
    ]

    def write_csv_v2(name: str, subset):
        p = out_dir / name
        wrote = 0
        with p.open("w", newline="", encoding="utf-8") as g:
            w = csv.DictWriter(g, fieldnames=v2_fields)
            w.writeheader()
            for r in subset:
                w.writerow({k: r.get(k, "") for k in v2_fields})
                wrote += 1
        print(f"{name}: {wrote} rows")

    write_csv_v2("reachable_with_role_v2.csv", rows_reachable)
    write_csv_v2("reachable_gk_v2.csv", [r for r in rows_reachable if r["who_reached_role"] == "GK"])
    write_csv_v2("reachable_dm_v2.csv", [r for r in rows_reachable if r["who_reached_role"] == "DM"])
    write_csv_v2("reachable_other_v2.csv", [r for r in rows_reachable if r["who_reached_role"] not in ("GK","DM")])

    print("Wrote slim views to:", out_dir)


if __name__ == "__main__":
    main()
