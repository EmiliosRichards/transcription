"""
02_classify.py
Classify each journey into a fixed taxonomy category using an LLM.

Usage:
    python scripts/02_classify.py --run runs/test_run
    python scripts/02_classify.py --run runs/test_run --max-journeys 5
"""

import argparse
import csv
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _clean_name(raw: str | None) -> str:
    """Clean up a person name extracted from ASR transcripts.
    Handles common garbling, normalises 'Herr/Frau' prefix, title-cases."""
    if not raw or raw.lower() in ("null", "none", "unbekannt", "n/a", ""):
        return ""
    name = raw.strip()
    # Remove stray punctuation from ASR
    name = re.sub(r"[.,:;!?]+$", "", name)
    # Normalise title case (ASR sometimes gives ALL CAPS or lowercase)
    parts = name.split()
    cleaned = []
    for p in parts:
        if p.lower() in ("herr", "frau", "dr", "dr.", "prof", "prof."):
            cleaned.append(p.capitalize())
        else:
            # Title-case but keep short prepositions lowercase
            if p.lower() in ("von", "van", "de", "zu", "am", "im"):
                cleaned.append(p.lower())
            else:
                cleaned.append(p.capitalize() if p == p.lower() or p == p.upper() else p)
    return " ".join(cleaned)


