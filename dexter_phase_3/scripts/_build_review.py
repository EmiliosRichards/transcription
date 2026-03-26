"""Build a review bucket from a pipeline run — one readable file per contact."""
import json
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build_review(run_dir: Path):
    review_dir = run_dir / "review"
    review_dir.mkdir(exist_ok=True)

    # Load all data
    journeys = {}
    with open(run_dir / "journeys.jsonl", encoding="utf-8") as f:
        for line in f:
            j = json.loads(line)
            journeys[j["phone"]] = j

    final = []
    with open(run_dir / "final_output.csv", encoding="utf-8") as f:
        final = list(csv.DictReader(f))

    # Sort: pitch first, then raus, then no_template
    action_order = {"pitch": 0, "raus": 1, "no_template": 2}
    final.sort(key=lambda r: (action_order.get(r.get("action", ""), 3), r.get("phone", "")))

    # Build per-contact review files
    for i, row in enumerate(final, 1):
        phone = row["phone"]
        journey = journeys.get(phone, {})
        calls = journey.get("calls", [])
        calls.sort(key=lambda c: c.get("started") or "")

        firma = row.get("firma", "") or "(unbekannt)"
        safe_phone = phone.replace("+", "")
        action = row.get("action", "")

        lines = []
        lines.append(f"{'='*80}")
        lines.append(f"CONTACT {i}: {firma}")
        lines.append(f"Phone: {phone}")
        lines.append(f"{'='*80}")
        lines.append("")

        # Contact info
        lines.append("CONTACT DETAILS")
        lines.append(f"-" * 40)
        lines.append(f"  Firma:         {firma}")
        lines.append(f"  PLZ / Ort:     {row.get('plz', '')} {row.get('ort', '')}")
        lines.append(f"  AP:            {row.get('ap_vorname', '')} {row.get('ap_nachname', '')}")
        lines.append(f"  Total calls:   {row.get('num_calls', len(calls))}")
        lines.append(f"  Last call:     {row.get('last_call_date', '')}")
        lines.append("")

        # Classification
        lines.append("CLASSIFICATION")
        lines.append(f"-" * 40)
        role_desc = "Gatekeeper" if row.get("role") == "GK" else "Decision Maker" if row.get("role") == "DM" else "Unknown"
        lines.append(f"  Role:          {row.get('role', '')} ({role_desc})")
        lines.append(f"  Category:      {row.get('category_id', '')} - {row.get('category_label', '')}")
        lines.append(f"  Confidence:    {row.get('confidence', '')}")
        lines.append(f"  Evidence:      \"{row.get('evidence_quote', '')}\"")
        lines.append(f"  Reason:        {row.get('reason_summary', '')}")
        lines.append(f"  System:        {row.get('system_in_use', '')}")
        lines.append(f"  AP Name:       {row.get('contact_person_name', '')}")
        lines.append(f"  AP Role:       {row.get('contact_person_role', '')}")
        lines.append(f"  GK Name:       {row.get('gatekeeper_name', '')}")
        lines.append("")

        # Do not call
        dnc = row.get("do_not_call", "")
        if dnc and dnc.lower() == "true":
            lines.append("DO NOT CALL: YES")
            lines.append(f"-" * 40)
            lines.append(f"  Call count:    {row.get('do_not_call_call_count', '')}")
            lines.append(f"  Evidence:      \"{row.get('do_not_call_evidence', '')}\"")
            lines.append("")

        # Termin booked
        termin = row.get("termin_booked", "")
        if termin and str(termin).lower() == "true":
            lines.append("TERMIN BOOKED: YES")
            lines.append(f"-" * 40)
            lines.append(f"  Details:       {row.get('termin_details', '')}")
            lines.append("")

        # Suggested new category
        snc = row.get("suggested_new_category", "")
        if snc:
            lines.append("SUGGESTED NEW CATEGORY")
            lines.append(f"-" * 40)
            lines.append(f"  Category:      {snc}")
            lines.append(f"  Reason:        {row.get('suggested_new_category_reason', '')}")
            lines.append("")

        # Reference match
        lines.append("REFERENCE MATCH")
        lines.append(f"-" * 40)
        ref = row.get("ref_einrichtung", "")
        if ref:
            lines.append(f"  Facility:      {ref}")
            lines.append(f"  Location:      {row.get('ref_ort', '')} (PLZ {row.get('ref_plz', '')})")
            lines.append(f"  System:        {row.get('ref_system', '')}")
            lines.append(f"  Traeger:       {row.get('ref_traeger', '')}")
            lines.append(f"  Proximity:     {row.get('ref_proximity', '')} ({row.get('ref_distance_km', '')} km)")
        else:
            lines.append("  (no reference matched)")
        lines.append("")

        # Action + Pitch
        lines.append(f"ACTION: {action.upper()}")
        lines.append(f"{'='*80}")
        lines.append("")

        pitch = row.get("pitch_text", "")
        enhanced = row.get("pitch_text_enhanced", "")
        followup = row.get("generic_followup", "")
        enhanced_followup = row.get("enhanced_followup", "")

        if pitch:
            lines.append("TEMPLATE PITCH:")
            lines.append(f"-" * 40)
            lines.append(f"  {pitch}")
            lines.append("")

        if enhanced:
            lines.append("ENHANCED PITCH (LLM):")
            lines.append(f"-" * 40)
            lines.append(f"  {enhanced}")
            lines.append("")

        if followup:
            lines.append("GENERIC FOLLOW-UP:")
            lines.append(f"-" * 40)
            lines.append(f"  {followup}")
            lines.append("")

        if enhanced_followup:
            lines.append("ENHANCED FOLLOW-UP (LLM):")
            lines.append(f"-" * 40)
            lines.append(f"  {enhanced_followup}")
            lines.append("")

        if not pitch and action == "raus":
            lines.append("  (no pitch - contact flagged as RAUS)")
            lines.append("")
        elif not pitch and action == "no_template":
            lines.append("  (no pitch - no template for this category)")
            lines.append("")

        # Full call transcripts
        lines.append(f"{'='*80}")
        lines.append(f"CALL TRANSCRIPTS ({len(calls)} calls)")
        lines.append(f"{'='*80}")
        lines.append("")

        for ci, call in enumerate(calls, 1):
            date = str(call.get("started", ""))[:16]
            txt = (call.get("transcript_text") or "").strip()

            lines.append(f"--- Call {ci} ({date}) ---")
            if not txt or len(txt) < 10:
                lines.append("  (no meaningful transcript)")
            else:
                lines.append(txt)
            lines.append("")

        # Write file
        filename = f"{i:02d}_{safe_phone}_{action}.txt"
        filepath = review_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # Summary index
    summary = []
    summary.append("REVIEW SUMMARY")
    summary.append(f"{'='*80}")
    summary.append(f"Run: {run_dir.name}")
    summary.append(f"Model: gpt-5.4-mini-2026-03-17")
    summary.append("")
    summary.append(f"Total contacts:   {len(final)}")
    summary.append(f"Pitches:          {sum(1 for r in final if r.get('action') == 'pitch')}")
    summary.append(f"  - Enhanced:     {sum(1 for r in final if r.get('pitch_text_enhanced', ''))}")
    summary.append(f"  - Template only:{sum(1 for r in final if r.get('action') == 'pitch' and not r.get('pitch_text_enhanced', ''))}")
    summary.append(f"Raus (flagged):   {sum(1 for r in final if r.get('action') == 'raus')}")
    summary.append(f"No template:      {sum(1 for r in final if r.get('action') == 'no_template')}")

    # DNC count
    dnc_count = sum(1 for r in final if r.get("do_not_call", "").lower() == "true")
    if dnc_count:
        summary.append(f"Do-not-call:      {dnc_count}")

    summary.append("")
    summary.append(f"{'#':>3s}  {'Phone':20s}  {'Action':12s}  {'Role':4s}  {'Category':45s}  {'Conf':5s}  {'Firma':30s}")
    summary.append("-" * 130)

    for i, row in enumerate(final, 1):
        firma = (row.get("firma", "") or "")[:30]
        cat = (row.get("category_label", "") or "")[:45]
        enhanced_marker = " *" if row.get("pitch_text_enhanced", "") else "  "
        summary.append(
            f"{i:3d}  {row['phone']:20s}  {row.get('action', ''):12s}  "
            f"{row.get('role', ''):4s}  {cat:45s}  {row.get('confidence', ''):5s}  {firma}{enhanced_marker}"
        )

    summary.append("")
    summary.append("* = LLM-enhanced pitch")
    summary.append("")
    summary.append("FILES:")
    summary.append("-" * 40)
    for i, row in enumerate(final, 1):
        phone = row["phone"]
        safe_phone = phone.replace("+", "")
        action = row.get("action", "")
        firma = (row.get("firma", "") or "")[:35]
        filename = f"{i:02d}_{safe_phone}_{action}.txt"
        summary.append(f"  {filename:45s} {firma}")

    with open(review_dir / "00_SUMMARY.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(summary))

    print(f"Review bucket created: {review_dir}")
    print(f"  {len(final)} contact files")
    print(f"  1 summary index (00_SUMMARY.txt)")


if __name__ == "__main__":
    run_name = sys.argv[1] if len(sys.argv) > 1 else "runs/sample_20_v2"
    run_dir = ROOT / run_name
    if not run_dir.exists():
        print(f"Run dir not found: {run_dir}")
        sys.exit(1)
    build_review(run_dir)
