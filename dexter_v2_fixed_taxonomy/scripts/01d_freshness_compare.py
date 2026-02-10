import argparse
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import find_dotenv, load_dotenv  # type: ignore

    load_dotenv(find_dotenv(usecwd=True))
except Exception:
    pass


def _strip_quotes(s: str) -> str:
    return str(s or "").strip().strip('"').strip("'")


def _sync_pg_url(url: str) -> str:
    return _strip_quotes(url).replace("postgresql+asyncpg", "postgresql+psycopg2")


def _norm_phone(x: Any) -> str:
    # Dialfire connections_phone is digits-only; normalize to digits.
    s = str(x or "")
    return "".join(ch for ch in s if ch.isdigit())


def _parse_dialfire_dt(rec_started: Any, fired_date: Any) -> Optional[datetime]:
    # Prefer recordings_started (usually ISO with Z). Fallback to transactions_fired_date (YYYY-MM-DD).
    s = str(rec_started or "").strip()
    if s:
        try:
            # e.g. 2026-02-02T13:05:04.923Z
            s2 = s.replace("Z", "+00:00")
            return datetime.fromisoformat(s2)
        except Exception:
            pass
    d = str(fired_date or "").strip()
    if len(d) >= 10:
        d10 = d[:10]
        try:
            # Treat date-only as UTC midnight
            return datetime.fromisoformat(d10 + "T00:00:00+00:00")
        except Exception:
            return None
    return None


@dataclass(frozen=True)
class MediaFreshness:
    latest_audio_started: Any
    latest_transcription_completed_at: Any
    missing_completed_transcriptions_count: int
    newest_missing_audio_started: Any


@dataclass(frozen=True)
class DialfireFreshness:
    phones_used: int
    max_transactions_fired_date_text: Any
    max_recordings_started_varchar: Any
    max_parsed_dt: Optional[datetime]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare transcription DB freshness vs Dialfire reporting freshness.")
    p.add_argument("--db-url", default=os.environ.get("DATABASE_URL", ""), help="Media pipeline Postgres URL (env DATABASE_URL).")
    p.add_argument(
        "--dialfire-db-url",
        default=os.environ.get("DIALFIRE_DATABASE_URL", ""),
        help="Dialfire reporting Postgres URL (env DIALFIRE_DATABASE_URL). Requires an SSH tunnel if URL points at localhost.",
    )
    p.add_argument("--dialfire-view", default=os.environ.get("DIALFIRE_AGENT_DATA_VIEW", "public.agent_data_v3"))
    p.add_argument("--scope", default="a.b2_object_key like 'dexter/audio/%'", help="SQL WHERE predicate scoping audio_files")
    p.add_argument(
        "--gateway-scope",
        default="a.b2_object_key like 'gateway/%/audio/%'",
        help="Secondary scope to report (helps detect prefix changes).",
    )
    p.add_argument("--phone-limit", type=int, default=2000, help="Max distinct phones to use for Dialfire comparison")
    p.add_argument("--out", default="runs/freshness/freshness_report.txt", help="Path to write a text report")
    return p.parse_args()


def _media_freshness(db_url: str, scope: str) -> MediaFreshness:
    from sqlalchemy import create_engine, text

    e = create_engine(db_url, connect_args={"connect_timeout": 5}, pool_pre_ping=True, pool_recycle=1800)
    with e.connect() as c:
        latest_audio = c.execute(text(f"select max(a.started) from media_pipeline.audio_files a where {scope}")).scalar()
        latest_completed = c.execute(
            text(
                f"""
select max(t.completed_at)
from media_pipeline.audio_files a
join media_pipeline.transcriptions t on t.audio_file_id=a.id
where {scope} and t.status='completed'
"""
            )
        ).scalar()
        missing = int(
            c.execute(
                text(
                    f"""
select count(*)
from media_pipeline.audio_files a
left join media_pipeline.transcriptions t
  on t.audio_file_id=a.id and t.status='completed'
where {scope} and t.id is null
"""
                )
            ).scalar()
            or 0
        )
        newest_missing = c.execute(
            text(
                f"""
select max(a.started)
from media_pipeline.audio_files a
left join media_pipeline.transcriptions t
  on t.audio_file_id=a.id and t.status='completed'
where {scope} and t.id is null
"""
            )
        ).scalar()

    return MediaFreshness(
        latest_audio_started=latest_audio,
        latest_transcription_completed_at=latest_completed,
        missing_completed_transcriptions_count=missing,
        newest_missing_audio_started=newest_missing,
    )


def _media_distinct_phones(db_url: str, scope: str, limit: int) -> list[str]:
    from sqlalchemy import create_engine, text

    e = create_engine(db_url, connect_args={"connect_timeout": 5}, pool_pre_ping=True, pool_recycle=1800)
    with e.connect() as c:
        lim = max(0, int(limit))
        rows = c.execute(
            text(
                f"""
select distinct a.phone
from media_pipeline.audio_files a
where {scope} and a.phone is not null
limit :lim
"""
            ),
            {"lim": lim},
        ).fetchall()
    phones = sorted({p for p in (_norm_phone(r[0]) for r in rows) if p})
    return phones[:lim]


