import argparse
import os
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
    load_dotenv(find_dotenv(usecwd=True))
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Preflight DB checks for Dexter v2 export.")
    p.add_argument("--db-url", default=os.environ.get("DATABASE_URL", ""), help="Postgres URL (defaults to env DATABASE_URL)")
    p.add_argument("--scope", default="a.b2_object_key like 'dexter/audio/%'", help="Scope predicate for Dexter calls")
    p.add_argument("--out", default=None, help="Optional path to write a text report")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not args.db_url:
        raise SystemExit("DATABASE_URL is not set. Provide --db-url or set $env:DATABASE_URL.")

    # Some shells/.env files include surrounding quotes; strip them defensively.
    raw = str(args.db_url).strip().strip('"').strip("'")
    db_url = raw.replace("postgresql+asyncpg", "postgresql+psycopg2")
    from sqlalchemy import create_engine, text  # lazy import
    from sqlalchemy.engine.url import make_url

    lines = []
    lines.append("Dexter v2 DB preflight")
    lines.append(f"scope: {args.scope}")
    try:
        u = make_url(db_url)
        lines.append(f"target: host={u.host} port={u.port} db={u.database} user={u.username}")
    except Exception as ex:
        lines.append(f"target: (could not parse DATABASE_URL) {type(ex).__name__}: {ex}")
    lines.append("")

    checks = []
    # 1) Schema presence
    checks.append(("has_media_pipeline_schema", text("select exists(select 1 from information_schema.schemata where schema_name='media_pipeline')")))
    # 2) Count scoped audio files
    checks.append(("audio_files_scoped_count", text(f"select count(*) from media_pipeline.audio_files a where {args.scope}")))
    # 3) Count scoped transcriptions joined
    checks.append(("transcriptions_scoped_join_count", text(f"""
select count(*)
from media_pipeline.audio_files a
join media_pipeline.transcriptions t on t.audio_file_id = a.id
where {args.scope}
""")))
    # 4) Latest started timestamp
    checks.append(("latest_started_scoped", text(f"select max(a.started) from media_pipeline.audio_files a where {args.scope}")))
    # 5) Null transcript_text count (joined)
    checks.append(("null_transcript_text_scoped", text(f"""
select count(*)
from media_pipeline.audio_files a
join media_pipeline.transcriptions t on t.audio_file_id = a.id
where {args.scope} and (t.transcript_text is null or length(t.transcript_text)=0)
""")))

    e = create_engine(db_url, pool_pre_ping=True, pool_recycle=1800)

    connect_error: Optional[str] = None
    try:
        with e.connect() as c:
            for name, q in checks:
                try:
                    val = c.execute(q).scalar()
                except Exception as ex:
                    val = f"ERROR: {ex}"
                lines.append(f"{name}: {val}")
    except Exception as ex:
        connect_error = f"{type(ex).__name__}: {ex}"
        lines.append(f"connect_error: {connect_error}")

    report = "\n".join(lines) + "\n"
    print(report, end="")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print("Wrote report:", out_path)

    if connect_error is not None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

