import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
except Exception:
    def load_dotenv(*args: Any, **kwargs: Any) -> None:  # no-op if dotenv not installed
        return None
    def find_dotenv(*args: Any, **kwargs: Any) -> str:
        return ""

try:
    from openai import OpenAI  # type: ignore
except Exception as e:  # pragma: no cover
    OpenAI = None  # type: ignore


@dataclass
class Args:
    run: Path
    input_path: Path
    out_path: Path
    model: str
    workers: int
    max_retries: int
    timeout_s: float
    temperature: Optional[float]


SYSTEM_PROMPT = (
    "You will receive a cluster summary with short English reasons and German snippets.\n"
    "Propose concise English label candidates and a one-sentence definition, then pick 2–3 provided German quotes.\n"
    "Rules:\n"
    "- Return valid JSON ONLY with exactly these keys: label_candidates, definition, example_quotes.\n"
    "- label_candidates: array of 3 short English options (each ≤ 3 words).\n"
    "- definition: one sentence (English) defining the cluster’s core reason.\n"
    "- example_quotes: array with 2–3 items; each must be a verbatim quote from the provided snippets (do not invent).\n"
)


def build_user_prompt(summary: Dict[str, Any]) -> str:
    label = summary.get("reason_label") or summary.get("label") or ""
    examples = summary.get("examples") or []
    # Prefer German evidence quotes; fall back to reason_free_text if missing
    snippets: list[str] = []
    for ex in examples:
        q = ex.get("evidence_quote") or ""
        if q:
            snippets.append(q)
    if not snippets:
        # fallback: include reason_free_text (may be English), still useful context
        for ex in examples:
            rft = ex.get("reason_free_text") or ""
            if rft:
                snippets.append(rft)

    # Truncate to keep tokens reasonable
    snippets = snippets[:12]

    lines = [
        f"Existing label (context only): {label}",
        "Snippets (use 2–3 for example_quotes; must be verbatim):",
    ]
    for i, s in enumerate(snippets, 1):
        s_trim = s.strip().replace("\n", " ")
        lines.append(f"- {s_trim}")
    lines.append(
        "Return JSON with keys: label_candidates, definition, example_quotes. No extra text."
    )
    return "\n".join(lines)


def parse_json_strict(text: str) -> Dict[str, Any]:
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError("Response must be a JSON object")
    # enforce required keys
    for k in ("label_candidates", "definition", "example_quotes"):
        if k not in obj:
            raise ValueError(f"Missing key: {k}")
    # normalize types
    if not isinstance(obj["label_candidates"], list):
        raise ValueError("label_candidates must be a list")
    if not isinstance(obj["definition"], str):
        raise ValueError("definition must be a string")
    if not isinstance(obj["example_quotes"], list):
        raise ValueError("example_quotes must be a list")
    # length constraints
    obj["label_candidates"] = [str(x).strip()[:50] for x in obj["label_candidates"]][:3]
    obj["example_quotes"] = [str(x).strip() for x in obj["example_quotes"]][:3]
    return obj


def call_llm(client: Any, model: str, system_prompt: str, user_prompt: str, timeout_s: float, temperature: Optional[float]) -> str:
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    # openai-python v1 client supports per-request timeout via client config; here we rely on env or default
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or "{}"


def backoff_delays(max_retries: int) -> Iterable[float]:
    base = 0.5
    for i in range(max_retries):
        yield base * (2 ** i)


def process_one(client: Any, model: str, summary: Dict[str, Any], timeout_s: float, temperature: Optional[float]) -> Dict[str, Any]:
    user_prompt = build_user_prompt(summary)
    last_err: Optional[Exception] = None
    for attempt, delay in enumerate(backoff_delays(3), start=1):
        try:
            content = call_llm(client, model, SYSTEM_PROMPT, user_prompt, timeout_s, temperature)
            obj = parse_json_strict(content)
            return obj
        except Exception as e:
            last_err = e
            time.sleep(delay)
            # second try with explicit JSON reminder
            try:
                content = call_llm(
                    client,
                    model,
                    SYSTEM_PROMPT,
                    user_prompt + "\n\nYou must return valid JSON only.",
                    timeout_s,
                    temperature,
                )
                obj = parse_json_strict(content)
                return obj
            except Exception as e2:
                last_err = e2
                time.sleep(delay)
                continue
    # final fallback: minimal structure
    if last_err:
        # include short fallback to keep pipeline moving
        return {
            "label_candidates": [str(summary.get("reason_label", "unknown"))[:30] or "unknown"],
            "definition": "Cluster of similar reasons extracted from calls.",
            "example_quotes": [],
            "_error": str(last_err),
        }
    return {
        "label_candidates": [str(summary.get("reason_label", "unknown"))[:30] or "unknown"],
        "definition": "Cluster of similar reasons extracted from calls.",
        "example_quotes": [],
    }


def load_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def write_jsonl(path: Path, items: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as g:
        for item in items:
            g.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    load_dotenv(find_dotenv())

    parser = argparse.ArgumentParser(description="Name clusters by proposing label candidates and definitions with LLM")
    parser.add_argument("--run", required=True, help="Run directory (contains reports/cluster_summaries.jsonl)")
    parser.add_argument("--input", default="reports/cluster_summaries.jsonl", help="Relative input JSONL path under run dir")
    parser.add_argument("--out", default="taxonomy/cluster_label_candidates.jsonl", help="Relative output JSONL path under run dir")
    parser.add_argument("--model", default=os.environ.get("NAME_MODEL", "gpt-4o-mini"), help="LLM model name")
    parser.add_argument("--workers", type=int, default=int(os.environ.get("NAME_WORKERS", "4")))
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("NAME_TIMEOUT", "60")))
    parser.add_argument("--temperature", type=float, default=None)
    args_ns = parser.parse_args()

    args = Args(
        run=Path(args_ns.run),
        input_path=Path(args_ns.run) / args_ns.input,
        out_path=Path(args_ns.run) / args_ns.out,
        model=args_ns.model,
        workers=args_ns.workers,
        max_retries=args_ns.max_retries,
        timeout_s=args_ns.timeout,
        temperature=args_ns.temperature if os.environ.get("NAME_TEMPERATURE") is not None else None,
    )

    if OpenAI is None:
        raise RuntimeError("openai package not installed. pip install openai>=1.0.0")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    client = OpenAI(api_key=api_key)

    summaries = list(load_jsonl(args.input_path))
    out_items: list[Dict[str, Any]] = []

    def task(idx: int, s: Dict[str, Any]) -> Dict[str, Any]:
        res = process_one(client, args.model, s, args.timeout_s, args.temperature)
        # pass-through identifiers if present
        if "cluster_id" in s:
            res["cluster_id"] = s["cluster_id"]
        if "reason_label" in s:
            res["source_reason_label"] = s["reason_label"]
        res["_input_index"] = idx
        return res

    if args.workers <= 1:
        for i, s in enumerate(summaries):
            out_items.append(task(i, s))
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(task, i, s): i for i, s in enumerate(summaries)}
            for fut in as_completed(futs):
                out_items.append(fut.result())

    # deterministic order by _input_index
    out_items.sort(key=lambda x: x.get("_input_index", 0))
    write_jsonl(args.out_path, out_items)
    print(f"Wrote {len(out_items)} -> {args.out_path}")


if __name__ == "__main__":
    main()


