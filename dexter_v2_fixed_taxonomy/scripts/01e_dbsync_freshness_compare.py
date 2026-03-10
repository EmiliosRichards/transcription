import argparse
import os
from dataclasses import dataclass
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


@dataclass(frozen=True)
class DbsyncFreshness:
    db: str
    user: str
    has_media_pipeline_schema: bool
    has_audio_files: bool
    has_transcriptions: bool
    has_agent_data_v3: bool
    has_contacts: bool
    has_recordings: bool
    has_transactions: bool
    transactions_latest_fired: Any
    transactions_latest_changed: Any
    recordings_latest_started: Any
    recordings_latest_changed: Any
    contacts_latest_created_date: Any
    contacts_latest_changed: Any


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare Dialfire dbsync freshness across media DB and reporting DB.")
    p.add_argument("--db-url", default=os.environ.get("DATABASE_URL", ""), help="Media pipeline Postgres URL (env DATABASE_URL).")
    p.add_argument(
        "--dialfire-db-url",
        default=os.environ.get("DIALFIRE_DATABASE_URL", ""),
        help="Dialfire reporting Postgres URL (env DIALFIRE_DATABASE_URL).",
    )
    p.add_argument("--out", default="runs/freshness/dbsync_freshness_compare.txt", help="Path to write a text report")
    return p.parse_args()


def _scalar(c, q: str, params: Optional[dict] = None) -> Any:
    from sqlalchemy import text

    return c.execute(text(q), params or {}).scalar()


def _safe_scalar(c, name: str, q: str) -> Any:
    try:
        return _scalar(c, q)
    except Exception as ex:
        return f"ERROR({name}): {type(ex).__name__}: {ex}"


def _probe(engine) -> DbsyncFreshness:
    from sqlalchemy import text

    with engine.connect() as c:
        db = c.execute(text("select current_database()")).scalar()
        user = c.execute(text("select current_user")).scalar()
        has_media_pipeline_schema = bool(
            c.execute(text("select exists(select 1 from information_schema.schemata where schema_name='media_pipeline')")).scalar()
        )
        has_audio_files = bool(c.execute(text("select to_regclass('media_pipeline.audio_files') is not null")).scalar())
        has_transcriptions = bool(c.execute(text("select to_regclass('media_pipeline.transcriptions') is not null")).scalar())
        has_agent_data_v3 = bool(c.execute(text("select to_regclass('public.agent_data_v3') is not null")).scalar())
        has_contacts = bool(c.execute(text("select to_regclass('public.contacts') is not null")).scalar())
        has_recordings = bool(c.execute(text("select to_regclass('public.recordings') is not null")).scalar())
        has_transactions = bool(c.execute(text("select to_regclass('public.transactions') is not null")).scalar())

        # These are varchar/text in the dbsync tables; ordering is safe for ISO-like strings.
        transactions_latest_fired = None
        transactions_latest_changed = None
        recordings_latest_started = None
        recordings_latest_changed = None
        contacts_latest_created_date = None
        contacts_latest_changed = None

        if has_transactions:
            transactions_latest_fired = _safe_scalar(
                c,
                "transactions_latest_fired",
                "select fired from public.transactions where fired is not null order by fired desc limit 1",
            )
            transactions_latest_changed = _safe_scalar(
                c,
                "transactions_latest_changed",
                'select "$changed" from public.transactions where "$changed" is not null order by "$changed" desc limit 1',
            )

        if has_recordings:
            recordings_latest_started = _safe_scalar(
                c,
                "recordings_latest_started",
                "select started from public.recordings where started is not null order by started desc limit 1",
            )
            recordings_latest_changed = _safe_scalar(
                c,
                "recordings_latest_changed",
                'select "$changed" from public.recordings where "$changed" is not null order by "$changed" desc limit 1',
            )

        if has_contacts:
            contacts_latest_created_date = _safe_scalar(
                c,
                "contacts_latest_created_date",
                'select "$created_date" from public.contacts where "$created_date" is not null order by "$created_date" desc limit 1',
            )
            contacts_latest_changed = _safe_scalar(
                c,
                "contacts_latest_changed",
                'select "$changed" from public.contacts where "$changed" is not null order by "$changed" desc limit 1',
            )

    return DbsyncFreshness(
        db=str(db),
        user=str(user),
        has_media_pipeline_schema=bool(has_media_pipeline_schema),
        has_audio_files=bool(has_audio_files),
        has_transcriptions=bool(has_transcriptions),
        has_agent_data_v3=bool(has_agent_data_v3),
        has_contacts=bool(has_contacts),
        has_recordings=bool(has_recordings),
        has_transactions=bool(has_transactions),
        transactions_latest_fired=transactions_latest_fired,
        transactions_latest_changed=transactions_latest_changed,
        recordings_latest_started=recordings_latest_started,
        recordings_latest_changed=recordings_latest_changed,
        contacts_latest_created_date=contacts_latest_created_date,
        contacts_latest_changed=contacts_latest_changed,
    )


def _render(label: str, r: DbsyncFreshness) -> str:
    lines: list[str] = []
    lines.append(f"[{label}] db={r.db} user={r.user}")
    lines.append(f"has_media_pipeline_schema: {r.has_media_pipeline_schema}")
    lines.append(f"has_media_pipeline.audio_files: {r.has_audio_files}")
    lines.append(f"has_media_pipeline.transcriptions: {r.has_transcriptions}")
    lines.append(f"has_public.agent_data_v3: {r.has_agent_data_v3}")
    lines.append(f"has_public.contacts: {r.has_contacts}")
    lines.append(f"has_public.recordings: {r.has_recordings}")
    lines.append(f"has_public.transactions: {r.has_transactions}")
    lines.append(f"transactions_latest_fired: {r.transactions_latest_fired}")
    lines.append(f"transactions_latest_changed: {r.transactions_latest_changed}")
    lines.append(f"recordings_latest_started: {r.recordings_latest_started}")
    lines.append(f"recordings_latest_changed: {r.recordings_latest_changed}")
    lines.append(f"contacts_latest_created_date: {r.contacts_latest_created_date}")
    lines.append(f"contacts_latest_changed: {r.contacts_latest_changed}")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    if not args.db_url:
        raise SystemExit("DATABASE_URL is not set.")

    from sqlalchemy import create_engine

    media_url = _sync_pg_url(args.db_url)
    dialfire_url = _sync_pg_url(args.dialfire_db_url) if args.dialfire_db_url else ""

    media_engine = create_engine(media_url, connect_args={"connect_timeout": 5}, pool_pre_ping=True, pool_recycle=1800)
    dialfire_engine = create_engine(dialfire_url, connect_args={"connect_timeout": 5}, pool_pre_ping=True, pool_recycle=1800) if dialfire_url else None

    lines: list[str] = []
    lines.append("DBSYNC freshness compare (contacts/recordings/transactions + agent view + media_pipeline)")
    lines.append("")

    media = _probe(media_engine)
    lines.append(_render("MEDIA_DB", media))
    lines.append("")

    if dialfire_engine is None:
        lines.append("[DIALFIRE_DB] skipped: DIALFIRE_DATABASE_URL not set")
    else:
        try:
            df = _probe(dialfire_engine)
            lines.append(_render("DIALFIRE_DB", df))
        except Exception as ex:
            lines.append(f"[DIALFIRE_DB] ERROR: {type(ex).__name__}: {ex}")

    report = "\n".join(lines) + "\n"
    print(report, end="")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print("Wrote report:", out_path)


if __name__ == "__main__":
    main()

