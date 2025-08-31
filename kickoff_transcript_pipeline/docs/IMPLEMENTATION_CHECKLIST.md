# IMPLEMENTATION_CHECKLIST

R0 — Repo scan (Completed)

- summary.md: present
- recommended_approach.md: present
- bridging_prompt.md: present

Notes:
- Inputs confirmed. Proceeding to R1 (config + schemas) and R2 (package skeleton).

R1 — Config + Schemas (Completed)

- configs/default.yaml created with deterministic defaults (temperature=0.2, seed=42).
- schemas/: segment.schema.json, aligned_pair.schema.json, master_line.schema.json, qa_item.schema.json.

R2 — Package skeleton (Completed)

- src/pipeline/: preflight.py, ingest/*, align/*, fuse/*, qa/*, export/*, llm/responses_client.py.
- run_fusion.py initial CLI added.

R3 — CLI + JSONL Logging (Completed)

- Expanded CLI to accept path overrides and write JSONL logs (run.jsonl).
- Preflight step logs duration and inputs.

R4 — Prompts (Completed)

- prompts/prompt_fuse_block.md added with No‑Dummy/Fail‑Closed clauses and strict JSON schema.
- prompts/prompt_extract_product.md added with quoting-first requirement and strict JSON schema.

R5 — Example data (Completed)

R6 — First dry-run (Completed)

R7 — Tests (Completed)

R8 — DOCX Export (Completed)

R9 — Block processing (Completed)

R10 — Accuracy tuning (Completed)

R11 — Automation-ready (Completed)

- Added Dockerfile and requirements.txt; container runs CLI by default.
- Makefile with run/smoke/docker targets.
- CLI supports --skip-existing for idempotent reruns and block-level retry.

- Exposed filler threshold, duplicate window, similarity thresholds, and confidence weights in config.
- Updated scoring to accept weights/thresholds; logged tuning parameters at run start.
- Tests: 7 passed after tuning changes.

- Implemented partitioning by minutes and per-block outputs.
- CLI supports --only-block / --start-block / --end-block for partial reruns.
- Verified run generated block_000.json.

- Implemented DOCX export with TOC and 5-minute chapter headings.
- Smoke test added; test suite: 6 passed.

- Unit tests added for ingest parsers, filler/duplicate filters, and confidence scoring.
- Test run: 5 passed.
- Next: DOCX export and block processing.

- Run directory: `out/run_20250822_165551/`
- Artifacts:
  - `preflight.json` with SHA-256 hashes and sizes >1KB for all inputs.
  - `run.jsonl` logging preflight and start_run events.
- Status: preflight_ok. Next: implement parsing/alignment to progress beyond preflight.

- examples/ created with tri-source sample (~2–3 minutes).
- data_in/ mirrored from examples/ so defaults work.


