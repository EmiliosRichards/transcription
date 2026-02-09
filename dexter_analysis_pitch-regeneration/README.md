# Dexter Calls  Phase A (Open-Ended Discovery)

## What is this?
Pipeline to discover call outcomes and failure reasons from transcripts without a predefined taxonomy, then prepare clean inputs for clustering  Taxonomy v1.

## Inputs
- A grouped JSONL file of calls per phone+campaign (German transcripts).
  - Typically produced by `scripts/originals/export_calls_for_final_numbers.py`
  - Default location in this repo (unless overridden): `output/dexter_calls_by_phone_campaign_final.jsonl`

## Outputs (per run)
- raw/dexter_free_extraction.jsonl  LLM annotations (outcome/reason/who/quote/conf)
- interim/dexter_free_extraction.csv  wide CSV for review
- slim/*.csv  short fields for embeddings & clustering
- reports/run_summary.txt  1-line summary per run
- reports/pre_embed_metrics.json  counts used to set clustering params
 - clusters_view.csv  join of clusters + evidence quotes (for reporting / naming)
 - reports/cluster_summaries.jsonl  per-cluster examples for naming
 - taxonomy/*  optional cluster naming + limited taxonomy outputs

## Method (Phase A)
1. Most-recent informative call per phone+campaign.
2. LLM free extraction (English labels, German quote; substring-anchored).
3. QC & views: slim CSVs (ALL, REACHABLE, conf0.5, GK/DM splits) with stable row_id.
4. Pre-embed metrics: top reasons, GK/DM split, uniqueness & top-10 share.
5. (Next) Embeddings + HDBSCAN  cluster naming  Taxonomy v1.

## Reproduce (example)
```powershell
# 0) activate venv (example)
. .venv\Scripts\Activate.ps1

# 1) choose a run folder (new folder per run)
$run = "dexter_analysis_pitch-regeneration\data\transcription_dexter_analysis\runs\2026-01-28_run1"

# 2) Phase A: free-label extraction (writes into $run via --run)
python dexter_analysis_pitch-regeneration\scripts\originals\extract_free_labels.py `
  --config dexter_analysis_pitch-regeneration\config\phaseA.yml `
  --run $run `
  --input "output\dexter_calls_by_phone_campaign_final.jsonl"

# 3) interim CSV for review
python dexter_analysis_pitch-regeneration\scripts\export_interim_csv.py --run $run

# 4) run summary + top reasons
python dexter_analysis_pitch-regeneration\scripts\summarize_run.py `
  --src "$run\raw\dexter_free_extraction.jsonl" `
  --out "$run\reports\run_summary.txt" `
  --write-top

# 5) slim views (filtering / splits)
python dexter_analysis_pitch-regeneration\scripts\export_slim_views.py `
  --src "$run\raw\dexter_free_extraction.jsonl" `
  --outdir "$run\slim" `
  --config dexter_analysis_pitch-regeneration\config\phaseA.yml

# 6) pre-embed metrics
python dexter_analysis_pitch-regeneration\scripts\pre_embed_metrics.py `
  --src "$run\slim\dexter_free_extraction_slim_reachable_conf05.csv" `
  --out "$run\reports\pre_embed_metrics.json" `
  --gk "$run\slim\dexter_free_extraction_slim_reachable_gk.csv" `
  --dm "$run\slim\dexter_free_extraction_slim_reachable_dm.csv"

# 7) embeddings (OpenAI)
python dexter_analysis_pitch-regeneration\scripts\embed_and_save.py `
  --src "$run\slim\dexter_free_extraction_slim_reachable_conf05.csv" `
  --outdir "$run" `
  --text-col auto `
  --workers 1

# 8) clustering (writes both clusters\<base>_clusters_pass1.csv and clusters_pass1.csv)
python dexter_analysis_pitch-regeneration\scripts\hdbscan_pass1.py `
  --run $run `
  --base dexter_free_extraction_slim_reachable_conf05 `
  --min-cluster-size 16 `
  --min-samples 5

# 9) join evidence quotes into a view + build per-cluster summaries (for naming)
python dexter_analysis_pitch-regeneration\scripts\post_clustering\build_clusters_view.py --run $run
python dexter_analysis_pitch-regeneration\scripts\post_clustering\build_cluster_summaries.py --run $run

# 10) OPTIONAL: ask AI to suggest names/definitions for clusters
python dexter_analysis_pitch-regeneration\scripts\post_clustering\name_clusters.py --run $run

# 11) PRODUCTION SHAPE: compress into a fixed number of buckets (top-K + Other)
python dexter_analysis_pitch-regeneration\scripts\post_clustering\build_limited_taxonomy.py `
  --run $run `
  --top-k 20 `
  --min-coverage 0.85

# 12) export labeled dataset using the limited mapping
python dexter_analysis_pitch-regeneration\scripts\post_clustering\export_discovery_labeled.py `
  --run $run `
  --base dexter_free_extraction_slim_reachable_conf05 `
  --map taxonomy\cluster_to_reason_label_limited.csv
```

## Quality thresholds
- JSON validity  98%
- reason == "unknown"  30% (observed ~23%)
- evidence substring mismatches  15% (observed ~2%)

## Notes / Limitations
- Transcripts are ASR; occasional noise/IVR. Evidence quotes are short and verbatim to reduce hallucinations.
- We bias toward the latest informative call for current status; history is used later at aggregation time.
- Unreachable markers are loaded from YAML (config/phaseA.yml) and applied when building REACHABLE views.
- row_id is sha1(phone|campaign_name|selected_call_started) for stable back-mapping.

## Next phases
- Embeddings + HDBSCAN  cluster labels & definitions  Taxonomy v1
- Phase B: classify all contacts with Taxonomy v1 (+ Other) and generate campaign-ready insights





## If clustering coverage is low (lots of outliers)

It’s normal for clustering to produce many “outliers” (cluster_id = -1) when the reasons are very diverse. For production (follow-up scripts), the recommended fix is **not** to chase every outlier into its own bucket, but to **compress** into a fixed number of buckets:

- Run `scripts/post_clustering/build_limited_taxonomy.py` with `--top-k` and/or `--min-coverage`
- Everything else becomes **R00 = Other** (long tail), which keeps the number of scripts manageable.

If you still want to explore the long tail (research mode), you can re-cluster only the outliers:

```powershell
@'
import csv, numpy as np
from pathlib import Path

run = Path(r"<PUT YOUR RUN FOLDER HERE>")
base = "dexter_free_extraction_slim_reachable_conf05"

vec = np.load(run / "vectors" / f"{base}_embeddings.npy")
with open(run / "vectors" / f"{base}_metadata.csv", encoding="utf-8") as f:
    meta_rows = list(csv.DictReader(f))
row_ids = [r["row_id"] for r in meta_rows]

labs = {}
with open(run / "clusters_pass1.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        labs[r["row_id"]] = int(r["cluster_id"])

keep_idx = [i for i, rid in enumerate(row_ids) if labs.get(rid, -1) == -1]
sub = vec[keep_idx, :]

new_base = base + "_outliers"
np.save(run / "vectors" / f"{new_base}_embeddings.npy", sub)

with open(run / "vectors" / f"{new_base}_metadata.csv", "w", newline="", encoding="utf-8") as g:
    wr = csv.writer(g)
    hdr = list(meta_rows[0].keys())
    wr.writerow(hdr)
    for i in keep_idx:
        wr.writerow([meta_rows[i][k] for k in hdr])

print(f"Outliers subset: {len(keep_idx)} vectors -> base={new_base}")
'@ | python
```