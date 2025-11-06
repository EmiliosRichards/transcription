import os
import json
import hashlib
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


# Load .env if present (project root)
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv())
except Exception:
    pass

INPUT_PATH = os.environ.get(
    "INPUT_GROUPED_JSONL", r"output\dexter_calls_by_phone_campaign_final.jsonl"
)
# Default outputs go to analysis folder unless overridden via env
OUT_PATH = os.environ.get(
    "OUT_FREE_EXTRACTION",
    r"data_pipelines\data\transcription_dexter_analysis\dexter_free_extraction.jsonl",
)
CACHE_DIR = os.environ.get("FREE_EXTRACTION_CACHE", r"output\cache\free_extraction")
MODEL = os.environ.get("FREE_EXTRACTION_MODEL", "gpt-4o-mini")
MAX_WORKERS = int(os.environ.get("FREE_EXTRACTION_WORKERS", "4"))
MIN_CHARS = int(os.environ.get("FREE_MIN_CHARS", "240"))
QC_MIN_CHARS = int(os.environ.get("FREE_QC_MIN_CHARS", str(MIN_CHARS)))
HEAD_CHARS = int(os.environ.get("FREE_HEAD_CHARS", "600"))
TAIL_CHARS = int(os.environ.get("FREE_TAIL_CHARS", "1000"))
DEBUG = os.environ.get("FREE_DEBUG", "").strip()
TEMP_STR = os.environ.get("FREE_TEMPERATURE", "").strip()

# Simple German unreachable/voicemail heuristics (lowercased contains-any)
UNREACHABLE_TOKENS = [
    "nicht erreichbar",
    "mailbox",
    "anrufbeantworter",
    "hinterlassen sie eine nachricht",
    "bitte hinterlassen",
    "besetzt",
    "keiner erreichbar",
    "keine zuständigen",
]


PROMPT_SYSTEM = (
    "You will read German cold-call transcripts (one company/phone group per request; if multiple calls are provided, base your answer on the most recent informative call).\n"
    "Extract concise, unconstrained labels plus a verbatim evidence quote.\n\n"
    "Return valid JSON only with exactly these keys:\n"
    "outcome_free_text (English, ≤6 words)\n"
    "reason_free_text (English, ≤10 words; use \"unknown\" if unclear)\n"
    "who_reached (English, one of: \"decision_maker\", \"gatekeeper\", \"unknown\")\n"
    "evidence_quote (German, ≤20 words, exact substring of the provided transcript)\n"
    "confidence (float 0..1)\n\n"
    "What “reason” means (important):\n"
    "reason_free_text = the primary cause that led to the outcome (the why).\n"
    "Do not restate the outcome (e.g., don’t say \"no sale\").\n"
    "Do not include who was reached (that goes in who_reached).\n"
    "Keep it short and concrete (2–10 words).\n"
    "Style grammar: core cause [; optional qualifier]\n\n"
    "Style examples (illustrative only; not a menu—do not force or copy unless it truly matches):\n"
    "outcome_free_text: \"no sale\" | reason_free_text: \"not interested; understood product\" | who_reached: \"decision_maker\"\n"
    "outcome_free_text: \"callback requested\" | reason_free_text: \"timing; interested\" | who_reached: \"decision_maker\"\n"
    "outcome_free_text: \"no sale\" | reason_free_text: \"misunderstood product\" | who_reached: \"decision_maker\"\n"
    "outcome_free_text: \"no sale\" | reason_free_text: \"not decision maker\" | who_reached: \"gatekeeper\"\n"
    "outcome_free_text: \"gatekept\" | reason_free_text: \"refused transfer\" | who_reached: \"gatekeeper\"\n"
    "outcome_free_text: \"unreachable\" | reason_free_text: \"voicemail\" | who_reached: \"unknown\"\n"
    "outcome_free_text: \"no sale\" | reason_free_text: \"too expensive; budget\" | who_reached: \"decision_maker\"\n\n"
    "Rules\n"
    "- Base all fields only on the transcript; no assumptions.\n"
    "- Keep outputs short; no explanations, no extra keys.\n"
    "- If you cannot find a supporting quote, set confidence ≤ 0.5 and still return the best short labels.\n"
    "- The evidence_quote must be a verbatim substring (German) from the transcript.\n"
    "- If unclear, set reason_free_text = \"unknown\".\n"
)


