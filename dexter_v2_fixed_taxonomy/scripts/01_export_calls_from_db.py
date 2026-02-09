import argparse
import csv
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
    load_dotenv(find_dotenv(usecwd=True))
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export Dexter calls from Postgres into flat CSV + grouped JSONL.")
    p.add_argument("--db-url", default=os.environ.get("DATABASE_URL", ""), help="Postgres URL (defaults to env DATABASE_URL)")
    p.add_argument(
        "--dialfire-db-url",
        default=os.environ.get("DIALFIRE_DATABASE_URL", ""),
        help="Optional Dialfire reporting DB URL (defaults to env DIALFIRE_DATABASE_URL). Used to filter out successes.",
    )
    p.add_argument(
        "--dialfire-view",
        default=os.environ.get("DIALFIRE_AGENT_DATA_VIEW", "public.agent_data_v3"),
        help="Dialfire reporting view to read (default: public.agent_data_v3).",
    )
    p.add_argument(
        "--outcome-filter",
        default="none",
        choices=["none", "not_success", "open", "declined", "open_declined"],
        help="If Dialfire DB is configured, filter journeys by latest contact status from Dialfire.",
    )
    p.add_argument(
        "--include-unknown-outcome",
        action="store_true",
        help="When filtering by outcome, keep journeys where Dialfire status couldn't be determined (default: drop them).",
    )
    p.add_argument(
        "--scope",
        default="a.b2_object_key like 'dexter/audio/%'",
        help="SQL WHERE predicate to scope Dexter audio_files rows (default: dexter/audio/ prefix)",
    )
    p.add_argument(
        "--campaign",
        default=None,
        help="Optional exact campaign_name filter (e.g. 'DEXTER  Messe').",
    )
    p.add_argument(
        "--latest-campaign",
        action="store_true",
        help="If set, auto-select the most recent non-empty campaign_name within scope (and within --only-completed if set).",
    )
    p.add_argument(
        "--group-by",
        default="phone_campaign",
        choices=["phone", "phone_campaign"],
        help="How to group calls into journeys",
    )
    p.add_argument(
        "--order",
        default="phone_campaign_started_asc",
        choices=["phone_campaign_started_asc", "started_desc"],
        help="Ordering before applying --limit (affects what rows you sample).",
    )
    p.add_argument(
        "--only-completed",
        action="store_true",
        help="Only export rows where transcriptions.status='completed' (recommended for classification).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for quick test exports (applied after ordering).",
    )
    p.add_argument("--out-flat", required=True, help="Output flat CSV path")
    p.add_argument("--out-grouped", required=True, help="Output grouped JSONL path")
    return p.parse_args()


def _iso(x: Any) -> str:
    return x.isoformat() if hasattr(x, "isoformat") else (str(x) if x is not None else "")


def _extract_dexter_b2_key(location: str) -> str:
    from urllib.parse import unquote

    s_raw = str(location or "")
    # Dialfire can store URL-encoded locations; decode first (e.g. dexter%2Faudio%2F...).
    s = unquote(s_raw)
    idx = s.find("dexter/audio/")
    if idx < 0:
        return ""
    key = s[idx:]
    for sep in ["?", " ", "\n", "\r", "\t", '"', "'"]:
        if sep in key:
            key = key.split(sep, 1)[0]
    return key.strip()


def _dialfire_engine(dialfire_db_url: str):
    raw = str(dialfire_db_url).strip().strip('"').strip("'")
    url = raw.replace("postgresql+asyncpg", "postgresql+psycopg2")
    from sqlalchemy import create_engine  # lazy import

    return create_engine(url, pool_pre_ping=True, pool_recycle=1800, connect_args={"connect_timeout": 5})


def _norm_phone(x: str) -> str:
    # Dialfire connections_phone is digits-only (no +, spaces). Normalize to digits.
    s = str(x or "")
    return "".join(ch for ch in s if ch.isdigit())


def _parse_dialfire_dt(rec_started: str, fired_date: str) -> Optional[datetime]:
    # Prefer recordings_started (usually ISO with Z). Fallback to transactions_fired_date (YYYY-MM-DD).
    s = (rec_started or "").strip()
    if s:
        try:
            # e.g. 2026-02-02T13:05:04.923Z
            s2 = s.replace("Z", "+00:00")
            return datetime.fromisoformat(s2)
        except Exception:
            pass
    d = (fired_date or "").strip()
    if len(d) >= 10:
        d10 = d[:10]
        try:
            # Treat date-only as UTC midnight
            return datetime.fromisoformat(d10 + "T00:00:00+00:00")
        except Exception:
            return None
    return None


