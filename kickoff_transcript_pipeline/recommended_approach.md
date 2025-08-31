Great brief. Here’s a pragmatic way to lay this out so you get a clean POC quickly, then scale it without repainting the house later.

# Recommended approach (short version)

* **Start with a Python CLI “micro‑orchestrator”** (run from Cursor or `make`). That gives you speed, testability, and reproducibility.
* **Keep the pipeline strictly modular** (tiny, composable steps with typed I/O on disk). That lets you slot in Airflow/**n8n** later only when you actually need scheduling/parallelism.
* **Break the “do‑everything” Prompt 1 into small, deterministic stages** (parse → align → fuse → QA → export). This increases accuracy and debuggability.
* **Use JSON as the contract between stages** and write every artifact to `out/` with logged hashes + run metadata.
* **Automate later**: when you need cron/SLA/alerting, wrap the same CLI with Airflow DAGs (or n8n webhooks → CLI). n8n is good if you want a visual trigger/ops panel; Airflow if you need heavy scheduling/SLAs. ([n8n][1], [theninjastudio.com][2])

---

# Architecture (POC → prod)

## 0) Repo layout (minimal but future‑proof)

```
project/
  .env
  Makefile
  pyproject.toml
  src/pipeline/
    __init__.py
    preflight.py          # file checks, hashing
    ingest/
      read_teams.py       # -> JSON (segments, speakers, timestamps)
      read_krisp.py
      read_charla.py
    align/
      estimate_offset.py  # sentence sim, median of top matches
      align_segments.py
    fuse/
      map_speakers.py     # 2+ speakers; majority vote vs Teams
      fuse_text.py        # base=Krisp, Teams=names, Charla=fallback
      filter_fillers.py   # <=3 tokens, collapse dups 3–5s
    qa/
      score_confidence.py # heuristic -> per-line conf
      build_qa_report.py
    export/
      write_master_txt.py
      write_master_docx.py
    llm/
      responses_client.py # thin wrapper around Responses API
  prompts/
    prompt_fuse_block.md  # smaller, focused
    prompt_extract_product.md
  data_in/                # teams.docx, krisp.txt, charla.txt
  out/
    run_20250822_1201/    # artifacts per run (see logging below)
  configs/
    default.yaml          # thresholds, model, block minutes, etc.
```

## 1) Orchestration (CLI first)

Create a single CLI (`run_fusion.py` or `pipeline main`) that runs **deterministic, named steps**:

```
pipeline run \
  --config configs/default.yaml \
  --teams data_in/teams.docx \
  --krisp data_in/krisp.txt \
  --charla data_in/charla.txt \
  --out out/
```

Under the hood, it executes steps in order; each step:

* reads a JSON/flat file contract,
* writes its own output file,
* logs `{step, input_hashes, output_hashes, params, duration, tokens_cost}` to `out/run_YYYYMMDD_HHMM.jsonl`.

Why CLI first?

* Fast iteration in Cursor.
* Easy to unit‑test each step.
* The same CLI can be wrapped by Airflow Operators or **n8n** Execute Command nodes later. ([n8n][1])

## 2) Break Prompt 1 into smaller calls

Instead of one giant “fusion” prompt, use **two or three focused LLM calls** with clear grounding and failure modes:

**(a) Parse/normalize (no LLM if possible):**

* Prefer deterministic parsers for Teams/Krisp/Charla → JSON with fields:
  `{ "source":"krisp", "t":[sec], "speaker":"Speaker 1", "text":"..." }`.
* If Teams names layout is tricky, a small “classifier prompt” can extract REAL names (fail‑closed if unclear).

**(b) Alignment (LLM optional):**

* Use code (e.g., difflib/rapidfuzz) to compute sentence similarity; estimate offsets (median of top‑k).
* Produce aligned blocks of \~10–15 minutes (from your brief).

**(c) Fusion (LLM with schema):**

* For each block, call the Responses API with **schema‑enforced output** returning `master_block`, `qa_block`, and minimal outline hints.
* Provide all **aligned** sentences for Krisp/Teams/Charla as input context; ask the model only to select/merge, **never invent** (keep the No‑Dummy clauses).
* Temperature 0.2, reasoning effort “high”, and **seed if available**.

**(d) QA + Confidence (post‑processing):**

* Compute your confidence heuristic numerically in code (not by the model) so it’s reproducible.
* Mark lines `<0.50` as LOW\_CONF, but keep master clean.

**(e) Exports:**

* `master.txt` (plain).
* `master.docx` rendered **client‑side** via `python-docx` with TOC and chapter headings every 5 minutes.
* `qa.txt` with LOW\_CONF entries, removed fillers, duplicate collapses, offsets, mapping evidence.

This split gives you **accuracy** (the model makes fewer, narrower decisions) and **traceability** (if something is off, you know which stage). It also fully honors the “No‑Dummy, Fail‑Closed, Visible QA” guardrails from the summary.

## 3) Data contracts (make bugs visible)

Define small Pydantic (or dataclass) models for:

* `Segment`: `{source, t_start, t_end?, speaker, text, tokens?}`
* `AlignedPair`: `{krisp_seg_id, teams_seg_id?, charla_seg_id?, offset_sec}`
* `MasterLine`: `{t, speaker, text, conf}`
* `QAItem`: `{t, snippet_refs, conf, reason}`

Persist these as newline‑delimited JSON. It’s noisy but **debuggable**.

## 4) Determinism & safety

* **Preflight**: existence, size >1KB, extension, SHA‑256. Abort on fail.
* **Deterministic knobs**: temperature/top‑p/seed; log model, prompt digest, and file hashes.
* **No‑Dummy**: every LLM call includes the safety block from the summary and **refuses to proceed** unless all three files were confirmed in preflight.

## 5) Block processing

* Use `minutes_per_block = 12` (configurable).
* Iterate blocks → `fusion → qa` → append to `master.txt` + `qa.txt`.
* If a block fails, you can re‑run **just that block** (use block index & input hashes in filenames).

## 6) Tests that matter (fast feedback)

* Unit tests for: parsing, offset estimator, alignment, filler filter, duplicate collapse, confidence scoring.
* Golden tests: small synthetic meetings with known mappings (2 speakers / 3+ speakers / noisy fillers).
* “Replay” test: same inputs + same config → identical outputs (hash compare).

## 7) Automating (when you need it)

* **Keep using the CLI** for a while; add a `Makefile`:

  * `make run` → local
  * `make smoke` → run on a 2‑min sample
  * `make block-test` → re-run one block
* **When jobs become frequent / many files arrive daily**:

  * **Airflow** if you want cron, SLAs, backfills, retries, monitoring per task/DAG.
  * **n8n** if you want a simpler, visual webhook → queue → shell execution + notifications (it’s open-source and has built‑in OpenAI nodes). ([n8n][1], [theninjastudio.com][2])

Both can wrap your existing CLI with zero code changes. Airflow gives you heavier governance; n8n gives you a friendlier ops UI and quick “glue” to Slack/Drive/S3.

---

# Concrete POC plan (1–2 days of build time)

**Milestone A — Skeleton running end‑to‑end on a 5–10 min call**

1. Preflight (hash, sizes) → `out/run_.../preflight.json`
2. Parse all three → `out/.../segments_{teams|krisp|charla}.jsonl`
3. Offset estimate + align (code only) → `out/.../aligned_block_000.json`
4. Block fusion via Responses API (schema) → `out/.../master_block_000.txt`, `qa_block_000.txt`
5. Post‑QA scoring (code) adds `conf` where needed → `out/.../qa.txt`
6. Exports: `master.txt`, `master.docx` (with TOC), `qa.txt`
7. Logging JSONL with costs, timing, hashes.

**Milestone B — Accuracy & resilience**

* Tune filler threshold and duplicate window (3–5s) from the summary.
* Add “majority speaker mapping” vs Teams for 2‑speaker Krisp; force Teams for >2.
* Add block retry + idempotent outputs (skip if exists & hashes match).

**Milestone C — Automation ready**

* Single `docker run ...` that mounts `data_in/` and writes to `out/`.
* Optional: one **n8n** workflow to listen to a webhook, drop files to `data_in/`, call the container/CLI, then post Slack summary with links. ([n8n][1])

---

# Why not jump straight to Airflow/“NA10”?

* For a single pipeline that’s still evolving, **orchestration overhead slows you down**. The CLI + clear file contracts gives you 90% of the benefit now.
* Move to Airflow when you actually need: cron/backfills, dozens of concurrent calls, SLAs, lineage in a shared data platform.
* If by **“NA10”** you mean **n8n**, it’s a solid option for light scheduling/triggering and a visual control plane later; it’s open‑source and AI‑agent–friendly. ([n8n][1], [theninjastudio.com][2])

---

# Design choices that map to the summary (one‑to‑one)

* **No‑Dummy / Fail‑Closed** → enforced in preflight and re‑stated in every LLM call.
* **Source grounding** → pass only aligned source segments; schema requires returning **only** selections/edits of those.
* **Visible QA separation** → master is clean; QA is separate.
* **Determinism** → log prompt versions + file hashes; low temperature; seeds if supported.
* **Block processing** → 10–15 min chunks.
* **Confidence heuristic** → computed in code exactly as specified.
* **DOCX on client side** with TOC → `python-docx`.

---

If you want, I can generate the initial **CLI skeleton** (with the folder structure, config, JSON schemas, step runners, preflight, and a stubbed Responses call) so you can drop it into Cursor and hit the ground running.

[1]: https://n8n.io/?utm_source=chatgpt.com "AI Workflow Automation Platform & Tools - n8n"
[2]: https://www.theninjastudio.com/blog/what-is-n8n?utm_source=chatgpt.com "What is n8n? The Open-Source Workflow Automation Tool for AI in 2025"
