"""Compare template vs enhanced pitches side by side."""
import csv
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
run_dir = ROOT / "runs" / "compare_test"

# Load both
template_rows = {}
with open(run_dir / "pitches.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        template_rows[r["phone"]] = r

enhanced_rows = {}
with open(run_dir / "pitches_enhanced.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        enhanced_rows[r["phone"]] = r

# Show comparison
count = 0
for phone, er in enhanced_rows.items():
    enhanced_text = er.get("pitch_text_enhanced", "")
    template_text = template_rows.get(phone, {}).get("pitch_text", "")

    if not template_text:
        continue

    count += 1
    firma = er.get("firma", "")[:40]
    cat = er.get("category_label", "")
    role = er.get("role", "")
    reason = er.get("reason_summary", "")
    ref = er.get("ref_einrichtung", "")
    ref_ort = er.get("ref_ort", "")
    dnc = er.get("do_not_call", "")
    suggested = er.get("suggested_new_category", "")

    print("=" * 90)
    print(f"CONTACT {count}: {phone}")
    print(f"  {firma} | {role} | {cat}")
    print(f"  Reason: {reason}")
    print(f"  Ref: {ref} in {ref_ort}")
    if dnc and dnc.lower() == "true":
        print(f"  *** DO NOT CALL ***  evidence: {er.get('do_not_call_evidence', '')[:60]}")
    if suggested:
        print(f"  SUGGESTED NEW CATEGORY: {suggested}")
        print(f"    Why: {er.get('suggested_new_category_reason', '')}")
    print()

    print("  TEMPLATE PITCH:")
    for line in textwrap.wrap(template_text, 85):
        print(f"    {line}")
    print()

    if enhanced_text:
        print("  ENHANCED PITCH:")
        for line in textwrap.wrap(enhanced_text, 85):
            print(f"    {line}")
    else:
        print("  ENHANCED: (no enhancement — LLM kept original)")
    print()

    if count >= 8:
        break

# Show the 8 template-only ones
print("\n" + "=" * 90)
print("TEMPLATE-ONLY CONTACTS (no enhancement step):")
print("=" * 90)

template_only = 0
for phone, tr in template_rows.items():
    if phone in enhanced_rows and enhanced_rows[phone].get("pitch_text_enhanced"):
        continue
    if not tr.get("pitch_text"):
        continue
    template_only += 1
    firma = tr.get("firma", "")[:40]
    cat = tr.get("category_label", "")
    role = tr.get("role", "")

    print(f"\n  CONTACT: {phone} | {firma} | {role} | {cat}")
    print(f"  PITCH:")
    for line in textwrap.wrap(tr["pitch_text"], 85):
        print(f"    {line}")

    if template_only >= 8:
        break