def load_config() -> dict:
    with open(ROOT / "config" / "config.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_taxonomy() -> dict:
    with open(ROOT / "config" / "taxonomy.json", encoding="utf-8") as f:
        return json.load(f)


def load_prompt_template() -> str:
    with open(ROOT / "prompts" / "classify_journey.txt", encoding="utf-8") as f:
        return f.read()


def format_categories_for_prompt(categories: list[dict]) -> str:
    lines = []
    for cat in categories:
        quotes = cat.get("quotes", [])
        quotes_str = " | ".join(f'"{q}"' for q in quotes) if quotes else ""
        lines.append(f'- **{cat["id"]}: {cat["label"]}**')
        if quotes_str:
            lines.append(f'  Typische Aussagen: {quotes_str}')
    return "\n".join(lines)


def build_system_prompt(taxonomy: dict, template: str) -> str:
    gk_text = format_categories_for_prompt(taxonomy["gatekeeper"])
    dm_text = format_categories_for_prompt(taxonomy["decision_maker"])
    return template.replace("{gk_categories}", gk_text).replace("{dm_categories}", dm_text)


def build_journey_context(journey: dict, max_words: int) -> str:
    """Build transcript context from journey calls.
    Selects most recent calls first (to prioritize them if we hit the word cap),
    then presents them in CHRONOLOGICAL order so the LLM reads oldest→newest
    and the most recent call is freshest in its attention."""
    calls = journey["calls"]
    if not calls:
        return ""

    # Select calls starting from most recent (priority for inclusion)
    sorted_by_recency = sorted(calls, key=lambda c: c.get("started") or "", reverse=True)

    selected = []
    word_count = 0
    for call in sorted_by_recency:
        text = (call.get("transcript_text") or "").strip()
        if not text or len(text) < 30:
            continue
        call_words = len(text.split())
        if word_count + call_words > max_words:
            break
        selected.append(call)
        word_count += call_words

    # Now reverse to chronological order (oldest first, newest last)
    selected.sort(key=lambda c: c.get("started") or "")

    parts = []
    for i, call in enumerate(selected):
        text = (call.get("transcript_text") or "").strip()
        date_str = call.get("started", "unbekannt")
        if date_str and "T" in str(date_str):
            date_str = str(date_str).split("T")[0]
        parts.append(f"--- Anruf {i + 1} von {len(selected)} (Datum: {date_str}) ---\n{text}")

    return "\n\n".join(parts)


def is_unreachable(context: str, markers: list[str]) -> bool:
    """Check if the context indicates only voicemail/unreachable."""
    if not context.strip():
        return True
    low = context.lower()
    # If the entire transcript is very short AND matches a marker
    if len(context.split()) < 15:
        return any(m in low for m in markers)
    return False


def _journey_metadata(journey: dict) -> dict:
    """Extract contact metadata fields from journey (populated by Dialfire enrichment)."""
    return {
        "firma": journey.get("firma", ""),
        "plz": journey.get("plz", ""),
        "ort": journey.get("ort", ""),
        "ap_vorname": journey.get("ap_vorname", ""),
        "ap_nachname": journey.get("ap_nachname", ""),
        "dialfire_contact_id": journey.get("dialfire_contact_id", ""),
        "dialfire_status": journey.get("dialfire_status", ""),
        "dialfire_status_detail": journey.get("dialfire_status_detail", ""),
    }


def classify_single(
    journey: dict,
    client: OpenAI,
    system_prompt: str,
    cfg: dict,
    index: int,
) -> dict:
    """Classify a single journey. Returns classification dict."""

    phone = journey["phone"]
    max_words = cfg.get("max_context_words", 3000)
    markers = cfg.get("unreachable_markers", [])
    min_chars = cfg.get("min_transcript_chars", 100)
    meta = _journey_metadata(journey)

    context = build_journey_context(journey, max_words)

    # Handle unreachable / empty transcripts
    if is_unreachable(context, markers) or len(context) < min_chars:
        return {
            "input_index": index,
            "phone": phone,
            "campaign_name": journey.get("campaign_name", ""),
            "num_calls": journey["num_calls"],
            "role": "UNKNOWN",
            "category_id": "NONE",
            "category_label": "Nicht erreichbar",
            "confidence": 1.0,
            "evidence_quote": "",
            "reason_summary": "Kontakt nicht erreichbar",
            "system_in_use": "unbekannt",
            "contact_person_name": None,
            "last_call_date": _last_call_date(journey),
            "_shortcut": "unreachable",
            "usage_prompt_tokens": 0,
            "usage_completion_tokens": 0,
            **meta,
        }

    # Call LLM
    user_msg = f"Kontakt: {phone}\nAnzahl Anrufe: {journey['num_calls']}\n\n{context}"

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=cfg.get("model", "gpt-4o-mini"),
                temperature=cfg.get("temperature", 0.0),
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
            )
            raw = response.choices[0].message.content
            result = json.loads(raw)

            # Validate evidence quote
            evidence = result.get("evidence_quote", "")
            evidence_mismatch = 0
            if evidence and evidence not in context:
                evidence_mismatch = 1
                result["confidence"] = min(result.get("confidence", 0.5), 0.5)

            usage = response.usage

            # Resolve best contact name: LLM extraction > Dialfire AP fields
            contact_name = _clean_name(result.get("contact_person_name"))
            contact_role = result.get("contact_person_role") or ""
            gk_name = _clean_name(result.get("gatekeeper_name"))
            # Fallback: use Dialfire AP fields if LLM didn't find a name
            if not contact_name and (meta.get("ap_vorname") or meta.get("ap_nachname")):
                parts = [meta.get("ap_vorname", ""), meta.get("ap_nachname", "")]
                contact_name = " ".join(p for p in parts if p).strip()

            return {
                "input_index": index,
                "phone": phone,
                "campaign_name": journey.get("campaign_name", ""),
                "num_calls": journey["num_calls"],
                "role": result.get("role", "UNKNOWN"),
                "category_id": result.get("category_id", "NONE"),
                "category_label": result.get("category_label", ""),
                "confidence": result.get("confidence", 0.0),
                "evidence_quote": evidence,
                "reason_summary": result.get("reason_summary", ""),
                "system_in_use": result.get("system_in_use", "unbekannt"),
                "contact_person_name": contact_name,
                "contact_person_role": contact_role,
                "gatekeeper_name": gk_name,
                "last_call_date": result.get("last_call_date") or _last_call_date(journey),
                "do_not_call": result.get("do_not_call", False),
                "do_not_call_evidence": result.get("do_not_call_evidence", ""),
                "_evidence_mismatch": evidence_mismatch,
                "_shortcut": None,
                "usage_prompt_tokens": usage.prompt_tokens if usage else 0,
                "usage_completion_tokens": usage.completion_tokens if usage else 0,
                **meta,
            }

        except json.JSONDecodeError:
            if attempt < 2:
                time.sleep(1)
                continue
            return _error_result(index, journey, "JSON parse error")
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            return _error_result(index, journey, str(e))

    return _error_result(index, journey, "max retries")


