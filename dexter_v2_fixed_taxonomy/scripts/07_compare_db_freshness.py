import argparse
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore

    load_dotenv(find_dotenv(usecwd=True))
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare freshness between media_pipeline DB and Dialfire reporting DB.")
    p.add_argument("--media-db-url", default=os.environ.get("DATABASE_URL", ""), help="Media pipeline DB URL (env DATABASE_URL)")
    p.add_argument(
        "--dialfire-db-url",
        default=os.environ.get("DIALFIRE_DATABASE_URL", ""),
        help="Dialfire reporting DB URL (env DIALFIRE_DATABASE_URL)",
    )
    p.add_argument("--dialfire-view", default="public.agent_data_v3", help="Dialfire view to inspect")
    p.add_argument("--out", default=None, help="Optional path to write JSON report (UTF-8).")
    return p.parse_args()


def _mk_engine(url: str):
    raw = str(url or "").strip().strip('"').strip("'")
    url2 = raw.replace("postgresql+asyncpg", "postgresql+psycopg2")
    from sqlalchemy import create_engine  # lazy import

    return create_engine(url2, pool_pre_ping=True, connect_args={"connect_timeout": 5})


def _exists(engine, reg: str) -> bool:
    from sqlalchemy import text

    with engine.connect() as c:
        return bool(c.execute(text("select to_regclass(:r) is not null"), {"r": reg}).scalar())


def _scalar(engine, sql: str, params: Optional[Dict[str, Any]] = None) -> Any:
    from sqlalchemy import text

    with engine.connect() as c:
        return c.execute(text(sql), params or {}).scalar()


def _parse_dt(x: Any) -> Optional[datetime]:
    if x is None:
        return None
    if isinstance(x, datetime):
        return x
    s = str(x).strip()
    if not s:
        return None
    # Try ISO with Z
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        pass
    # Try YYYY-MM-DD
    try:
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return datetime.fromisoformat(s[:10] + "T00:00:00+00:00")
    except Exception:
        return None
    return None


def _age_days(dt: Optional[datetime]) -> Optional[float]:
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    dtu = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return round((now - dtu).total_seconds() / 86400.0, 2)


def main() -> None:
    args = parse_args()
    if not args.media_db_url:
        raise SystemExit("DATABASE_URL not set")
    if not args.dialfire_db_url:
        raise SystemExit("DIALFIRE_DATABASE_URL not set")

    e_media = _mk_engine(args.media_db_url)
    e_df = _mk_engine(args.dialfire_db_url)

    # Presence checks: do we have the underlying dbsync tables in each DB?
    regs = {
        "media_pipeline.audio_files": "media_pipeline.audio_files",
        "media_pipeline.transcriptions": "media_pipeline.transcriptions",
        "public.contacts": "public.contacts",
        "public.transactions": "public.transactions",
        "public.recordings": "public.recordings",
        "dialfire.agent_view": args.dialfire_view,
    }

    presence = {"media_db": {}, "dialfire_db": {}}
    errors: Dict[str, str] = {}

    for k, reg in regs.items():
        try:
            presence["media_db"][k] = _exists(e_media, reg)
        except Exception as ex:
            presence["media_db"][k] = False
            errors.setdefault("media_db", f"{type(ex).__name__}: {ex}")
        try:
            presence["dialfire_db"][k] = _exists(e_df, reg)
        except Exception as ex:
            presence["dialfire_db"][k] = False
            errors.setdefault("dialfire_db", f"{type(ex).__name__}: {ex}")

    # Freshness signals
    media = {}
    # media_pipeline freshness (Dexter-specific)
    try:
        if presence["media_db"]["media_pipeline.audio_files"]:
            media["latest_audio_started"] = _scalar(
                e_media, "select max(a.started) from media_pipeline.audio_files a where a.b2_object_key like 'dexter/audio/%'"
            )
        if presence["media_db"]["media_pipeline.transcriptions"]:
            media["latest_transcription_completed_at"] = _scalar(
                e_media,
                """
select max(t.completed_at)
from media_pipeline.audio_files a
join media_pipeline.transcriptions t on t.audio_file_id=a.id
where a.b2_object_key like 'dexter/audio/%' and t.status='completed'
""",
            )
    except Exception as ex:
        errors.setdefault("media_db_freshness", f"{type(ex).__name__}: {ex}")

    # Underlying dbsync freshness (if present)
    try:
        if presence["media_db"]["public.transactions"]:
            media["transactions_latest_fired"] = _scalar(
                e_media, "select max(fired) from public.transactions where fired is not null"
            )
        if presence["media_db"]["public.recordings"]:
            media["recordings_latest_started"] = _scalar(
                e_media, "select max(started) from public.recordings where started is not null"
            )
    except Exception as ex:
        errors.setdefault("media_db_dbsync_freshness", f"{type(ex).__name__}: {ex}")

    df = {}
    # Dialfire freshness from agent view (always available per our preflight)
    try:
        if presence["dialfire_db"]["dialfire.agent_view"]:
            df["agent_view_max_fired_date_text"] = _scalar(e_df, f"select max(transactions_fired_date) from {args.dialfire_view}")
            df["agent_view_max_recordings_started_text"] = _scalar(e_df, f"select max(recordings_started) from {args.dialfire_view}")
        # Underlying dbsync freshness if present (recordings.started is usually reliable)
        if presence["dialfire_db"]["public.recordings"]:
            df["recordings_latest_started"] = _scalar(e_df, "select max(started) from public.recordings where started is not null")
    except Exception as ex:
        errors.setdefault("dialfire_db_freshness", f"{type(ex).__name__}: {ex}")

    # Build compact report
    def enrich(d: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(d)
        for k, v in list(out.items()):
            dt = _parse_dt(v)
            if dt:
                # Make JSON-serializable and keep parsed/age fields.
                out[k] = (dt.isoformat() if dt.tzinfo else dt.replace(tzinfo=timezone.utc).isoformat())
                out[k + "_parsed_utc"] = dt.astimezone(timezone.utc).isoformat()
                out[k + "_age_days"] = _age_days(dt)
            elif isinstance(v, datetime):
                out[k] = v.isoformat()
        return out

    report = {
        "errors": errors or None,
        "presence": presence,
        "media_db_freshness": enrich(media),
        "dialfire_db_freshness": enrich(df),
    }

    import json

    s = json.dumps(report, ensure_ascii=False, indent=2)
    print(s)
    if args.out:
        from pathlib import Path

        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(s, encoding="utf-8")


if __name__ == "__main__":
    main()

