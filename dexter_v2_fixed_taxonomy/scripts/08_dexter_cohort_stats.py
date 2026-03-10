import argparse
import os
from typing import Any, Dict, List, Tuple

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore

    load_dotenv(find_dotenv(usecwd=True))
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Dexter cohort stats from media_pipeline DB.")
    p.add_argument("--db-url", default=os.environ.get("DATABASE_URL", ""), help="Media DB URL (env DATABASE_URL)")
    p.add_argument("--scope", default="a.b2_object_key like 'dexter/audio/%'", help="SQL WHERE predicate")
    p.add_argument("--top", type=int, default=15, help="Top-N campaigns to print")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not args.db_url:
        raise SystemExit("DATABASE_URL not set (set it in dexter_v2_fixed_taxonomy/.env)")

    raw = str(args.db_url).strip().strip('"').strip("'")
    db_url = raw.replace("postgresql+asyncpg", "postgresql+psycopg2")

    from sqlalchemy import create_engine, text  # lazy import

    e = create_engine(db_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})

    with e.connect() as c:
        audio_rows = c.execute(text(f"select count(*) from media_pipeline.audio_files a where {args.scope}")).scalar()
        uniq_phone = c.execute(text(f"select count(distinct a.phone) from media_pipeline.audio_files a where {args.scope}")).scalar()
        uniq_phone_campaign = c.execute(
            text(f"select count(distinct (a.phone || '|' || coalesce(a.campaign_name,''))) from media_pipeline.audio_files a where {args.scope}")
        ).scalar()
        min_started = c.execute(text(f"select min(a.started) from media_pipeline.audio_files a where {args.scope}")).scalar()
        max_started = c.execute(text(f"select max(a.started) from media_pipeline.audio_files a where {args.scope}")).scalar()

        print("dexter_audio_rows:", audio_rows)
        print("dexter_unique_phones:", uniq_phone)
        print("dexter_unique_phone_campaign:", uniq_phone_campaign)
        print("dexter_started_range:", min_started, "->", max_started)

        print("\nTop campaigns by rows:")
        rows = c.execute(
            text(
                f"""
select coalesce(a.campaign_name,'') as campaign_name, count(*) as n
from media_pipeline.audio_files a
where {args.scope}
group by 1
order by n desc
limit {int(args.top)}
"""
            )
        ).fetchall()
        for name, n in rows:
            print(f"- {name}: {n}")

        print("\nTop campaigns by distinct phones:")
        rows = c.execute(
            text(
                f"""
select coalesce(a.campaign_name,'') as campaign_name, count(distinct a.phone) as n
from media_pipeline.audio_files a
where {args.scope}
group by 1
order by n desc
limit {int(args.top)}
"""
            )
        ).fetchall()
        for name, n in rows:
            print(f"- {name}: {n}")

        print("\nCall count per phone (summary):")
        # Percentiles via ordered-set aggregates
        row = c.execute(
            text(
                f"""
with per_phone as (
  select a.phone, count(*) as n
  from media_pipeline.audio_files a
  where {args.scope} and a.phone is not null and length(trim(a.phone))>0
  group by 1
)
select
  min(n) as min_calls,
  percentile_cont(0.25) within group (order by n) as p25_calls,
  percentile_cont(0.50) within group (order by n) as median_calls,
  percentile_cont(0.75) within group (order by n) as p75_calls,
  percentile_cont(0.90) within group (order by n) as p90_calls,
  max(n) as max_calls
from per_phone
"""
            )
        ).fetchone()
        print(
            "min:", row[0],
            "p25:", row[1],
            "median:", row[2],
            "p75:", row[3],
            "p90:", row[4],
            "max:", row[5],
        )


if __name__ == "__main__":
    main()