def main() -> None:
    args = parse_args()
    if not args.db_url:
        raise SystemExit("DATABASE_URL is not set. Provide --db-url or set $env:DATABASE_URL.")

    # Force sync driver for SQLAlchemy
    raw = str(args.db_url).strip().strip('"').strip("'")
    db_url = raw.replace("postgresql+asyncpg", "postgresql+psycopg2")

    from sqlalchemy import bindparam, create_engine, text  # lazy import
    from sqlalchemy.engine.url import make_url

    try:
        u = make_url(db_url)
        print(f"Connecting to host={u.host} port={u.port} db={u.database} user={u.username}")
    except Exception as ex:
        print(f"Connecting to (could not parse DATABASE_URL) {type(ex).__name__}: {ex}")

    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"connect_timeout": 5},
    )

    status_pred = "and t.status = 'completed'" if args.only_completed else ""
    limit_sql = f"limit {int(args.limit)}" if (args.limit and args.limit > 0) else ""
    params: Dict[str, Any] = {}
    campaign_pred = ""

    if args.latest_campaign:
        # Pick the most recent non-empty campaign_name in scope (and in completed subset if requested).
        latest_sql = text(
            f"""
select a.campaign_name
from media_pipeline.audio_files a
join media_pipeline.transcriptions t on t.audio_file_id = a.id
where {args.scope}
  {status_pred}
  and a.campaign_name is not null
  and length(trim(a.campaign_name)) > 0
order by a.started desc nulls last, a.id desc
limit 1
"""
        )
        with engine.connect() as c:
            latest = c.execute(latest_sql).scalar()
        if latest:
            args.campaign = str(latest)
            print(f"Auto-selected latest campaign_name: {args.campaign}")

    if args.campaign:
        campaign_pred = "and a.campaign_name = :campaign_name"
        params["campaign_name"] = str(args.campaign)

    if args.order == "started_desc":
        order_by = "a.started desc nulls last, a.id desc"
    else:
        order_by = "a.phone, campaign_name, a.started nulls last, a.id"

    sql = text(
        f"""
select
  a.phone,
  coalesce(a.campaign_name,'') as campaign_name,
  a.id as audio_id,
  a.b2_object_key,
  a.started,
  a.stopped,
  t.status,
  t.completed_at,
  t.transcript_text,
  cast(t.segments as text) as segments_json
from media_pipeline.audio_files a
join media_pipeline.transcriptions t on t.audio_file_id = a.id
where {args.scope}
  {status_pred}
  {campaign_pred}
order by {order_by}
{limit_sql}
"""
    )

    rows: List[Dict[str, Any]] = []
    with engine.connect() as c:
        for r in c.execute(sql, params):
            rows.append(dict(r._mapping))

    # Optional: Dialfire outcome filtering (skip successes / keep open/declined)
    if args.outcome_filter != "none":
        if not args.dialfire_db_url:
            raise SystemExit("outcome-filter requires Dialfire DB. Set DIALFIRE_DATABASE_URL or pass --dialfire-db-url.")

        from sqlalchemy import text  # lazy import

        dengine = _dialfire_engine(args.dialfire_db_url)

        starts: List[datetime] = [r.get("started") for r in rows if isinstance(r.get("started"), datetime)]
        t0: Optional[datetime] = min(starts) - timedelta(days=7) if starts else None
        t1: Optional[datetime] = max(starts) + timedelta(days=7) if starts else None
        d0 = t0.date().isoformat() if t0 else None
        d1 = t1.date().isoformat() if t1 else None

        phones = sorted({p for p in (_norm_phone(r.get("phone") or "") for r in rows) if p})
        if not phones:
            raise SystemExit("No phones found in export to join with Dialfire.")

        df_sql = text(
            f"""
select
  recordings_location,
  recordings_started,
  transactions_fired_date,
  connections_phone,
  contacts_id,
  contacts_campaign_id,
  transactions_status,
  transactions_status_detail,
  transaction_id
from {args.dialfire_view}
where connections_phone in :phones
  and (transactions_fired_date is null or transactions_fired_date::text ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}')
  {'' if (d0 is None or d1 is None) else 'and transactions_fired_date >= :d0 and transactions_fired_date <= :d1'}
"""
        ).bindparams(bindparam("phones", expanding=True))

        params_df: Dict[str, Any] = {"phones": phones}
        if d0 is not None and d1 is not None:
            params_df["d0"] = d0
            params_df["d1"] = d1

        with dengine.connect() as c:
            df_rows = [dict(r._mapping) for r in c.execute(df_sql, params_df)]

        # Choose representative Dialfire (campaign_id, contact_id) per phone within the window.
        # We pick the most frequent pair per phone (ties broken by latest timestamp).
        dialfire_pair_counts: Dict[str, Dict[Tuple[str, str], int]] = defaultdict(dict)
        dialfire_pair_latest_dt: Dict[str, Dict[Tuple[str, str], datetime]] = defaultdict(dict)
        contact_latest: Dict[str, Dict[str, Any]] = {}

        for dr in df_rows:
            phone = _norm_phone(str(dr.get("connections_phone") or ""))
            if not phone:
                continue

            cid = str(dr.get("contacts_id") or "").strip()
            camp_id = str(dr.get("contacts_campaign_id") or "").strip()
            if cid and camp_id:
                ck = f"{camp_id}|{cid}"
                prev2 = contact_latest.get(ck)
                if prev2 is None:
                    contact_latest[ck] = dr
                else:
                    dt_new = _parse_dialfire_dt(str(dr.get("recordings_started") or ""), str(dr.get("transactions_fired_date") or ""))
                    dt_prev = _parse_dialfire_dt(str(prev2.get("recordings_started") or ""), str(prev2.get("transactions_fired_date") or ""))
                    if dt_new and (not dt_prev or dt_new > dt_prev):
                        contact_latest[ck] = dr

                pair = (camp_id, cid)
                dialfire_pair_counts[phone][pair] = int(dialfire_pair_counts[phone].get(pair, 0)) + 1
                dt = _parse_dialfire_dt(str(dr.get("recordings_started") or ""), str(dr.get("transactions_fired_date") or ""))
                if dt:
                    prev_dt = dialfire_pair_latest_dt[phone].get(pair)
                    if not prev_dt or dt > prev_dt:
                        dialfire_pair_latest_dt[phone][pair] = dt

        dialfire_by_phone_pair: Dict[str, Tuple[str, str]] = {}
        for phone, counts in dialfire_pair_counts.items():
            # pick highest count, then latest dt
            best_pair: Optional[Tuple[str, str]] = None
            best_count = -1
            best_dt: Optional[datetime] = None
            for pair, cnt in counts.items():
                dt = dialfire_pair_latest_dt.get(phone, {}).get(pair)
                if cnt > best_count:
                    best_pair, best_count, best_dt = pair, cnt, dt
                elif cnt == best_count:
                    if dt and (not best_dt or dt > best_dt):
                        best_pair, best_dt = pair, dt
            if best_pair:
                dialfire_by_phone_pair[phone] = best_pair

        matched = 0
        for r in rows:
            phone = _norm_phone(str(r.get("phone") or ""))
            pair = dialfire_by_phone_pair.get(phone)
            if pair:
                matched += 1
                camp_id, cid = pair
                r["dialfire_contacts_id"] = cid
                r["dialfire_contacts_campaign_id"] = camp_id
                ck = f"{camp_id}|{cid}"
                lr = contact_latest.get(ck)
                r["dialfire_transactions_status"] = (lr.get("transactions_status") if lr else "") or ""
                r["dialfire_transactions_status_detail"] = (lr.get("transactions_status_detail") if lr else "") or ""
                r["dialfire_contact_latest_status"] = r["dialfire_transactions_status"]
                r["dialfire_contact_latest_status_detail"] = r["dialfire_transactions_status_detail"]
            else:
                r["dialfire_contacts_id"] = ""
                r["dialfire_contacts_campaign_id"] = ""
                r["dialfire_transactions_status"] = ""
                r["dialfire_transactions_status_detail"] = ""
                r["dialfire_contact_latest_status"] = ""
                r["dialfire_contact_latest_status_detail"] = ""

        print(f"Dialfire match rate (by phone): {matched}/{len(rows)} (unique phones {len(phones)})")

        if args.outcome_filter == "not_success":
            allowed = {"open", "declined"}
        elif args.outcome_filter == "open":
            allowed = {"open"}
        elif args.outcome_filter == "declined":
            allowed = {"declined"}
        else:
            allowed = {"open", "declined"}

        # Group rows and decide which journeys to keep based on contact_latest_status
        tmp_groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for r in rows:
            phone = str(r.get("phone") or "")
            campaign = str(r.get("campaign_name") or "")
            key = (phone, campaign) if args.group_by == "phone_campaign" else (phone, "")
            tmp_groups[key].append(r)

        keep_keys: set[Tuple[str, str]] = set()
        drop_keys: set[Tuple[str, str]] = set()
        for key, rs in tmp_groups.items():
            st = ""
            for r in rs:
                st = str(r.get("dialfire_contact_latest_status") or "").strip().lower()
                if st:
                    break
            if st in allowed:
                keep_keys.add(key)
            elif (not st) and args.include_unknown_outcome:
                keep_keys.add(key)
            else:
                drop_keys.add(key)

        before = len(rows)
        rows = [r for r in rows if ((str(r.get("phone") or ""), str(r.get("campaign_name") or "")) if args.group_by == "phone_campaign" else (str(r.get("phone") or ""), "")) in keep_keys]
        print(f"Outcome filter='{args.outcome_filter}': kept {len(keep_keys)} journeys, dropped {len(drop_keys)}; rows {before} -> {len(rows)}")

    else:
        # Ensure fields exist for downstream CSV schema
        for r in rows:
            r.setdefault("dialfire_contacts_id", "")
            r.setdefault("dialfire_contacts_campaign_id", "")
            r.setdefault("dialfire_transactions_status", "")
            r.setdefault("dialfire_transactions_status_detail", "")
            r.setdefault("dialfire_contact_latest_status", "")
            r.setdefault("dialfire_contact_latest_status_detail", "")

    out_flat = Path(args.out_flat)
    out_grouped = Path(args.out_grouped)
    out_flat.parent.mkdir(parents=True, exist_ok=True)
    out_grouped.parent.mkdir(parents=True, exist_ok=True)

    cols = [
        "phone",
        "campaign_name",
        "audio_id",
        "b2_object_key",
        "started",
        "stopped",
        "status",
        "completed_at",
        "transcript_text",
        "segments_json",
        "dialfire_contacts_id",
        "dialfire_contacts_campaign_id",
        "dialfire_transactions_status",
        "dialfire_transactions_status_detail",
        "dialfire_contact_latest_status",
        "dialfire_contact_latest_status_detail",
    ]

    with out_flat.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            r2 = dict(r)
            r2["started"] = _iso(r2.get("started"))
            r2["stopped"] = _iso(r2.get("stopped"))
            r2["completed_at"] = _iso(r2.get("completed_at"))
            w.writerow({k: r2.get(k, "") for k in cols})

    # Group into journeys
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        phone = str(r.get("phone") or "")
        campaign = str(r.get("campaign_name") or "")
        key = (phone, campaign) if args.group_by == "phone_campaign" else (phone, "")
        groups[key].append(
            {
                "audio_id": r.get("audio_id"),
                "b2_object_key": r.get("b2_object_key"),
                "started": _iso(r.get("started")),
                "stopped": _iso(r.get("stopped")),
                "status": r.get("status") or "",
                "completed_at": _iso(r.get("completed_at")),
                "transcript_text": r.get("transcript_text") or "",
                "segments_json": r.get("segments_json") or "",
                "dialfire_contacts_id": r.get("dialfire_contacts_id") or "",
                "dialfire_contacts_campaign_id": r.get("dialfire_contacts_campaign_id") or "",
                "dialfire_transactions_status": r.get("dialfire_transactions_status") or "",
                "dialfire_transactions_status_detail": r.get("dialfire_transactions_status_detail") or "",
                "dialfire_contact_latest_status": r.get("dialfire_contact_latest_status") or "",
                "dialfire_contact_latest_status_detail": r.get("dialfire_contact_latest_status_detail") or "",
            }
        )

    with out_grouped.open("w", encoding="utf-8") as f:
        for (phone, campaign), calls in groups.items():
            # Sort calls by started (string ISO sorts OK if consistently formatted; we still keep order stable)
            calls_sorted = sorted(calls, key=lambda c: (str(c.get("started") or ""), str(c.get("audio_id") or "")))
            f.write(
                json.dumps(
                    {
                        "group_by": args.group_by,
                        "phone": phone,
                        "campaign_name": campaign,
                        "num_calls": len(calls_sorted),
                        "calls": calls_sorted,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(f"Wrote flat: {out_flat} ({len(rows)} rows)")
    print(f"Wrote grouped: {out_grouped} ({len(groups)} groups)")


if __name__ == "__main__":
    main()

