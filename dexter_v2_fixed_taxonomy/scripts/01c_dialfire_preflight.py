import argparse
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore

    load_dotenv(find_dotenv(usecwd=True))
except Exception:
    pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Preflight checks for Dialfire reporting DB (agent_data_v*).")
    p.add_argument(
        "--db-url",
        default=os.environ.get("DIALFIRE_DATABASE_URL", ""),
        help="Dialfire reporting Postgres URL (defaults to env DIALFIRE_DATABASE_URL)",
    )
    p.add_argument(
        "--views",
        default="public.agent_data_v3,public.agent_data_v2,public.agent_data,public.campaign_state_reference_data",
        help="Comma-separated list of views to probe (schema-qualified).",
    )
    p.add_argument(
        "--sample",
        type=int,
        default=2000,
        help="Sample size for lightweight status/detail counts (avoids full COUNT(*) scans). Set 0 to skip sampling.",
    )
    p.add_argument(
        "--sample-large-views",
        action="store_true",
        help="Also sample large agent_data_v* views (can still be slow). By default we only sample smaller reference views.",
    )
    p.add_argument("--out", default=None, help="Optional path to write a text report")
    return p.parse_args()


def _split_schema_name(qualified: str) -> Tuple[str, str]:
    q = (qualified or "").strip()
    if "." in q:
        s, n = q.split(".", 1)
        return s.strip() or "public", n.strip()
    return "public", q


def _format_target(url: str) -> str:
    try:
        from sqlalchemy.engine.url import make_url

        u = make_url(url)
        return f"host={u.host} port={u.port} db={u.database} user={u.username}"
    except Exception as ex:
        return f"(could not parse url) {type(ex).__name__}: {ex}"


