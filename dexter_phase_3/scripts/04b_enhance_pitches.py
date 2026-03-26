"""
04b_enhance_pitches.py
OPTIONAL step: Use an LLM to lightly personalise pitches based on call history.
Takes the template-filled pitch from 04 and enhances it with transcript context.

Usage:
    python scripts/04b_enhance_pitches.py --run runs/test_run
    python scripts/04b_enhance_pitches.py --run runs/test_run --max 10  # test on 10
"""

import argparse
import csv
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def load_config() -> dict:
    with open(ROOT / "config" / "config.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_journeys(run_dir: Path) -> dict:
    """Load journeys keyed by phone for transcript access."""
    journeys = {}
    jpath = run_dir / "journeys.jsonl"
    if not jpath.exists():
        return journeys
    with open(jpath, encoding="utf-8") as f:
        for line in f:
            j = json.loads(line)
            journeys[j["phone"]] = j
    return journeys


def build_transcript_summary(journey: dict, max_words: int = 1500) -> str:
    """Build a condensed transcript summary, chronological (oldest first)."""
    calls = journey.get("calls", [])
    if not calls:
        return ""

    sorted_calls = sorted(calls, key=lambda c: c.get("started") or "")
    parts = []
    word_count = 0

    for call in sorted_calls:
        text = (call.get("transcript_text") or "").strip()
        if not text or len(text) < 30:
            continue
        date = str(call.get("started", ""))[:10]
        words = len(text.split())
        if word_count + words > max_words:
            break
        parts.append(f"[{date}] {text}")
        word_count += words

    return "\n\n".join(parts)


def build_available_fields(row: dict) -> str:
    """List what data we actually have for this contact."""
    fields = []

    def add(label, value):
        if value and value.strip() and value.strip().lower() not in ("", "null", "none", "unbekannt"):
            fields.append(f"- {label}: {value}")
        else:
            fields.append(f"- {label}: (nicht verfügbar)")

    add("Datum des letzten Anrufs", row.get("last_call_date", ""))
    add("Firma/Einrichtung", row.get("firma", ""))
    add("Ort", row.get("ort", ""))
    add("Ansprechpartner Name", row.get("contact_person_name", ""))
    add("Ansprechpartner Rolle", row.get("contact_person_role", ""))
    add("Gatekeeper Name", row.get("gatekeeper_name", ""))
    add("Genutztes System", row.get("system_in_use", ""))
    add("Referenz-Einrichtung", row.get("ref_einrichtung", ""))
    add("Referenz-Ort", row.get("ref_ort", ""))
    add("Grund der Ablehnung", row.get("reason_summary", ""))
    add("Kategorie", row.get("category_label", ""))
    add("Rolle (GK/DM)", row.get("role", ""))

    return "\n".join(fields)


def enhance_single(
    row: dict,
    journey: dict | None,
    prompt_template: str,
    client: OpenAI,
    model: str,
) -> dict:
    """Enhance a single pitch. Returns the row with pitch_text_enhanced added."""
    pitch = row.get("pitch_text", "")
    if not pitch or row.get("action") in ("exclude", "raus"):
        row["pitch_text_enhanced"] = ""
        row["enhanced_followup"] = ""
        return row

    transcript_summary = build_transcript_summary(journey) if journey else ""
    if not transcript_summary:
        row["pitch_text_enhanced"] = ""
        row["enhanced_followup"] = ""
        return row

    available_fields = build_available_fields(row)
    system_prompt = prompt_template.replace("{available_fields}", available_fields)

    user_msg = f"""## Template Pitch

{pitch}

## Generic Follow-up (falls vorhanden)

{row.get('generic_followup', '(keine)')}

## Call History

{transcript_summary}"""

    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.3,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
        )
        result = json.loads(response.choices[0].message.content)

        if result.get("enhanced"):
            row["pitch_text_enhanced"] = result.get("pitch_text", "")
            row["enhanced_followup"] = result.get("enhanced_followup", "")
        else:
            row["pitch_text_enhanced"] = ""
            row["enhanced_followup"] = ""

    except Exception as e:
        print(f"  ERROR enhancing {row.get('phone', '?')}: {e}")
        row["pitch_text_enhanced"] = ""
        row["enhanced_followup"] = ""

    return row


def main():
    parser = argparse.ArgumentParser(description="LLM-enhance pitches (optional step)")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--max", type=int, default=0, help="Max contacts to enhance (0=all)")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    cfg = load_config()
    model = cfg.get("model", "gpt-5.4-mini-2026-03-17")
    run_dir = ROOT / args.run if not args.run.is_absolute() else args.run

    # Load prompt
    with open(ROOT / "prompts" / "enhance_pitch.txt", encoding="utf-8") as f:
        prompt_template = f.read()

    # Load pitches (output of step 04)
    input_path = run_dir / "pitches.csv"
    if not input_path.exists():
        print(f"ERROR: {input_path} not found. Run 04_generate_pitches.py first.")
        return

    with open(input_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Load journeys for transcript access
    print("Loading journeys for transcript context...")
    journeys = load_journeys(run_dir)
    print(f"  {len(journeys)} journeys loaded")

    # Filter to rows that have pitches
    to_enhance = [r for r in rows if r.get("pitch_text") and r.get("action") not in ("exclude", "raus")]
    skip = [r for r in rows if r not in to_enhance]

    not_enhanced = []
    if args.max and args.max < len(to_enhance):
        not_enhanced = to_enhance[args.max:]
        to_enhance = to_enhance[:args.max]

    print(f"Enhancing {len(to_enhance)} pitches (skipping {len(skip)} excluded/empty, {len(not_enhanced)} passed through)...")

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    enhanced_count = 0
    unchanged_count = 0

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for row in to_enhance:
            phone = row.get("phone", "")
            journey = journeys.get(phone)
            future = executor.submit(
                enhance_single, row, journey, prompt_template, client, model,
            )
            futures[future] = phone

        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if result.get("pitch_text_enhanced"):
                enhanced_count += 1
            else:
                unchanged_count += 1

            done = enhanced_count + unchanged_count
            if done % 25 == 0:
                print(f"  {done}/{len(to_enhance)} done ({enhanced_count} enhanced, {unchanged_count} unchanged)")

    # Add back skipped rows and unprocessed rows
    for row in skip:
        row["pitch_text_enhanced"] = ""
        row["enhanced_followup"] = ""
        results.append(row)
    for row in not_enhanced:
        row["pitch_text_enhanced"] = ""
        row["enhanced_followup"] = ""
        results.append(row)

    # Sort back to original order (by phone)
    phone_order = {r.get("phone"): i for i, r in enumerate(rows)}
    results.sort(key=lambda r: phone_order.get(r.get("phone"), 99999))

    # Write output
    out_path = run_dir / "pitches_enhanced.csv"
    fieldnames = list(results[0].keys()) if results else []
    if "pitch_text_enhanced" not in fieldnames:
        fieldnames.append("pitch_text_enhanced")

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nDone: {enhanced_count} enhanced, {unchanged_count} unchanged -> {out_path}")


if __name__ == "__main__":
    main()
