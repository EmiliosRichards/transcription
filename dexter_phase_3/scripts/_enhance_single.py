"""Run LLM enhancement on a single phone number from a run."""
import csv
import json
import os
import sys
import textwrap
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Import helpers from 04b
sys.path.insert(0, str(ROOT / "scripts"))
from scripts_04b_helper import build_transcript_summary, build_available_fields

import yaml

def main():
    phone = sys.argv[1] if len(sys.argv) > 1 else "+49718187014"
    run_name = sys.argv[2] if len(sys.argv) > 2 else "runs/sample_20_v2"
    run_dir = ROOT / run_name

    with open(ROOT / "config" / "config.yml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    model = cfg.get("model", "gpt-5.4-mini-2026-03-17")

    with open(ROOT / "prompts" / "enhance_pitch.txt", encoding="utf-8") as f:
        prompt_template = f.read()

    # Load journey
    journey = None
    with open(run_dir / "journeys.jsonl", encoding="utf-8") as f:
        for line in f:
            j = json.loads(line)
            if j["phone"] == phone:
                journey = j
                break

    # Load pitch row
    row = None
    with open(run_dir / "pitches.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["phone"] == phone:
                row = r
                break

    if not row or not journey:
        print(f"Phone {phone} not found")
        return

    pitch = row.get("pitch_text", "")
    followup = row.get("generic_followup", "")

    print("=" * 80)
    print(f"ENHANCING: {phone}")
    print(f"Firma: {row.get('firma', '')}")
    print(f"Category: {row.get('category_id', '')} - {row.get('category_label', '')}")
    print("=" * 80)

    # Show transcript summary
    calls = journey.get("calls", [])
    calls.sort(key=lambda c: c.get("started") or "")
    print(f"\nCALL HISTORY ({len(calls)} calls):")
    for i, call in enumerate(calls, 1):
        txt = (call.get("transcript_text") or "").strip()
        date = str(call.get("started", ""))[:10]
        if txt and len(txt) > 30:
            print(f"\n  --- Call {i} ({date}) ---")
            print(f"  {txt[:200]}{'...' if len(txt) > 200 else ''}")

    # Build the LLM input
    transcript_summary = ""
    sorted_calls = sorted(calls, key=lambda c: c.get("started") or "")
    word_count = 0
    parts = []
    for call in sorted_calls:
        txt = (call.get("transcript_text") or "").strip()
        if not txt or len(txt) < 30:
            continue
        date = str(call.get("started", ""))[:10]
        words = len(txt.split())
        if word_count + words > 1500:
            break
        parts.append(f"[{date}] {txt}")
        word_count += words
    transcript_summary = "\n\n".join(parts)

    # Build available fields
    fields = []
    def add(label, value):
        if value and value.strip() and value.strip().lower() not in ("", "null", "none", "unbekannt"):
            fields.append(f"- {label}: {value}")
        else:
            fields.append(f"- {label}: (nicht verfuegbar)")

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
    available_fields = "\n".join(fields)

    system_prompt = prompt_template.replace("{available_fields}", available_fields)

    user_msg = f"""## Template Pitch

{pitch}

## Generic Follow-up (falls vorhanden)

{followup or '(keine)'}

## Call History

{transcript_summary}"""

    print(f"\n{'=' * 80}")
    print("TEMPLATE PITCH:")
    print("-" * 40)
    for line in textwrap.wrap(pitch, 85):
        print(f"  {line}")

    if followup:
        print(f"\nGENERIC FOLLOW-UP:")
        print("-" * 40)
        print(f"  {followup}")

    print(f"\n{'=' * 80}")
    print(f"Calling {model}...")
    print()

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
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
    usage = response.usage

    print("LLM RESPONSE:")
    print("-" * 40)
    print(f"  enhanced: {result.get('enhanced')}")
    print(f"  changes:  {result.get('changes_made', '')}")
    print()

    print("ENHANCED PITCH:")
    print("-" * 40)
    for line in textwrap.wrap(result.get("pitch_text", ""), 85):
        print(f"  {line}")

    ef = result.get("enhanced_followup", "")
    if ef:
        print(f"\nENHANCED FOLLOW-UP:")
        print("-" * 40)
        print(f"  {ef}")

    print(f"\nTokens: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}")


if __name__ == "__main__":
    main()
