IMPLEMENTATION_CHECKLIST.md (template)

Save this file at docs/IMPLEMENTATION_CHECKLIST.md. Keep it updated as you work.

Project: Transcript Fusion POC

Owner: <your‑name>
Date: <YYYY‑MM‑DD>

R0 — Repo Scan




Notes:
R1 — Config & Schemas




Gate: Validate schemas with a dummy instance set (no outputs generated).

R2 — Package Skeleton




Gate: Import check passes (python -c "import pipeline").

R3 — CLI




Gate: make smoke runs preflight + schema validation only.

R4 — Prompts




Gate: Prompt lint (spellcheck, placeholders resolved).

R5 — Example Data




Gate: Preflight passes on examples.

R6 — First Dry‑Run




Gate: master.txt line format [mm:ss] Speaker: Text; no QA lines inside master.

R7 — Tests




Gate: CI step green (if configured).

R8 — DOCX Export




Gate: Manual open confirms headings & TOC.

R9 — Block Processing




Gate: Removing one block output then re‑running only recreates that block.

R10 — Accuracy Tuning




Gate: Reduced LOW_CONF rate on examples without introducing hallucinations.

R11 — Automation Ready




Gate: One‑command run works on clean machine.

Notes / Decisions Log




Known Risks & Mitigations

Different start offsets → handled in align/estimate_offset.py using median of top‑k sentence matches.

2‑speaker Krisp mapping → majority vote vs Teams; >2 speaker cases force Teams names.

Hallucinations → No‑Dummy rule enforced in prompts and by schema; code computes confidence.

How to use this in your repo

Save summary.md and recommended_approach.md at the repo root.

Create docs/ and commit IMPLEMENTATION_CHECKLIST.md (from the template above).

In Cursor, open a new chat and paste the SYSTEM / SUPERVISOR PROMPT from the top of this document.

Let the agent create/modify files step‑by‑step; it should update the checklist as it goes.

If it gets stuck, the Fail‑Closed gates will tell you what to fix. Commit early and often.