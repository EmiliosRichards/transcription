import argparse
import os
from typing import List

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore

    load_dotenv(find_dotenv(usecwd=True))
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Debug: sample a few rows from Dialfire agent_data_v3 for given phone(s).")
    p.add_argument("--db-url", default=os.environ.get("DIALFIRE_DATABASE_URL", ""), help="Dialfire DB URL (env DIALFIRE_DATABASE_URL)")
    p.add_argument("--view", default="public.agent_data_v3", help="View name (default public.agent_data_v3)")
    p.add_argument("--phone", action="append", default=[], help="Phone to sample (can be repeated)")
    p.add_argument("--any", action="store_true", help="Sample arbitrary rows (ignores --phone).")
    p.add_argument("--limit", type=int, default=5, help="Rows per phone")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not args.db_url:
        raise SystemExit("Set DIALFIRE_DATABASE_URL or pass --db-url")

    raw = str(args.db_url).strip().strip('"').strip("'")
    url = raw.replace("postgresql+asyncpg", "postgresql+psycopg2")

    from sqlalchemy import create_engine, text  # lazy import

    e = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})

    phones: List[str] = list(args.phone or [])
    if args.any:
        phones = ["(any)"]
    elif not phones:
        raise SystemExit("Provide at least one --phone '+49...' or pass --any")

    for p in phones:
        print("=" * 80)
        print("phone:", p)
        if args.any:
            q = text(
                f"""
select
  connections_phone,
  transactions_fired_date,
  recordings_started,
  recordings_start_time,
  contacts_campaign_id,
  contacts_id,
  transactions_status,
  transactions_status_detail,
  transaction_id,
  recordings_location
from {args.view}
limit {int(args.limit)}
"""
            )
            params = {}
        else:
            q = text(
                f"""
select
  connections_phone,
  transactions_fired_date,
  recordings_started,
  recordings_start_time,
  contacts_campaign_id,
  contacts_id,
  transactions_status,
  transactions_status_detail,
  transaction_id,
  recordings_location
from {args.view}
where connections_phone = :p
limit {int(args.limit)}
"""
            )
            params = {"p": p}

        with e.connect() as c:
            rows = c.execute(q, params).fetchall()
        print("rows:", len(rows))
        for r in rows:
            (cp, fired, rec_started, rec_start_time, camp_id, cid, st, detail, txid, loc) = r
            print("---")
            print("connections_phone:", cp)
            print("transactions_fired_date:", fired)
            print("recordings_started:", rec_started)
            print("recordings_start_time:", rec_start_time)
            print("contacts_campaign_id:", camp_id, "contacts_id:", cid)
            print("transactions_status:", st, "detail:", detail)
            print("transaction_id:", txid)
            s = str(loc or "")
            print("recordings_location:", (s[:200] + ("..." if len(s) > 200 else "")))


if __name__ == "__main__":
    main()

