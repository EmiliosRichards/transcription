Got it 👍 Here’s the full English translation of your document:

---

**Super—here’s your complete handover for your LLM specialist.**
This document summarizes all insights, pitfalls, guardrails, the finalized prompts, and an actionable API pipeline – including validation checklists and example code.

---

### 1) Executive Summary

**Goal:** From multiple raw transcripts of the same call (Teams, Krisp, Charla), create a clean master transcript that:

* uses the best wording,
* carries the correct speaker names,
* transparently documents uncertainties in a QA report,
* is available in TXT (for further AI analysis) and DOCX with table of contents (for humans).

**Core principles / Guardrails (for all prompts & pipelines):**

* **Absolute no-dummy rule:** Never generate placeholder/fantasy text if real input files are available.
* **Fail-closed:** If an expected file is missing/inconsistent → abort with a clear error message (no “creative” filling).
* **Source grounding:** Content must come only from the provided files; in case of uncertainty → mark as LOW\_CONF, do not guess.
* **Visible QA separation:** Master transcript stays clean; QA notes in a separate file.
* **Deterministic execution:** Set temperature/top-p/seed; log prompt version + file hashes.

---

### 2) Sources & Characteristics

**Teams (.docx)**

* Strongest speaker names/labels (real names),
* wording partly paraphrased or clumsy.

**Krisp (.txt)**

* Best word quality, fluent sentence structure,
* only Speaker 1 / Speaker 2 (mapping required).

**Charla (.txt)**

* Complements missing half-sentences/smoothing,
* speakers partly generic; fallback/support.

**Proven heuristic:**

* *Krisp = base text*
* *Teams = name mapping (Speaker 1/2 or >2 speakers)*
* *Charla = backup if Krisp/Teams diverge or have gaps*

---

### 3) Risks & How to Circumvent Them

* **Recording start offsets (different start times)** → estimate offset with sentence-based similarity (median of best matches), not just timecodes.
* **Krisp has only 2 speakers** → robust mapping (majority vote sentence-wise against Teams).
* **Teams wording deviates** → use only for names and timing anchors; keep text quality Krisp-driven.
* **Noise/fillers (“yeah, okay, right…”)** → filter (≤3 words) + collapse duplicates in 3–5 sec windows.
* **“Hallucinations”/fantasy text** → no-dummy rule + fail-closed + QA separation.

---

### 4) Prompt Catalog (Final Versions)

#### 4.1 Prompt 1 — Transcript Fusion (Deep Research)

**Purpose:** Three transcripts (Teams, Krisp, Charla) → one master transcript + QA report + exports (TXT & DOCX).

**Prompt 1 (Deep Research):** Master transcript fusion

**Goal:**
Generate a clean, speaker-corrected master transcript from three transcripts (Teams .docx, Krisp .txt, Charla .txt) with a separate QA report. Do not invent content.

**Security rules (strict, global):**

* Never generate dummy/example content. Outputs must come solely from loaded files.
* Before processing: check that all three files are loaded/readable; if not → abort with error.
* Before every export (TXT/DOCX) explicitly confirm (API controller flag) that real content is being exported.
* For uncertainties, mark as LOW\_CONF in QA report, don’t guess.

**Input logic & validation:**

1. Request Teams transcript (.docx). Check:

   * Contains real speaker names/Teams layout?
   * Contains timestamps?
2. Request Krisp transcript (.txt). Check:

   * Contains “Speaker 1/2”? Timestamps?
3. Request Charla transcript (.txt). Check:

   * Contains time blocks and continuous text?
   * If any check fails → abort.

**Procedure:**

1. Determine number of speakers (via Teams). If exactly 2:

   * Krisp = base text; map Speaker 1/2 → names by majority vs Teams.
   * Teams = reference for names/timing; Charla = support.
     If >2 speakers:
   * Teams required for name mapping, Krisp for text quality, Charla as fallback.

2. Offset calculation (Krisp↔Teams, Charla↔Teams):

   * Sentence similarity (e.g. SequenceMatcher).
   * Offset = median of top matches (seconds).

3. Segmentation & alignment:

   * Split into sentences/segments.
   * Align by text similarity, secondarily by offset-corrected timestamps.

4. Fusion:

   * Base = Krisp sentence.
   * Speaker name = Teams mapping.
   * Charla for smoothing/filling gaps if Krisp/Teams diverge.
   * Remove short fillers (≤3 tokens), collapse duplicates within 3–5 sec per speaker.
   * Format: “\[mm\:ss] Speaker: Text”.

5. Confidence & QA:

   * Confidence per line from similarity (Krisp↔Teams/Charla), length, timing proximity.
   * LOW\_CONF <0.50 noted in QA report (not in master).

6. Export:

   * TXT = plain master text.
   * DOCX = same, plus:
     • Chapter heading every 5 min (Level 1)
     • Speaker change optional Level 2
     • Automatic TOC
   * QA report = TXT listing all LOW\_CONF, removed fillers, duplicates, sample snippets.

**Output:**

1. Master transcript (TXT)
2. Master transcript (DOCX, with TOC)
3. QA report (TXT)

---

#### 4.2 Prompt 2 — Client’s Product (Analysis on Master Transcript)

