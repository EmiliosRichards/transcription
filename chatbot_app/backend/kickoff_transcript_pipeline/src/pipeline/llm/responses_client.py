import os
from typing import Dict, Any, List, Optional
import logging
import time
import sys
import json
from pathlib import Path
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam


logger = logging.getLogger("pipeline.llm")

def _dbg_enabled() -> bool:
    v = os.environ.get("LLM_DEBUG", "1").strip().lower()
    return v in ("1", "true", "yes", "on")

def _snapshot_enabled() -> tuple[bool, str | None]:
    path = os.environ.get("LLM_SNAPSHOT_DIR")
    if path:
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            return True, path
        except Exception:
            return False, None
    return False, None

def _ensure_debug_logger() -> None:
    if not _dbg_enabled():
        return
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("[llm] %(message)s"))
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False


def fuse_block_via_llm(aligned_payload: Dict[str, Any], prompt_md: str, model: str, temperature: Optional[float]) -> Dict[str, str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)

    system = (
        "You are a careful transcript fusion assistant. Use only provided inputs. "
        "If inputs are missing/invalid, answer with a JSON error: {\"error\":\"fail_closed\",\"reason\":\"...\"}."
    )

    user_content = (
        prompt_md
        + "\n\nAligned input (JSON):\n"
        + str(aligned_payload)
        + "\n\nReturn strict JSON with keys: master_block, qa_block, outline_hint."
    )

    messages: List[ChatCompletionMessageParam] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    _ensure_debug_logger()
    t0 = time.time()
    fallback_used = False
    if _dbg_enabled():
        logger.info("fuse request model=%s temp_req=%s", model, temperature)
    snap_ok, snap_dir = _snapshot_enabled()
    try:
        if temperature is None:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
            )
        else:
            completion = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=messages,
            )
    except Exception as e:
        msg = str(e)
        if "temperature" in msg and ("unsupported" in msg or "does not support" in msg):
            fallback_used = True
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
            )
        else:
            raise

    text = completion.choices[0].message.content or "{}"

    # Snapshot request/response (fuse)
    if snap_ok and snap_dir:
        try:
            ts = int(time.time() * 1000)
            Path(snap_dir, f"fuse_{ts}_request.json").write_text(
                json.dumps({"model": model, "temperature": None if fallback_used else temperature, "messages": messages}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            Path(snap_dir, f"fuse_{ts}_response.txt").write_text(text, encoding="utf-8")
        except Exception:
            pass
    if _dbg_enabled():
        used_temp = None if fallback_used else temperature
        usage = getattr(completion, "usage", None)
        usage_info = {
            "prompt": getattr(usage, "prompt_tokens", None),
            "completion": getattr(usage, "completion_tokens", None),
            "total": getattr(usage, "total_tokens", None),
        } if usage else None
        ms = round((time.time() - t0) * 1000)
        looks_json = text.lstrip().startswith("{")
        logger.info(
            "[llm] fuse model=%s temp_used=%s fallback=%s ms=%s usage=%s json_like=%s len=%s",
            model,
            used_temp,
            fallback_used,
            ms,
            usage_info,
            looks_json,
            len(text),
        )
    # Rely on downstream to parse/validate strict JSON
    return {"raw": text}


def cleanup_segments_via_llm(payload: Dict[str, Any], model: str, temperature: Optional[float], system_prompt: str, retry_hint: Optional[str] = None) -> Dict[str, str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)

    seg_count = 0
    try:
        seg_count = int(len(payload.get("segments", [])))
    except Exception:
        seg_count = 0
    messages: List[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                "You will receive:\n"
                "- glossary_static: non-editable reference list of domain terms.\n"
                "- segments: Teams-anchored list [{t_start, speaker, teams_text, candidates:{krisp[], gpt_ref[]}}].\n"
                "- language: ISO code.\n"
                "- meta.prev_tail_context and meta.next_head_context: read-only snippets of surrounding Teams text for context.\n"
                "- context.prev_cleaned_tail: last 1–2 prior segments for continuity (READ-ONLY; do not edit or echo beyond JSON schema).\n"
                f"Return EXACTLY {seg_count} cleaned_segments.\n\n"
                "SEGMENT_COUNT=" + str(seg_count) + "\n\n"
                "Payload JSON follows:\n" + str(payload)
            ),
        },
    ]
    if retry_hint:
        messages.append({"role": "user", "content": retry_hint})

    _ensure_debug_logger()
    t0 = time.time()
    fallback_used = False
    if _dbg_enabled():
        logger.info("cleanup request model=%s temp_req=%s", model, temperature)
    snap_ok, snap_dir = _snapshot_enabled()
    try:
        if temperature is None:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
            )
        else:
            completion = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=messages,
            )
    except Exception as e:
        msg = str(e)
        if "temperature" in msg and ("unsupported" in msg or "does not support" in msg):
            fallback_used = True
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
            )
        else:
            raise
    text = completion.choices[0].message.content or "{}"

    # Snapshot request/response (cleanup)
    if snap_ok and snap_dir:
        try:
            ts = int(time.time() * 1000)
            Path(snap_dir, f"cleanup_{ts}_request.json").write_text(
                json.dumps({"model": model, "temperature": None if fallback_used else temperature, "messages": messages}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            Path(snap_dir, f"cleanup_{ts}_response.txt").write_text(text, encoding="utf-8")
        except Exception:
            pass
    if _dbg_enabled():
        used_temp = None if fallback_used else temperature
        usage = getattr(completion, "usage", None)
        usage_info = {
            "prompt": getattr(usage, "prompt_tokens", None),
            "completion": getattr(usage, "completion_tokens", None),
            "total": getattr(usage, "total_tokens", None),
        } if usage else None
        ms = round((time.time() - t0) * 1000)
        looks_json = text.lstrip().startswith("{")
        logger.info(
            "[llm] cleanup model=%s temp_used=%s fallback=%s ms=%s usage=%s json_like=%s len=%s",
            model,
            used_temp,
            fallback_used,
            ms,
            usage_info,
            looks_json,
            len(text),
        )
    return {"raw": text}