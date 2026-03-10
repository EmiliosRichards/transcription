from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def _set_env_if_provided(name: str, value: str | None) -> None:
    if value is None:
        return
    os.environ[name] = value


def _load_dotenv(path: Path, *, override: bool = False) -> List[str]:
    """
    Minimal .env loader (no external deps).
    Returns a list of keys that were set.
    """
    if not path.exists():
        raise FileNotFoundError(str(path))
    keys_set: List[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        val = v.strip()
        if not key:
            continue
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        if not override and key in os.environ and str(os.environ.get(key) or "") != "":
            continue
        os.environ[key] = val
        keys_set.append(key)
    return keys_set


def _safe_json(obj: Any) -> Any:
    """Best-effort JSON-serializable conversion."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, list):
        return [_safe_json(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _safe_json(v) for k, v in obj.items()}
    return str(obj)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run Manuav eval + partner match + pitch suite.")
    ap.add_argument("--url", action="append", default=[], help="Company URL (repeatable)")
    ap.add_argument("--urls-file", default="", help="Path to text file with one URL per line")
    ap.add_argument("--out", default="", help="Output JSONL path (default: ./chatbot_app/backend/suite_outputs/...)")
    ap.add_argument("--sleep-seconds", type=float, default=0.0, help="Sleep between companies (rate limiting)")
    ap.add_argument("--dotenv", default="", help="Optional .env file to load (key=value lines)")
    ap.add_argument("--dotenv-override", action="store_true", help="Override existing env vars with .env values")

    # Cost/speed controls (override env defaults for this run)
    ap.add_argument("--eval-model", default="", help="Override COMPANY_EVAL_MODEL")
    ap.add_argument("--eval-max-tool-calls", default="", help="Override COMPANY_EVAL_MAX_TOOL_CALLS")
    ap.add_argument("--eval-second-query", default="", help="Override COMPANY_EVAL_SECOND_QUERY (1/0)")
    ap.add_argument("--intel-model", default="", help="Override COMPANY_INTEL_MODEL")
    ap.add_argument("--intel-max-tool-calls", default="", help="Override COMPANY_INTEL_MAX_TOOL_CALLS")
    ap.add_argument("--pitch-model", default="", help="Override COMPANY_PITCH_MODEL")
    ap.add_argument("--pitch-timeout-seconds", default="", help="Override COMPANY_PITCH_TIMEOUT_SECONDS")

    args = ap.parse_args()

    # Resolve paths relative to backend root (this script lives in <repo>/chatbot_app/backend/scripts/)
    backend_root = Path(__file__).resolve().parents[1]
    repo_root = backend_root.parents[1]

    if args.dotenv:
        dotenv_path = Path(args.dotenv)
        if not dotenv_path.is_absolute():
            # Try relative to repo root first, then backend root.
            cand = (repo_root / dotenv_path).resolve()
            dotenv_path = cand if cand.exists() else (backend_root / dotenv_path).resolve()
        keys = _load_dotenv(dotenv_path, override=bool(args.dotenv_override))
        # Do not print values (secrets). Only show whether key was loaded.
        print(f"[suite] loaded dotenv={dotenv_path} keys={len(keys)}", flush=True)

    urls: List[str] = []
    for u in args.url:
        u = (u or "").strip()
        if u:
            urls.append(u)

    if args.urls_file:
        p = Path(args.urls_file)
        if not p.exists():
            raise SystemExit(f"urls-file not found: {p}")
        for ln in p.read_text(encoding="utf-8").splitlines():
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            urls.append(s)

    # de-dup preserving order
    seen = set()
    urls = [u for u in urls if not (u in seen or seen.add(u))]
    if not urls:
        raise SystemExit("No URLs provided. Use --url or --urls-file.")

    # Apply overrides
    _set_env_if_provided("COMPANY_EVAL_MODEL", args.eval_model or None)
    _set_env_if_provided("COMPANY_EVAL_MAX_TOOL_CALLS", args.eval_max_tool_calls or None)
    _set_env_if_provided("COMPANY_EVAL_SECOND_QUERY", args.eval_second_query or None)
    _set_env_if_provided("COMPANY_INTEL_MODEL", args.intel_model or None)
    _set_env_if_provided("COMPANY_INTEL_MAX_TOOL_CALLS", args.intel_max_tool_calls or None)
    _set_env_if_provided("COMPANY_PITCH_MODEL", args.pitch_model or None)
    _set_env_if_provided("COMPANY_PITCH_TIMEOUT_SECONDS", args.pitch_timeout_seconds or None)

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Missing OPENAI_API_KEY in environment.")

    # Import backend code
    sys.path.append(str(backend_root))

    from app.services.company_intel import evaluate_company_url, generate_sales_pitch_for_company  # type: ignore

    out_path = Path(args.out) if args.out else None
    if out_path is None:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        out_path = backend_root / "suite_outputs" / f"suite_{ts}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[suite] urls={len(urls)} out={out_path}", flush=True)
    print(
        "[suite] eval_model=%s eval_max_tool_calls=%s intel_model=%s pitch_model=%s"
        % (
            os.environ.get("COMPANY_EVAL_MODEL", ""),
            os.environ.get("COMPANY_EVAL_MAX_TOOL_CALLS", ""),
            os.environ.get("COMPANY_INTEL_MODEL", ""),
            os.environ.get("COMPANY_PITCH_MODEL", ""),
        )
        ,
        flush=True,
    )

    with out_path.open("w", encoding="utf-8") as f:
        for i, url in enumerate(urls, start=1):
            t0 = time.time()
            row: Dict[str, Any] = {"input_url": url, "ok": False}
            try:
                ev = evaluate_company_url(url=url, include_description=True)
                pitch = generate_sales_pitch_for_company(
                    company_url=ev.get("input_url") or url,
                    company_name=ev.get("company_name") or "",
                    description=ev.get("description"),
                    eval_positives=ev.get("positives") or [],
                    eval_concerns=ev.get("concerns") or [],
                    eval_fit_attributes=ev.get("fit_attributes") or {},
                )
                row.update(
                    {
                        "ok": True,
                        "eval": _safe_json(ev),
                        "pitch": _safe_json(pitch),
                    }
                )
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"

            row["elapsed_seconds"] = round(time.time() - t0, 3)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()

            status = "OK" if row.get("ok") else "ERR"
            score = None
            try:
                score = float(((row.get("eval") or {}) if isinstance(row.get("eval"), dict) else {}).get("score") or 0)
            except Exception:
                score = None
            print(f"[suite] {i}/{len(urls)} {status} score={score} url={url}", flush=True)

            if args.sleep_seconds and i < len(urls):
                time.sleep(float(args.sleep_seconds))

    print("[suite] done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