def _last_call_date(journey: dict) -> str | None:
    calls = journey.get("calls", [])
    if not calls:
        return None
    dates = [c.get("started") for c in calls if c.get("started")]
    if not dates:
        return None
    latest = max(dates)
    if "T" in str(latest):
        return str(latest).split("T")[0]
    return str(latest)


def _error_result(index: int, journey: dict, error: str) -> dict:
    return {
        "input_index": index,
        "phone": journey["phone"],
        "campaign_name": journey.get("campaign_name", ""),
        "num_calls": journey["num_calls"],
        "role": "UNKNOWN",
        "category_id": "ERROR",
        "category_label": f"Error: {error}",
        "confidence": 0.0,
        "evidence_quote": "",
        "reason_summary": "",
        "system_in_use": "unbekannt",
        "contact_person_name": None,
        "last_call_date": _last_call_date(journey),
        "_shortcut": "error",
        "_error": error,
        "usage_prompt_tokens": 0,
        "usage_completion_tokens": 0,
        **_journey_metadata(journey),
    }


def main():
    parser = argparse.ArgumentParser(description="Classify Dexter journeys")
    parser.add_argument("--run", type=Path, required=True, help="Run directory")
    parser.add_argument("--max-journeys", type=int, default=None)
    args = parser.parse_args()

    cfg = load_config()
    taxonomy = load_taxonomy()
    template = load_prompt_template()
    system_prompt = build_system_prompt(taxonomy, template)

    run_dir = ROOT / args.run if not args.run.is_absolute() else args.run
    journeys_path = run_dir / "journeys.jsonl"
    if not journeys_path.exists():
        print(f"ERROR: {journeys_path} not found. Run 01_export_journeys.py first.")
        return

    # Load journeys
    journeys = []
    with open(journeys_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                journeys.append(json.loads(line))

    if args.max_journeys:
        journeys = journeys[:args.max_journeys]
    print(f"Classifying {len(journeys)} journeys with {cfg.get('model', 'gpt-4o-mini')}...")

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    workers = cfg.get("workers", 4)
    results = [None] * len(journeys)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(classify_single, j, client, system_prompt, cfg, i): i
            for i, j in enumerate(journeys)
        }
        done = 0
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()
            done += 1
            if done % 50 == 0 or done == len(journeys):
                print(f"  {done}/{len(journeys)} classified")

    # Write outputs
    # JSONL
    jsonl_path = run_dir / "classifications.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # CSV
    csv_path = run_dir / "classifications.csv"
    fieldnames = [
        "input_index", "phone", "campaign_name", "num_calls",
        "role", "category_id", "category_label", "confidence",
        "evidence_quote", "reason_summary", "system_in_use",
        "contact_person_name", "contact_person_role", "gatekeeper_name",
        "last_call_date", "do_not_call", "do_not_call_evidence",
        "firma", "plz", "ort", "ap_vorname", "ap_nachname",
        "dialfire_contact_id", "dialfire_status", "dialfire_status_detail",
        "_evidence_mismatch", "_shortcut",
        "usage_prompt_tokens", "usage_completion_tokens",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    # Summary
    roles = {}
    categories = {}
    shortcuts = 0
    errors = 0
    total_prompt = 0
    total_completion = 0
    for r in results:
        roles[r["role"]] = roles.get(r["role"], 0) + 1
        cat = f"{r['category_id']}: {r['category_label']}"
        categories[cat] = categories.get(cat, 0) + 1
        if r.get("_shortcut"):
            shortcuts += 1
        if r.get("category_id") == "ERROR":
            errors += 1
        total_prompt += r.get("usage_prompt_tokens", 0)
        total_completion += r.get("usage_completion_tokens", 0)

    summary = {
        "total": len(results),
        "roles": roles,
        "shortcuts": shortcuts,
        "errors": errors,
        "top_categories": sorted(categories.items(), key=lambda x: -x[1])[:15],
        "token_usage": {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
        },
    }
    summary_path = run_dir / "classification_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\nDone! {len(results)} classified -> {csv_path}")
    print(f"Roles: {roles}")
    print(f"Shortcuts (unreachable): {shortcuts}, Errors: {errors}")
    print(f"Tokens: {total_prompt + total_completion:,} total")


if __name__ == "__main__":
    main()