**Goal:** From the master transcript extract all info explaining:

* What the client (contractor) offers (product/service, variants, modules).
* What is offered to their end customers (performance, scope, specifics).
* USPs/differentiators (technical, processual, economic).
* Customer benefits (concrete, measurable, use cases).
* Competitive distinction.

**Obligations:**

* First quote verbatim (with \[mm\:ss]), then summarize/synthesize.
* Strict terminology: “Mandant” = contractor/client; “Kunde/customers” = end customers of client. If ambiguous, infer from context and note.
* Do not omit anything. Pruning comes later.

**Optional:** Add more prompts (pitch extraction, objections + handling, target tone of voice, script generator in JSON import format) after Prompt 2.

---

### 5) API Implementation (Practical Guide)

**Recommended endpoint:** Responses API (unified Chat/Assistants; structured output possible).

* Docs: Responses API / Guides, Structured Outputs / JSON Schema, File Upload.

**5.1 Project Structure**

```
project/
  .env                         # OPENAI_API_KEY=...
  run_fusion.py
  prompts/
    prompt1_fusion.md
    prompt2_produkt.md
  data_in/
    teams.docx
    krisp.txt
    charla.txt
  out/
    master.txt
    master.docx
    qa.txt
    logs/
      run_YYYYMMDD_HHMM.jsonl
```

**5.2 Robustness Checklist (Controller/Preflight):**

* Do all three files exist?
* Log hash of each file (reproducibility).
* File size plausible (>1 KB).
* File type plausible (.docx/.txt).
* No export without preflight OK.

**5.3 Structured Output (JSON Schema):**
Responses API can enforce schema → clean return of master\_txt, qa\_txt, outline\_docx\_instructions.
DOCX rendered client-side (python-docx + TOC).

*(schema example shortened)*

**5.4 Python Skeleton (Upload → Responses call → Artifacts)**
\[included in original; left unchanged here]

**5.5 Block processing (for XXL calls):**
Block size \~10–15 min.
Per block: fusion + QA → merger sequentially builds master.txt & qa.txt.
Advantage: more stable, reproducible, easier reruns.

**5.6 Parameter recommendations:**

* temperature=0.2 (precise, low variance)
* reasoning.effort="high" (deep cross-referencing)
* Seeds/determinism depending on SDK – otherwise logs & hashes for reruns.

---

### 6) QA Report Specification

Includes:

* LOW\_CONF spots: \[mm\:ss] + “Krisp: … | Teams match: … | Charla: … | conf=0.43”
* Removed fillers (count + examples)
* Duplicate collapse (count + examples)
* Offset estimates (Krisp↔Teams, Charla↔Teams)
* Speaker mapping (e.g. Speaker 1 → Bastian, Speaker 2 → Lorenz Schrader) + voice evidence (match counts)

Confidence heuristic (recommended):
+0.25 if Krisp↔Teams similarity ≥0.65
+0.25 if Krisp↔Charla similarity ≥0.65
–0.10 if Teams match <0.40
–0.05 if very short sentences (≤4 tokens)
LOW\_CONF <0.50

---

### 7) DOCX Rendering (Client-side)

Title: “Master Transcript (<Date>/<Meeting name>)”
Structure:

* Level 1: Chapter every 5 min (“00:00–04:59”, “05:00–09:59”)
* Content: “\[mm\:ss] Speaker: Text” as normal paragraph
* TOC: automatic table of contents (python-docx/template; updated in Word on open).

---

### 8) Operations & Monitoring

* Logging: JSONL per run with prompt version, model, temperature, seeds (if available), file hashes, block boundaries, cost estimate (tokens in/out), duration.
* Reruns: if blocks fail → only regenerate those.
* Versioning: version prompts/; filenames with ISO date.
* Security: no personal data stored permanently; use hashes instead of filenames in logs.

---

### 9) Cost Note

Costs scale linearly with tokens (in + out).
For gpt-4.1 and Responses API see official pricing; expect a few USD per 1–2h conference (depending on length/QA depth).

---

### 10) “No-Dummy” Add-on (for all your prompts)

At the beginning of each prompt, append:

**Mandatory safety clauses:**

* Use only content from provided files. Never generate example/placeholder/fantasy content.
* Abort and return clear error if any required file is missing, faulty, or unreadable.
* Do not export (TXT/DOCX/JSON) before input validation.
* Mark every uncertainty as LOW\_CONF in QA report instead of speculating.

---

### What your LLM specialist can concretely do now

* Save these prompts in your codebase (prompts/prompt1\_fusion.md, prompt2\_produkt.md).
* Implement the Responses pipeline as per section 5 (upload → responses call with JSON schema → save artifacts).
* Implement DOCX renderer (python-docx) with TOC.
* Enable block processing if the call is very long.
* Check logs/QA, adjust thresholds (filler filter, duplicate window, LOW\_CONF cutoff) if needed.

If you want, I can next provide a ready-to-use Python script (production-grade) with:

* File upload & hashing
* Responses call incl. structured output
* Clean DOCX export (with TOC)
* Full logging/retry – as a drop-in tool for your ops.

---

Do you want me to also translate the embedded **Python code comments** into English, or should I keep them in German for your dev team?