def _hash_key(phone: str, campaign: str) -> str:
    h = hashlib.sha1(f"{phone}|{campaign}".encode("utf-8")).hexdigest()
    return h


def _truncate_text(text: str, max_chars: int = 1600) -> str:
    if not text:
        return ""
    # Override by env HEAD/TAIL to bias outcome region
    max_chars = HEAD_CHARS + TAIL_CHARS + 10
    if len(text) <= max_chars:
        return text
    head = text[:HEAD_CHARS]
    tail = text[-TAIL_CHARS:]
    return head + "\n...\n" + tail


def _prepare_context(one_call: Dict[str, Any]) -> Tuple[str, int]:
    original = str(one_call.get("transcript_text") or "")
    truncated = _truncate_text(original)
    started = one_call.get("started") or ""
    ctx = f"[Call started={started}]\n{truncated}"
    return ctx, max(0, len(original) - len(truncated))


def _parse_ts(s: Any) -> str:
    # Keep ISO strings sortable descending; if None, empty
    return str(s or "")


def _is_unreachable(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    for tok in UNREACHABLE_TOKENS:
        if tok in t:
            return True
    return False


def _select_informative_call(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not calls:
        return {}
    # Sort newest -> oldest by started, then completed_at as tiebreaker
    calls_sorted = sorted(
        calls,
        key=lambda c: (_parse_ts(c.get("started")), _parse_ts(c.get("completed_at"))),
        reverse=True,
    )
    for c in calls_sorted:
        txt = str(c.get("transcript_text") or "")
        if len(txt) >= MIN_CHARS and not _is_unreachable(txt):
            c["_selected_reason"] = "informative"
            return c
    # Fallback to newest
    calls_sorted[0]["_selected_reason"] = "fallback_newest"
    return calls_sorted[0]


def _latest_call_info(calls: List[Dict[str, Any]]) -> Tuple[str, str]:
    if not calls:
        return "", ""
    calls_sorted = sorted(
        calls,
        key=lambda c: (_parse_ts(c.get("started")), _parse_ts(c.get("completed_at"))),
        reverse=True,
    )
    latest = calls_sorted[0]
    return str(latest.get("transcript_text") or ""), str(latest.get("started") or "")


def _call_llm(context: str) -> Dict[str, Any]:
    from openai import OpenAI

    client = OpenAI()
    messages = [
        {"role": "system", "content": PROMPT_SYSTEM},
        {"role": "user", "content": (
            "Kontext (mehrere Anrufe derselben Firma):\n\n" + context + "\n\n"
            "Bitte antworte NUR mit JSON und keine weiteren Erklärungen.")}
    ]
    # Backoff + one retry on JSON
    def _send(msgs) -> str:
        base = 0.5
        for attempt in range(3):  # 2 retries total
            try:
                kwargs = {
                    "model": MODEL,
                    "messages": msgs,  # type: ignore[arg-type]
                    "response_format": {"type": "json_object"},
                }
                # Some models do not support temperature; only pass when explicitly set
                if TEMP_STR:
                    try:
                        kwargs["temperature"] = float(TEMP_STR)
                    except Exception:
                        pass
                resp = client.chat.completions.create(**kwargs)
                return resp.choices[0].message.content or "{}"
            except Exception as e:
                s = str(e).lower()
                transient = ("429" in s) or ("rate" in s) or ("timeout" in s) or ("server" in s) or ("5" in s and "http" in s)
                if attempt >= 2 or not transient:
                    raise
                delay = base * (2 ** attempt) + 0.05
                time.sleep(delay)
        return "{}"

    content = _send(messages)
    try:
        data = json.loads(content)
        data.setdefault("_retried", False)
        data.setdefault("_parse_fallback", False)
        return data
    except Exception:
        messages[-1]["content"] += "\n\nReturn valid JSON only with the required keys."
        content2 = _send(messages)
        try:
            data2 = json.loads(content2)
            data2.setdefault("_retried", True)
            data2.setdefault("_parse_fallback", False)
            return data2
        except Exception:
            return {
                "outcome_free_text": "unknown",
                "reason_free_text": "unknown",
                "who_reached": "unknown",
                "evidence_quote": "",
                "confidence": 0.3,
                "_retried": True,
                "_parse_fallback": True,
            }


def main() -> None:
    # --- Argparse (parameterization via YAML config) ---
    parser = argparse.ArgumentParser(description="Dexter free-label extraction")
    parser.add_argument("--config", default=None, help="Path to YAML config (e.g., config/phaseA.yml)")
    args, unknown = parser.parse_known_args()

    # --- Load config if provided; override globals ---
    output_dir_from_cfg: str | None = None
    prompt_version: str = os.environ.get("FREE_PROMPT_VER", "v3")
    if args.config:
        if yaml is None:
            raise RuntimeError("pyyaml is required for --config usage. Install pyyaml.")
        with open(args.config, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        # Optional keys in YAML
        model = cfg.get("model")
        if model:
            global MODEL
            MODEL = str(model)
        trunc = cfg.get("truncation") or {}
        head = trunc.get("head_chars")
        tail = trunc.get("tail_chars")
        if head is not None:
            global HEAD_CHARS
            HEAD_CHARS = int(head)
        if tail is not None:
            global TAIL_CHARS
            TAIL_CHARS = int(tail)
        mins = cfg.get("min_chars") or {}
        min_sel = mins.get("select")
        min_qc = mins.get("qc")
        if min_sel is not None:
            global MIN_CHARS
            MIN_CHARS = int(min_sel)
        if min_qc is not None:
            global QC_MIN_CHARS
            QC_MIN_CHARS = int(min_qc)
        workers_cfg = cfg.get("workers")
        if workers_cfg is not None:
            global MAX_WORKERS
            MAX_WORKERS = int(workers_cfg)
        pv = cfg.get("prompt_version")
        if pv:
            prompt_version = str(pv)
        output_dir_from_cfg = cfg.get("output_dir")

    # --- Output/run folder structure ---
    def _ensure(dirpath: str) -> str:
        os.makedirs(dirpath, exist_ok=True)
        return dirpath

    run_root = None
    if output_dir_from_cfg:
        run_root = output_dir_from_cfg
        raw_dir = _ensure(os.path.join(run_root, "raw"))
        _ensure(os.path.join(run_root, "interim"))
        _ensure(os.path.join(run_root, "slim"))
        _ensure(os.path.join(run_root, "reports"))
        # Compute OUT_PATH inside raw; avoid overwrite
        def _unique(path: str) -> str:
            if not os.path.exists(path):
                return path
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            base, ext = os.path.splitext(path)
            return f"{base}_{ts}{ext}"

        out_candidate = os.path.join(raw_dir, "dexter_free_extraction.jsonl")
        unique_out = _unique(out_candidate)
        # Update globals used below
        global OUT_PATH
        OUT_PATH = unique_out
        # Move cache under run_root/cache/free_extraction to keep runs tidy
        global CACHE_DIR
        CACHE_DIR = os.path.join(run_root, "cache", "free_extraction")
        os.makedirs(CACHE_DIR, exist_ok=True)
    
    os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    groups: List[Dict[str, Any]] = []
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                groups.append(json.loads(line))
            except Exception:
                continue

    def process_one(g: Tuple[int, Dict[str, Any]]) -> Tuple[int, Dict[str, Any]]:
        idx, item = g
        phone = str(item.get("phone") or "")
        campaign = str(item.get("campaign_name") or "")
        calls = item.get("calls") or []
        chosen = _select_informative_call(calls)
        latest_text, latest_started = _latest_call_info(calls)
        txt_for_hash = str(chosen.get("transcript_text") or "")
        # Cache on latest call content to auto-invalidate when newest changes
        content_key = hashlib.sha1(latest_text.encode("utf-8")).hexdigest()
        key = _hash_key(phone, campaign + "|" + content_key)
        cache_file = os.path.join(CACHE_DIR, key + ".json")
        if DEBUG:
            print(f"start idx={idx} phone={phone} campaign={campaign} cache_file={cache_file}")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as cf:
                    data = json.load(cf)
                    data["_cache_hit"] = True
                    return idx, data
            except Exception:
                pass

        ctx, truncated_chars = _prepare_context(chosen) if chosen else ("", 0)
        if not ctx.strip():
            data = {
                "phone": phone,
                "campaign_name": campaign,
                "outcome_free_text": "unknown",
                "reason_free_text": "unknown",
                "who_reached": "unknown",
                "evidence_quote": "",
                "confidence": 0.1,
                "chosen_audio_id": None,
                "chosen_started": None,
                "chosen_reason": "empty",
                "_filtered": True,
                "input_index": idx,
                "num_calls_in_group": len(calls),
                "latest_started": latest_started,
                "selected_call_started": None,
                "truncated_chars": 0,
                "model": MODEL,
                "run_ts": datetime.now(timezone.utc).isoformat(),
            }
            try:
                with open(cache_file, "w", encoding="utf-8") as cf:
                    json.dump(data, cf, ensure_ascii=False)
            except Exception as _e:
                if DEBUG:
                    print("cache_write_error:", cache_file, str(_e))
                raise
            data["_cache_hit"] = False
            if DEBUG:
                try:
                    with open(cache_file + ".touch", "w", encoding="utf-8") as tf:
                        tf.write("1")
                    print("write_cache:", cache_file)
                except Exception as _e:
                    print("cache_write_error:", cache_file, str(_e))
            return idx, data

        # QC short transcripts
        full_txt = str(chosen.get("transcript_text") or "")
        if len(full_txt) < QC_MIN_CHARS:
            out = {
                "phone": phone,
                "campaign_name": campaign,
                "outcome_free_text": "unknown",
                "reason_free_text": "unknown",
                "who_reached": "unknown",
                "evidence_quote": "",
                "confidence": 0.15,
                "chosen_audio_id": chosen.get("audio_id"),
                "chosen_started": chosen.get("started"),
                "chosen_reason": chosen.get("_selected_reason"),
                "_filtered": True,
                "input_index": idx,
                "num_calls_in_group": len(calls),
                "latest_started": latest_started,
                "selected_call_started": chosen.get("started"),
                "truncated_chars": truncated_chars,
                "model": MODEL,
                "run_ts": datetime.now(timezone.utc).isoformat(),
            }
            with open(cache_file, "w", encoding="utf-8") as cf:
                json.dump(out, cf, ensure_ascii=False)
            out["_cache_hit"] = False
            if DEBUG:
                try:
                    with open(cache_file + ".touch", "w", encoding="utf-8") as tf:
                        tf.write("1")
                    print("write_cache:", cache_file)
                except Exception as _e:
                    print("cache_write_error:", cache_file, str(_e))
            return idx, out

        result = _call_llm(ctx)
        out = {
            "phone": phone,
            "campaign_name": campaign,
            **result,
            "chosen_audio_id": chosen.get("audio_id"),
            "chosen_started": chosen.get("started"),
            "chosen_reason": chosen.get("_selected_reason"),
            "_filtered": False,
            "input_index": idx,
            "num_calls_in_group": len(calls),
            "latest_started": latest_started,
            "selected_call_started": chosen.get("started"),
            "truncated_chars": truncated_chars,
            "model": MODEL,
            "run_ts": datetime.now(timezone.utc).isoformat(),
        }
        # Safety nets: trim labels and validate evidence substring
        def _limit_words(text: str, max_words: int) -> str:
            parts = [t for t in (text or "").split() if t]
            if len(parts) <= max_words:
                return " ".join(parts)
            return " ".join(parts[:max_words])

        out["outcome_free_text"] = _limit_words(str(out.get("outcome_free_text") or ""), 6)
        out["reason_free_text"] = _limit_words(str(out.get("reason_free_text") or ""), 10)

        full_txt = str(chosen.get("transcript_text") or "")
        ev = str(out.get("evidence_quote") or "").strip()
        if ev and (ev not in full_txt):
            # lower confidence and tag mismatch
            try:
                conf = float(out.get("confidence", 0.3))
            except Exception:
                conf = 0.3
            out["confidence"] = min(conf, 0.5)
            out["_evidence_mismatch"] = 1
        else:
            out["_evidence_mismatch"] = 0
        try:
            with open(cache_file, "w", encoding="utf-8") as cf:
                json.dump(out, cf, ensure_ascii=False)
        except Exception as _e:
            if DEBUG:
                print("cache_write_error:", cache_file, str(_e))
            raise
        try:
            with open(cache_file, "w", encoding="utf-8") as cf:
                json.dump(out, cf, ensure_ascii=False)
        except Exception as _e:
            if DEBUG:
                print("cache_write_error:", cache_file, str(_e))
            raise
        out["_cache_hit"] = False
        if DEBUG:
            try:
                with open(cache_file + ".touch", "w", encoding="utf-8") as tf:
                    tf.write("1")
                print("write_cache:", cache_file)
            except Exception as _e:
                print("cache_write_error:", cache_file, str(_e))
        # small politeness pause when not cache
        time.sleep(0.05)
        return idx, out

    # Deterministic order by input index + counters
    results_indexed: List[Tuple[int, Dict[str, Any]]] = []
    errors = 0
    with ThreadPoolExecutor(max_workers=max(1, MAX_WORKERS)) as ex:
        futs = [ex.submit(process_one, (i, g)) for i, g in enumerate(groups)]
        for fut in as_completed(futs):
            try:
                results_indexed.append(fut.result())
            except Exception as e:
                errors += 1
                if DEBUG:
                    import traceback
                    print("worker_error:", repr(e))
                    traceback.print_exc()

    results_indexed.sort(key=lambda t: t[0])

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for _i, row in results_indexed:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Summary counters
    total = len(groups)
    cache_hits = sum(1 for _i, r in results_indexed if r.get("_cache_hit"))
    filtered_short = sum(1 for _i, r in results_indexed if r.get("_filtered"))
    retries = sum(1 for _i, r in results_indexed if r.get("_retried"))
    parse_fallbacks = sum(1 for _i, r in results_indexed if r.get("_parse_fallback"))
    ev_mismatch = sum(1 for _i, r in results_indexed if r.get("_evidence_mismatch"))
    unknown_cnt = sum(1 for _i, r in results_indexed if (r.get("reason_free_text") or "").strip().lower()=="unknown")

    print(
        f"Processed={total} cache_hits={cache_hits} retries={retries} "
        f"parse_fallbacks={parse_fallbacks} filtered_short={filtered_short} "
        f"evidence_mismatch={ev_mismatch} errors={errors} -> {OUT_PATH} (model={MODEL}, workers={MAX_WORKERS}, cache_dir={CACHE_DIR})"
    )

    # One-line summary echo (date/time, source, model, rows, unknown %, mismatches, knobs, prompt)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    base = os.path.basename(OUT_PATH)
    line = (
        f"{ts} | {base} | model={MODEL} | rows={total} | unknown={unknown_cnt} "
        f"({unknown_cnt/max(1,total):.1%}) | evidence_mismatch={ev_mismatch} | "
        f"workers={MAX_WORKERS} | min_chars={MIN_CHARS}/{QC_MIN_CHARS} | trunc={HEAD_CHARS}+{TAIL_CHARS} | "
        f"prompt_ver={prompt_version}"
    )
    print(line)


if __name__ == "__main__":
    main()


