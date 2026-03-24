"""One-off walkthrough script for a single contact to show the full pipeline."""
import csv
import json
import os
import re
import sys
import textwrap
from pathlib import Path

import pgeocode
import yaml
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PHONE = sys.argv[1] if len(sys.argv) > 1 else "+499313503402"

engine = create_engine(os.environ["DATABASE_URL"])

# ── STEP 1: Raw DB ──────────────────────────────────────────────────────
print("=" * 90)
print(f"WALKTHROUGH: {PHONE}")
print("=" * 90)
print()
print("STEP 1: RAW DATABASE RECORDS")
print("-" * 90)

with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT af.id, af.started, af.stopped, t.transcript_text, t.status
        FROM media_pipeline.audio_files af
        LEFT JOIN media_pipeline.transcriptions t ON t.audio_file_id = af.id
        WHERE af.phone = :phone AND af.b2_object_key LIKE 'dexter/audio/%%'
        ORDER BY af.started
    """), {"phone": PHONE}).fetchall()

    print(f"\n{len(rows)} call records:\n")
    for i, r in enumerate(rows, 1):
        date = str(r[1])[:16]
        txt = r[3] or ""
        secs = f"{(r[2] - r[1]).total_seconds():.0f}s" if r[1] and r[2] else "?"
        print(f"  Call {i} | {date} | {secs:>5s} | {len(txt):>5d} chars")

    print(f"\n{'─' * 90}")
    print("FULL TRANSCRIPTS:\n")
    for i, r in enumerate(rows, 1):
        txt = (r[3] or "(empty)").strip()
        print(f"--- Call {i} ({str(r[1])[:10]}) ---")
        for line in textwrap.wrap(txt, 88):
            print(f"  {line}")
        print()

    # Contact data
    print(f"{'─' * 90}")
    print("DIALFIRE CONTACT:\n")
    cr = conn.execute(text("""
        SELECT "$id", firma, plz, ort, strasse,
               "AP_Vorname", "AP_Nachname", "$status", "$status_detail"
        FROM public.contacts
        WHERE "$phone" = :phone
        ORDER BY (CASE WHEN plz IS NOT NULL AND plz != '' THEN 0 ELSE 1 END),
                 "$changed" DESC NULLS LAST
        LIMIT 1
    """), {"phone": PHONE}).fetchone()

    if cr:
        for label, val in [
            ("contact_id", cr[0]), ("firma", cr[1]), ("plz", cr[2]),
            ("ort", cr[3]), ("strasse", cr[4]),
            ("AP_Vorname", cr[5]), ("AP_Nachname", cr[6]),
            ("status", cr[7]), ("status_detail", cr[8]),
        ]:
            print(f"  {label:20s} {val}")
    print()

# ── STEP 2: Build context ───────────────────────────────────────────────
print("=" * 90)
print("STEP 2: CONTEXT BUILDING (02_classify.py)")
print("-" * 90)

with engine.connect() as conn:
    db_rows = conn.execute(text("""
        SELECT af.started, t.transcript_text
        FROM media_pipeline.audio_files af
        LEFT JOIN media_pipeline.transcriptions t ON t.audio_file_id = af.id
        WHERE af.phone = :phone AND af.b2_object_key LIKE 'dexter/audio/%%'
        ORDER BY af.started DESC
    """), {"phone": PHONE}).fetchall()

parts = []
word_count = 0
calls_included = 0
for i, (started, txt) in enumerate(db_rows):
    txt = (txt or "").strip()
    if not txt or len(txt) < 30:
        continue
    date = str(started)[:10]
    words = len(txt.split())
    if word_count + words > 3000:
        break
    parts.append(f"--- Anruf {calls_included + 1} (Datum: {date}) ---")
    parts.append(txt)
    word_count += words
    calls_included += 1

context = "\n\n".join(parts)
user_msg = f"Kontakt: {PHONE}\nAnzahl Anrufe: {len(rows)}\n\n{context}"

print(f"\n  Calls included: {calls_included} (most recent first)")
print(f"  Context words:  {word_count}")
print(f"  User msg size:  {len(user_msg)} chars")
print()

# ── STEP 3: LLM Classification ──────────────────────────────────────────
print("=" * 90)
print("STEP 3: LLM CLASSIFICATION")
print("-" * 90)

with open(ROOT / "config" / "taxonomy.json", encoding="utf-8") as f:
    taxonomy = json.load(f)
with open(ROOT / "prompts" / "classify_journey.txt", encoding="utf-8") as f:
    template = f.read()


def fmt(cats):
    lines = []
    for c in cats:
        quotes = c.get("quotes", [])
        qs = " | ".join(f'"{q}"' for q in quotes)
        lines.append(f'- **{c["id"]}: {c["label"]}**')
        if qs:
            lines.append(f"  Typische Aussagen: {qs}")
    return "\n".join(lines)


system_prompt = template.replace("{gk_categories}", fmt(taxonomy["gatekeeper"])).replace(
    "{dm_categories}", fmt(taxonomy["decision_maker"])
)

print(f"\n  System prompt: {len(system_prompt)} chars")
print(f"  Calling gpt-5.4-mini-2026-03-17...\n")

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
response = client.chat.completions.create(
    model="gpt-5.4-mini-2026-03-17",
    temperature=0.0,
    response_format={"type": "json_object"},
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ],
)

result = json.loads(response.choices[0].message.content)
usage = response.usage

print("  RAW LLM RESPONSE:")
print(json.dumps(result, indent=2, ensure_ascii=False))
print(f"\n  Tokens: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}")

# ── STEP 4: Post-processing ─────────────────────────────────────────────
print()
print("=" * 90)
print("STEP 4: POST-PROCESSING")
print("-" * 90)

evidence = result.get("evidence_quote", "")
found = evidence in context if evidence else False
print(f"\n  4a. Evidence validation:")
print(f"      Quote:    \"{evidence}\"")
print(f"      In text?  {found}")
if not found and evidence:
    print(f"      --> Confidence capped at 0.5!")


def clean_name(n):
    if not n or str(n).lower() in ("null", "none", "unbekannt", "n/a"):
        return ""
    return re.sub(r"[.,:;!?]+$", "", str(n).strip())


contact_name = clean_name(result.get("contact_person_name"))
gk_name = clean_name(result.get("gatekeeper_name"))

print(f"\n  4b. Name resolution:")
print(f"      LLM contact_person_name: {result.get('contact_person_name')!r}")
print(f"      LLM contact_person_role: {result.get('contact_person_role')!r}")
print(f"      LLM gatekeeper_name:     {result.get('gatekeeper_name')!r}")
print(f"      Dialfire AP fields:       {cr[5]!r} / {cr[6]!r}" if cr else "      (no contact)")
print(f"      --> Final AP name: {contact_name!r}")
print(f"      --> Final GK name: {gk_name!r}")
if not contact_name:
    print(f'      --> Pitch fallback: "der zustaendigen Person"')

print(f"\n  4c. System: {result.get('system_in_use')!r}")

# ── STEP 5: Reference matching ──────────────────────────────────────────
print()
print("=" * 90)
print("STEP 5: REFERENCE MATCHING (real km distance)")
print("-" * 90)

contact_plz = cr[2] if cr else ""
print(f"\n  Contact PLZ: {contact_plz} ({cr[3] if cr else '?'})")

dist_calc = pgeocode.GeoDistance("de")
refs = []
with open(ROOT / "config" / "referenzen.csv", encoding="utf-8") as f:
    refs = list(csv.DictReader(f))

scored = []
for ref in refs:
    rplz = ref.get("plz", "")
    if not rplz or not contact_plz:
        continue
    km = dist_calc.query_postal_code(contact_plz, rplz)
    if km != km:
        continue
    scored.append((km, ref))
scored.sort(key=lambda x: x[0])

print(f"\n  Top 5 nearest references:")
for km, ref in scored[:5]:
    prox = "nah" if km <= 50 else "fern"
    print(f"    {km:6.1f} km [{prox}]  {ref['einrichtung'][:40]:40s} {ref['ort']}")

best_km, best_ref = scored[0]
best_prox = "nah" if best_km <= 50 else "fern"
print(f"\n  Winner: {best_ref['einrichtung']} in {best_ref['ort']} ({best_km:.0f}km, {best_prox})")

# ── STEP 6: Pitch generation ────────────────────────────────────────────
print()
print("=" * 90)
print("STEP 6: PITCH GENERATION")
print("-" * 90)

cat_id = result.get("category_id", "")
cat = None
for c in taxonomy["gatekeeper"] + taxonomy["decision_maker"]:
    if c["id"] == cat_id:
        cat = c
        break

if not cat:
    print(f"\n  No template for {cat_id}")
else:
    print(f"\n  Category: {cat['id']} - {cat['label']}")
    print(f"  Action:   {cat['action']}")

    if cat["action"] == "exclude":
        print(f"\n  --> RAUS: kept in CSV flagged, no pitch")
        print(f"  Note: \"{cat['answer_template']}\"")
    else:
        print(f"\n  Raw template:")
        for line in textwrap.wrap(cat["answer_template"], 85):
            print(f"    {line}")

        print(f"\n  Filling placeholders:")
        print(f"    [Datum]            --> {result.get('last_call_date', '')}")
        print(f"    [Name Heim]        --> {best_ref['einrichtung']}")
        print(f"    [Ort in der Naehe] --> {best_ref['ort']}")
        print(f"    [Grund]            --> {result.get('reason_summary', '')}")
        ap = contact_name or "der zustaendigen Person"
        print(f"    [mein AP]          --> {ap}")
        print(f"    proximity          --> {best_prox}")

# ── STEP 7: Final row ───────────────────────────────────────────────────
print()
print("=" * 90)
print("STEP 7: FINAL CSV ROW")
print("-" * 90)
action = "raus" if (cat and cat["action"] == "exclude") else "pitch"
final = {
    "phone": PHONE,
    "firma": cr[1] if cr else "",
    "ort": cr[3] if cr else "",
    "plz": contact_plz,
    "num_calls": str(len(rows)),
    "last_call_date": result.get("last_call_date", ""),
    "role": result.get("role", ""),
    "category_id": cat_id,
    "category_label": result.get("category_label", ""),
    "confidence": str(result.get("confidence", "")),
    "action": action,
    "reason_summary": result.get("reason_summary", ""),
    "system_in_use": result.get("system_in_use", ""),
    "contact_person_name": contact_name,
    "contact_person_role": result.get("contact_person_role", ""),
    "gatekeeper_name": gk_name,
    "ref_einrichtung": best_ref["einrichtung"],
    "ref_ort": best_ref["ort"],
    "ref_distance_km": f"{best_km:.1f}",
    "ref_proximity": best_prox,
}
print()
for k, v in final.items():
    print(f"  {k:25s} = {v}")
print()