def _dialfire_freshness(dialfire_db_url: str, view: str, phones: list[str]) -> DialfireFreshness:
    from sqlalchemy import bindparam, create_engine, text

    e = create_engine(
        dialfire_db_url,
        connect_args={"connect_timeout": 5},
        pool_pre_ping=True,
        pool_recycle=1800,
    )

    # 1) cheap max values as stored (lexicographic works for YYYY-MM-DD and ISO 8601-ish strings)
    q_max = (
        text(
            f"""
select
  max(transactions_fired_date) as max_fired_date,
  max(recordings_started) as max_recordings_started
from {view}
where connections_phone in :phones
"""
        )
        .bindparams(bindparam("phones", expanding=True))
        .execution_options(stream_results=True)
    )

    # 2) robust max datetime by fetching only the two timestamp-ish columns for the phone subset
    q_cols = (
        text(
            f"""
select recordings_started, transactions_fired_date
from {view}
where connections_phone in :phones
"""
        )
        .bindparams(bindparam("phones", expanding=True))
        .execution_options(stream_results=True)
    )

    max_fired: Any = None
    max_rec: Any = None
    max_parsed: Optional[datetime] = None
    with e.connect() as c:
        r = c.execute(q_max, {"phones": phones}).fetchone()
        if r is not None:
            max_fired = r[0]
            max_rec = r[1]

        for rec_started, fired_date in c.execute(q_cols, {"phones": phones}):
            dt = _parse_dialfire_dt(rec_started, fired_date)
            if dt and (max_parsed is None or dt > max_parsed):
                max_parsed = dt

    return DialfireFreshness(
        phones_used=len(phones),
        max_transactions_fired_date_text=max_fired,
        max_recordings_started_varchar=max_rec,
        max_parsed_dt=max_parsed,
    )


def main() -> None:
    args = parse_args()
    if not args.db_url:
        raise SystemExit("DATABASE_URL is not set. Provide --db-url or set $env:DATABASE_URL.")

    media_url = _sync_pg_url(args.db_url)
    dialfire_url = _sync_pg_url(args.dialfire_db_url) if args.dialfire_db_url else ""

    lines: list[str] = []
    lines.append("Freshness report: transcription DB vs Dialfire reporting DB")
    lines.append(f"scope: {args.scope}")
    lines.append("")

    media_primary = _media_freshness(media_url, args.scope)
    lines.append("[media_pipeline_primary_scope]")
    lines.append(f"scope: {args.scope}")
    lines.append(f"latest_audio_started: {media_primary.latest_audio_started}")
    lines.append(f"latest_transcription_completed_at: {media_primary.latest_transcription_completed_at}")
    lines.append(f"missing_completed_transcriptions_count: {media_primary.missing_completed_transcriptions_count}")
    lines.append(f"newest_missing_audio_started: {media_primary.newest_missing_audio_started}")
    lines.append("")

    media_gateway = _media_freshness(media_url, args.gateway_scope)
    lines.append("[media_pipeline_gateway_scope]")
    lines.append(f"scope: {args.gateway_scope}")
    lines.append(f"latest_audio_started: {media_gateway.latest_audio_started}")
    lines.append(f"latest_transcription_completed_at: {media_gateway.latest_transcription_completed_at}")
    lines.append(f"missing_completed_transcriptions_count: {media_gateway.missing_completed_transcriptions_count}")
    lines.append(f"newest_missing_audio_started: {media_gateway.newest_missing_audio_started}")
    lines.append("")

    media_overall = _media_freshness(media_url, "1=1")
    lines.append("[media_pipeline_overall]")
    lines.append("scope: (all audio_files)")
    lines.append(f"latest_audio_started: {media_overall.latest_audio_started}")
    lines.append(f"latest_transcription_completed_at: {media_overall.latest_transcription_completed_at}")
    lines.append(f"missing_completed_transcriptions_count: {media_overall.missing_completed_transcriptions_count}")
    lines.append(f"newest_missing_audio_started: {media_overall.newest_missing_audio_started}")
    lines.append("")

    dialfire: Optional[DialfireFreshness] = None
    dialfire_err: Optional[str] = None
    if dialfire_url:
        try:
            phones = _media_distinct_phones(media_url, args.scope, args.phone_limit)
            dialfire = _dialfire_freshness(dialfire_url, args.dialfire_view, phones)
        except Exception as ex:
            dialfire_err = f"{type(ex).__name__}: {ex}"

    lines.append("[dialfire]")
    lines.append(f"view: {args.dialfire_view}")
    if dialfire:
        lines.append(f"phones_used_for_compare: {dialfire.phones_used}")
        lines.append(f"dialfire_max_transactions_fired_date_text: {dialfire.max_transactions_fired_date_text}")
        lines.append(f"dialfire_max_recordings_started_varchar: {dialfire.max_recordings_started_varchar}")
        lines.append(f"dialfire_max_parsed_datetime: {dialfire.max_parsed_dt}")
    elif dialfire_err:
        lines.append(f"dialfire_connect_or_query_error: {dialfire_err}")
        lines.append("note: If your Dialfire URL uses localhost:5434, ensure the SSH tunnel is up in an interactive terminal.")
    else:
        lines.append("dialfire_connect_or_query_error: (skipped) DIALFIRE_DATABASE_URL not set")

    report = "\n".join(lines) + "\n"
    print(report, end="")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print("Wrote report:", out_path)


if __name__ == "__main__":
    main()

