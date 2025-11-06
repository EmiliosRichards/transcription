# Dexter Calls  Phase A (Open-Ended Discovery)

## What is this?
Pipeline to discover call outcomes and failure reasons from transcripts without a predefined taxonomy, then prepare clean inputs for clustering  Taxonomy v1.

## Inputs
- data/transcription_dexter_analysis/inputs/dexter_calls_by_phone_campaign_final.jsonl (grouped calls per phone+campaign; transcripts in German)

## Outputs (per run)
- raw/dexter_free_extraction.jsonl  LLM annotations (outcome/reason/who/quote/conf)
- interim/dexter_free_extraction.csv  wide CSV for review
- slim/*.csv  short fields for embeddings & clustering
- reports/run_summary.txt  1-line summary per run
- reports/pre_embed_metrics.json  counts used to set clustering params

## Method (Phase A)
1. Most-recent informative call per phone+campaign.
2. LLM free extraction (English labels, German quote; substring-anchored).
3. QC & views: slim CSVs (ALL, REACHABLE, conf0.5, GK/DM splits) with stable row_id.
4. Pre-embed metrics: top reasons, GK/DM split, uniqueness & top-10 share.
5. (Next) Embeddings + HDBSCAN  cluster naming  Taxonomy v1.

## Reproduce (example)
`powershell
# 0) activate venv
. .venv/scripts/activate

# 1) run extraction (uses YAML for thresholds, markers, output_dir)
python data_pipelines_dexter\scripts\originals\extract_free_labels.py --config data_pipelines_dexter\config\phaseA.yml

# 2) summarize & create slim views
 = "data_pipelines_dexter\data\transcription_dexter_analysis\runs\2025-09-29"
python data_pipelines_dexter\scripts\summarize_run.py --src \raw\dexter_free_extraction.jsonl --out \reports\run_summary.txt --write-top
python data_pipelines_dexter\scripts\export_slim_views.py --src \raw\dexter_free_extraction.jsonl --outdir \slim --config data_pipelines_dexter\config\phaseA.yml

# 3) pre-embed metrics
python data_pipelines_dexter\scripts\pre_embed_metrics.py \
  --src \slim\dexter_free_extraction_slim_reachable_conf05.csv \
  --out \reports\pre_embed_metrics.json \
  --gk \slim\dexter_free_extraction_slim_reachable_gk.csv \
  --dm \slim\dexter_free_extraction_slim_reachable_dm.csv
`

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





## On <80% clustering coverage 
(.venv) PS C:\Users\emili\Projects\transcription> python data_pipelines_dexter\scripts\hdbscan_pass1.py `
>>   --run $run `
>>   --base dexter_free_extraction_slim_reachable_conf05 `
>>   --min-cluster-size 16 `
>>   --min-samples 5 `
>>   --prediction-data `
>>   --save-centroids `
>>   --append-report
C:\Users\emili\Projects\transcription\.venv\Lib\site-packages\sklearn\utils\deprecation.py:132: FutureWarning: 'force_all_finite' was renamed to 'ensure_all_finite' in 1.6 and will be removed in 1.8.
  warnings.warn(
C:\Users\emili\Projects\transcription\.venv\Lib\site-packages\sklearn\utils\deprecation.py:132: FutureWarning: 'force_all_finite' was renamed to 'ensure_all_finite' in 1.6 and will be removed in 1.8.
  warnings.warn(
HDBSCAN pass1 | total=1436 | coverage=56.7% | outlier_rate=43.3% | min_cluster_size_req=16 | min_samples_req=5 | min_cluster_size_used=16 | min_samples_used=5
Top clusters: [(4, 140), (3, 81), (2, 67), (14, 53), (12, 53), (5, 51), (16, 48), (0, 32), (18, 32), (8, 31)]
Wrote: data_pipelines_dexter\data\transcription_dexter_analysis\runs\2025-09-29\clusters_pass1.csv
Report: data_pipelines_dexter\data\transcription_dexter_analysis\runs\2025-09-29\reports\cluster_pass1.txt
(.venv) PS C:\Users\emili\Projects\transcription>


A) Create the outliers-only subset (new base)

@'
import csv, numpy as np
from pathlib import Path

run = Path(r"data_pipelines_dexter\data\transcription_dexter_analysis\runs\2025-09-29")
base = "dexter_free_extraction_slim_reachable_conf05"

# Load full set
vec = np.load(run / "vectors" / f"{base}_embeddings.npy")
with open(run / "vectors" / f"{base}_metadata.csv", encoding="utf-8") as f:
    meta_rows = list(csv.DictReader(f))
row_ids = [r["row_id"] for r in meta_rows]

# Read pass1 labels
labs = {}
with open(run / "clusters_pass1.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        labs[r["row_id"]] = int(r["cluster_id"])

# Keep -1 only
keep_idx = [i for i, rid in enumerate(row_ids) if labs.get(rid, -1) == -1]
sub = vec[keep_idx, :]

new_base = base + "_outliers"
np.save(run / "vectors" / f"{new_base}_embeddings.npy", sub)

# Write aligned metadata CSV
with open(run / "vectors" / f"{new_base}_metadata.csv", "w", newline="", encoding="utf-8") as g:
    wr = csv.writer(g)
    hdr = list(meta_rows[0].keys())
    wr.writerow(hdr)
    for i in keep_idx:
        wr.writerow([meta_rows[i][k] for k in hdr])

print(f"Outliers subset: {len(keep_idx)} vectors -> base={new_base}")
'@ | python