def main() -> None:
    args = parse_args()
    if not args.db_url:
        raise SystemExit("DIALFIRE_DATABASE_URL is not set. Provide --db-url or set $env:DIALFIRE_DATABASE_URL.")

    raw = str(args.db_url).strip().strip('"').strip("'")
    db_url = raw.replace("postgresql+asyncpg", "postgresql+psycopg2")

    from sqlalchemy import create_engine, text  # lazy import

    # Use a short connect timeout so misconfigured tunnels fail fast.
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"connect_timeout": 5},
    )

    view_list = [v.strip() for v in str(args.views).split(",") if v.strip()]

    lines: List[str] = []
    lines.append("Dialfire DB preflight")
    lines.append(f"target: {_format_target(db_url)}")
    lines.append("")

    # Probe views existence
    found: List[str] = []
    for v in view_list:
        schema, name = _split_schema_name(v)
        q = text("select to_regclass(:reg) is not null")
        reg = f"{schema}.{name}"
        with engine.connect() as c:
            ok = bool(c.execute(q, {"reg": reg}).scalar())
        lines.append(f"exists {reg}: {ok}")
        if ok:
            found.append(reg)

    lines.append("")
    if not found:
        lines.append("No specified views found. Check permissions/schema/view names.")
        report = "\n".join(lines) + "\n"
        print(report, end="")
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(report, encoding="utf-8")
            print("Wrote report:", out_path)
        raise SystemExit(1)

    # Column inventory + join candidates
    join_candidate_keywords = [
        "phone",
        "campaign",
        "campaign_id",
        "contacts_campaign_id",
        "contact",
        "contact_id",
        "transactions_status",
        "transactions_status_detail",
        "transaction",
        "recording",
        "fired",
        "started",
        "stopped",
        "timestamp",
        "time",
        "user_login",
        "agent",
    ]

    for reg in found:
        schema, name = _split_schema_name(reg)
        lines.append("=" * 80)
        lines.append(f"View: {schema}.{name}")

        # Avoid forcing evaluation of large reporting views (even LIMIT 1 can be slow).
        # We rely on information_schema for column inventory and to_regclass() for existence.
        lines.append("readable: (skipped)")

        # status distribution (only if columns exist)
        try:
            with engine.connect() as c:
                cols = c.execute(
                    text(
                        """
select column_name, data_type, udt_name
from information_schema.columns
where table_schema=:s and table_name=:t
order by ordinal_position
"""
                    ),
                    {"s": schema, "t": name},
                ).fetchall()
            col_names = [str(r[0]) for r in cols]
            col_types: Dict[str, str] = {str(r[0]): f"{r[1]} ({r[2]})" for r in cols}
        except Exception as ex:
            lines.append(f"columns: ERROR: {type(ex).__name__}: {ex}")
            lines.append("")
            continue

        lines.append(f"n_columns: {len(col_names)}")
        # Show a concise column list
        lines.append("columns (first 60): " + ", ".join(col_names[:60]) + (" ..." if len(col_names) > 60 else ""))

        interesting = [c for c in col_names if any(k in c.lower() for k in join_candidate_keywords)]
        lines.append("possible_join_or_outcome_columns: " + (", ".join(interesting) if interesting else "(none)"))
        # Show types for key join columns if present
        key_cols = [
            "connections_phone",
            "recordings_started",
            "recordings_start_time",
            "transactions_fired_date",
            "contacts_id",
            "contacts_campaign_id",
            "transactions_status",
            "transactions_status_detail",
            "recordings_location",
            "transaction_id",
        ]
        present_key_cols = [c for c in key_cols if c in col_types]
        if present_key_cols:
            lines.append("key_column_types:")
            for c in present_key_cols:
                lines.append(f"  - {c}: {col_types.get(c)}")

        # Lightweight sampling-based counts.
        # Default: only sample smaller reference views; sampling agent_data_v* can still be slow.
        is_large = name.startswith("agent_data")
        allow_sampling = (not is_large) or bool(args.sample_large_views)
        if allow_sampling and args.sample and args.sample > 0 and ("transactions_status" in col_names or "transactions_status_detail" in col_names):
            try:
                # Sample only relevant columns (avoid computing/transporting wide rows).
                sample_cols: List[str] = []
                if "transactions_status" in col_names:
                    sample_cols.append("transactions_status")
                if "transactions_status_detail" in col_names:
                    sample_cols.append("transactions_status_detail")
                if not sample_cols:
                    raise RuntimeError("No status columns to sample")

                sample_sql = f"select {', '.join(sample_cols)} from {schema}.{name} limit {int(args.sample)}"
                with engine.connect() as c:
                    rows = c.execute(text(sample_sql)).fetchall()
                # infer column indexes
                idx_status = 0 if "transactions_status" in sample_cols else None
                idx_detail = (sample_cols.index("transactions_status_detail") if "transactions_status_detail" in sample_cols else None)
                status_counts: Dict[str, int] = {}
                detail_counts: Dict[str, int] = {}
                for r in rows:
                    if idx_status is not None:
                        s = (str(r[idx_status]) if r[idx_status] is not None else "").strip() or "(null)"
                        status_counts[s] = status_counts.get(s, 0) + 1
                    if idx_detail is not None:
                        d = (str(r[idx_detail]) if r[idx_detail] is not None else "").replace("\n", " ").strip() or "(null)"
                        # keep only first 120 chars for display
                        d = d[:120]
                        detail_counts[d] = detail_counts.get(d, 0) + 1

                if status_counts:
                    lines.append(f"transactions_status_counts_sampled(n={len(rows)}):")
                    for k, v in sorted(status_counts.items(), key=lambda kv: kv[1], reverse=True)[:20]:
                        lines.append(f"  - {k}: {v}")

                if detail_counts:
                    lines.append(f"top_transactions_status_detail_sampled(n={len(rows)}):")
                    for k, v in sorted(detail_counts.items(), key=lambda kv: kv[1], reverse=True)[:25]:
                        lines.append(f"  - {k}: {v}")
            except Exception as ex:
                lines.append(f"sampling_counts: ERROR: {type(ex).__name__}: {ex}")
        elif is_large and not args.sample_large_views:
            lines.append("sampling_counts: (skipped for agent_data_v*; pass --sample-large-views to enable)")

        lines.append("")

    report = "\n".join(lines) + "\n"
    print(report, end="")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print("Wrote report:", out_path)


if __name__ == "__main__":
    main()

