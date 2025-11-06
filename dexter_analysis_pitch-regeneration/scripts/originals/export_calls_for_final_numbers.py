import os
import csv
import json
from typing import List, Dict
from sqlalchemy import create_engine, text


FINAL_NUMBERS_CSV = os.environ.get(
    "FINAL_NUMBERS_CSV", r"output\dexter_final_numbers.csv"
)
OUT_FLAT = os.environ.get(
    "OUT_FLAT", r"output\dexter_calls_flat_final.csv"
)
OUT_GROUPS = os.environ.get(
    "OUT_GROUPS", r"output\dexter_calls_by_phone_campaign_final.jsonl"
)
SCOPE_PREDICATE = os.environ.get(
    "DEXTER_SCOPE", "a.b2_object_key like 'dexter/audio/%'"
)


def digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def load_included_digits(csv_path: str) -> List[str]:
    digits_list: List[str] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            raw = (row.get("phone") or "").strip()
            if not raw:
                continue
            d = digits(raw)
            if d:
                digits_list.append(d)
    # de-duplicate preserving order
    seen = set()
    uniq: List[str] = []
    for d in digits_list:
        if d in seen:
            continue
        seen.add(d)
        uniq.append(d)
    return uniq


def values_cte_for_list(col: str, vals: List[str]) -> (str, Dict[str, str]):
    params: Dict[str, str] = {}
    pieces: List[str] = []
    for i, v in enumerate(vals):
        key = f"v{i}"
        params[key] = v
        pieces.append(f"(:{key})")
    cte = f"with nums({col}) as (values {', '.join(pieces)})"
    return cte, params


def main() -> None:
    nums = load_included_digits(FINAL_NUMBERS_CSV)
    if not nums:
        raise SystemExit(f"No phones found in {FINAL_NUMBERS_CSV}")

    cte, params = values_cte_for_list("d", nums)

    db_url = os.environ["DATABASE_URL"].replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    e = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={
            "keepalives": 1,
            "keepalives_idle": 60,
            "keepalives_interval": 30,
            "keepalives_count": 5,
            "connect_timeout": 10,
        },
    )

    sql = text(
        f"""
{cte}
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
join nums on regexp_replace(coalesce(a.phone,''),'[^0-9]+','','g') = nums.d
where {SCOPE_PREDICATE}
order by a.phone, campaign_name, a.started nulls last, a.id
"""
    )

    rows: List[Dict] = []
    with e.connect() as c:
        for r in c.execute(sql, params):
            rows.append(dict(r._mapping))

    def iso(x):
        return x.isoformat() if hasattr(x, "isoformat") else (x or "")

    os.makedirs(os.path.dirname(OUT_FLAT) or ".", exist_ok=True)
    with open(OUT_FLAT, "w", newline="", encoding="utf-8") as f:
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
        ]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            r["started"] = iso(r.get("started"))
            r["stopped"] = iso(r.get("stopped"))
            r["completed_at"] = iso(r.get("completed_at"))
            w.writerow({k: r.get(k, "") for k in cols})

    from collections import defaultdict

    groups = defaultdict(list)
    for r in rows:
        key = (r.get("phone", ""), r.get("campaign_name", ""))
        groups[key].append(
            {
                "audio_id": r.get("audio_id"),
                "b2_object_key": r.get("b2_object_key"),
                "started": iso(r.get("started")),
                "stopped": iso(r.get("stopped")),
                "status": r.get("status") or "",
                "completed_at": iso(r.get("completed_at")),
                "transcript_text": r.get("transcript_text") or "",
                "segments_json": r.get("segments_json") or "",
            }
        )

    with open(OUT_GROUPS, "w", encoding="utf-8") as f:
        for (phone, campaign), calls in groups.items():
            f.write(
                json.dumps(
                    {"phone": phone, "campaign_name": campaign, "calls": calls},
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(
        f"Exported {len(rows)} call rows -> {OUT_FLAT}\n"
        f"Grouped {len(groups)} (phone,campaign) -> {OUT_GROUPS}"
    )


if __name__ == "__main__":
    main()


