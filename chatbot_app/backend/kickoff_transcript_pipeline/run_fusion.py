import argparse
import json
import os
from pathlib import Path
from datetime import datetime
import time
import yaml

from src.pipeline.preflight import preflight_check, write_preflight_report
from src.pipeline.logging_utils import RunLogger, sha256_text
from src.pipeline.ingest.read_krisp import read_krisp_txt
from src.pipeline.ingest.read_charla import read_charla_txt
from src.pipeline.ingest.read_teams import read_teams_docx
from src.pipeline.ingest.read_teams_vtt import read_teams_vtt
from src.pipeline.align.align_segments import align_segments
from src.pipeline.fuse.map_speakers import map_speakers_via_alignment
from src.pipeline.export.write_master_docx import write_master_docx
from src.pipeline.blocks import partition_by_minutes, select_block
from src.pipeline.llm.responses_client import fuse_block_via_llm, cleanup_segments_via_llm
import statistics
import difflib


def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcript fusion pipeline (skeleton)")
    parser.add_argument("--config", required=True)
    parser.add_argument("--teams", help="Override path to Teams .docx")
    parser.add_argument("--krisp", help="Override path to Krisp .txt")
    parser.add_argument("--charla", help="Override path to Charla .txt")
    parser.add_argument("--use-charla", action="store_true", help="Include Charla in alignment/fusion if provided")
    parser.add_argument("--only-block", type=int, help="Run only the specified block index")
    parser.add_argument("--start-block", type=int, help="Start block index (inclusive)")
    parser.add_argument("--end-block", type=int, help="End block index (inclusive)")
    parser.add_argument("--skip-existing", action="store_true", help="Skip writing blocks that already exist")
    parser.add_argument("--fuse", action="store_true", help="Call LLM to fuse the selected blocks")
    parser.add_argument("--export-docx", action="store_true", help="Render master.docx for this run from master.txt")
    parser.add_argument("--run-dir", help="Optional: reuse a specific run directory under out/ instead of creating a new one")
    parser.add_argument("--extract-products", action="store_true", help="Run product extraction on master.txt using prompt_extract_product.md")
    parser.add_argument("--ref-json", help="Optional: path to reference transcript JSON with timestamped segments")
    parser.add_argument("--low-consensus-threshold", type=float, default=0.35, help="Threshold to flag low-consensus blocks")
    parser.add_argument("--temperature", type=float, help="Optional LLM temperature; if omitted, no temperature is sent")
    parser.add_argument("--glossary", type=str, help="Comma-separated static glossary terms (used as hints)")
    parser.add_argument("--include-context", action="store_true", help="Include prev/next context strings in payload meta (default: off)")
    parser.add_argument("--cleanup-enabled", action="store_true", help="Run AI wording cleanup sequentially")
    parser.add_argument("--cleanup-max-tokens", type=int, default=4000, help="Max tokens per cleanup batch (estimate)")
    parser.add_argument("--cleanup-concurrency", type=int, default=1, help="Number of cleanup batches to process in parallel per block")
    parser.add_argument("--cleanup-model", type=str, default="gpt-5-2025-08-07", help="LLM model for cleanup")
    parser.add_argument("--diagnostics", action="store_true", help="Write candidate selection diagnostics per block")
    # Global offset alignment flags
    parser.add_argument("--auto-offset-enabled", action="store_true", help="Enable global offset estimation and trimming for Krisp")
    parser.add_argument("--offset-adjust-gpt", action="store_true", help="Also rewrite GPT timestamps using the same offset (use with care)")
    parser.add_argument("--offset-min-phrase-tokens", type=int, default=2)
    parser.add_argument("--offset-max-phrase-tokens", type=int, default=5)
    parser.add_argument("--offset-similarity-threshold", type=float, default=0.70)
    parser.add_argument("--offset-expand-tokens", type=int, default=8)
    parser.add_argument("--offset-trim-pad-sec", type=int, default=2)
    args = parser.parse_args()

    config = load_config(Path(args.config))

    teams = Path(args.teams or config["inputs"]["teams"]).resolve()
    krisp = Path(args.krisp or config["inputs"]["krisp"]).resolve()
    # Only resolve Charla when explicitly enabled
    charla = None
    if getattr(args, "use_charla", False):
        c_src = None
        try:
            c_src = args.charla if getattr(args, "charla", None) else config.get("inputs", {}).get("charla")
        except Exception:
            c_src = None
        if c_src:
            try:
                charla = Path(c_src).resolve()
            except Exception:
                charla = None

    out_dir = Path(config["export"]["out_dir"]).resolve()
    if args.run_dir:
        run_dir = (out_dir / args.run_dir).resolve() if not Path(args.run_dir).is_absolute() else Path(args.run_dir).resolve()
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = out_dir / f"run_{timestamp}"
    log_path = run_dir / "run.jsonl"
    # Prepare LLM snapshot directory and expose via env for the LLM client
    try:
        snapshot_dir = run_dir / "llm"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        os.environ["LLM_SNAPSHOT_DIR"] = str(snapshot_dir)
    except Exception:
        # Non-fatal; snapshotting will be skipped if directory cannot be created
        pass
    logger = RunLogger(log_path)

    t0 = time.time()
    preflight_inputs = [teams, krisp]
    if charla:
        preflight_inputs.append(charla)
    ok, checks = preflight_check(preflight_inputs)
    write_preflight_report(out_dir, run_dir, checks)
    logger.log(
        "preflight",
        {
            "inputs": [c.__dict__ for c in checks],
            "duration_sec": round(time.time() - t0, 3),
        },
    )

    if not ok:
        logger.log("abort", {"reason": "preflight_failed"})
        print("Preflight failed. See preflight.json for details.")
        return 2

    logger.log("start_run", {"model": config.get("model"), "temperature": config.get("temperature"), "seed": config.get("seed"), "minutes_per_block": config.get("minutes_per_block")})
    logger.log(
        "tuning",
        {
            "filler_max_tokens": config.get("filler_max_tokens"),
            "duplicate_window_sec": config.get("duplicate_window_sec"),
            "low_conf_threshold": config.get("low_conf_threshold"),
            "similarity_threshold_high": config.get("similarity_threshold_high"),
            "similarity_threshold_low": config.get("similarity_threshold_low"),
            "confidence_weights": config.get("confidence_weights"),
        },
    )
    # Ingest segments
    t1 = time.time()
    k_segments = read_krisp_txt(krisp)
    c_segments = read_charla_txt(charla) if (args.use_charla and charla and Path(charla).exists()) else []
    if teams.suffix.lower() == ".vtt":
        t_segments = read_teams_vtt(teams)
    else:
        t_segments = read_teams_docx(teams)
    logger.log(
        "ingest",
        {
            "counts": {
                "krisp": len(k_segments),
                "charla": len(c_segments),
                "teams": len(t_segments),
            },
            "duration_sec": round(time.time() - t1, 3),
        },
    )

    # Prepare container for GPT reference sequence (possibly offset-adjusted)
    ref_seq_for_blocks: list[dict] | None = None

    # Optional: global offset alignment (pre-preamble trimming)
    if bool(getattr(args, "auto_offset_enabled", False)):
        try:
            from src.pipeline.align.estimate_global_offset import estimate_global_offset_and_bounds
            gpt_seq = []
            if args.ref_json and Path(args.ref_json).exists():
                try:
                    ref_all = json.loads(Path(args.ref_json).read_text(encoding="utf-8"))
                    if isinstance(ref_all, dict) and isinstance(ref_all.get("segments"), list):
                        gpt_seq = [
                            {"t_start": int(x.get("start") or x.get("t_start") or 0), "text": str(x.get("text", ""))}
                            for x in ref_all.get("segments", [])
                            if isinstance(x, dict) and str(x.get("text", "")).strip()
                        ]
                    elif isinstance(ref_all, list):
                        gpt_seq = [
                            {"t_start": int(x.get("start") or x.get("t_start") or 0), "text": str(x.get("text", ""))}
                            for x in ref_all
                            if isinstance(x, dict) and str(x.get("text", "")).strip()
                        ]
                except Exception:
                    gpt_seq = []
            teams_seq = [{"t_start": int(x.get("t_start") or 0), "text": str(x.get("text", ""))} for x in t_segments]
            krisp_seq = [{"t_start": int(x.get("t_start") or 0), "text": str(x.get("text", ""))} for x in k_segments]
            res = estimate_global_offset_and_bounds(
                teams_seq,
                krisp_seq,
                gpt_seq or None,
                min_phrase_tokens=int(args.offset_min_phrase_tokens),
                max_phrase_tokens=int(args.offset_max_phrase_tokens),
                similarity_threshold=float(args.offset_similarity_threshold),
                expand_tokens=int(args.offset_expand_tokens),
                end_similarity_threshold=max(0.58, float(args.offset_similarity_threshold) - 0.06),
                begin_lines_after=3,
                end_lines_after=4,
            )
            # apply offset to Krisp
            off = int(res.offset_sec or 0)
            pad = int(args.offset_trim_pad_sec)
            if off != 0:
                def _shift_keep(seg: dict) -> dict:
                    tt = int(seg.get("t_start") or 0) - off
                    seg2 = dict(seg)
                    seg2["t_start"] = max(0, tt)
                    return seg2
                # compute end bound if available
                end_bound = None
                if res.end_hit is not None:
                    end_bound = int(res.end_hit.teams_t + (res.offset_sec or 0) + pad)
                else:
                    # Fallback: if no end anchor, trim to last confident Krisp time plus pad
                    try:
                        last_krisp_t = max(int(s.get("t_start") or 0) for s in k_segments) if k_segments else None
                        if last_krisp_t is not None:
                            end_bound = last_krisp_t + pad
                    except Exception:
                        end_bound = None
                # filter segments outside bounds
                new_k: list[dict] = []
                for s in k_segments:
                    ts = int(s.get("t_start") or 0)
                    if ts < off - pad:
                        continue
                    if end_bound is not None and ts > end_bound:
                        continue
                    new_k.append(_shift_keep(s))
                k_segments = new_k
                # optionally apply to GPT (in-memory only)
                if bool(getattr(args, "offset_adjust_gpt", False)) and gpt_seq:
                    try:
                        for x in gpt_seq:
                            x["t_start"] = max(0, int(x.get("t_start") or 0) - off)
                    except Exception:
                        pass
            # expose adjusted GPT refs (if any) for block slicing later
            try:
                if gpt_seq:
                    ref_seq_for_blocks = list(gpt_seq)
            except Exception:
                pass
            # write diagnostics
            (run_dir / "offsets.json").write_text(json.dumps({
                "offset_sec": off,
                "begin": res.begin_hit.__dict__ if res.begin_hit else None,
                "end": res.end_hit.__dict__ if res.end_hit else None,
            }, indent=2), encoding="utf-8")
            (run_dir / "offset_diagnostics.json").write_text(json.dumps(res.diagnostics, indent=2), encoding="utf-8")
            logger.log("global_offset", {"offset_sec": off, "have_begin": bool(res.begin_hit), "have_end": bool(res.end_hit)})
        except Exception:
            pass

    # If no offset workflow populated GPT refs yet, but a ref file exists, read it now (no adjustment)
    if ref_seq_for_blocks is None and args.ref_json and Path(args.ref_json).exists():
        try:
            ref_all = json.loads(Path(args.ref_json).read_text(encoding="utf-8"))
            if isinstance(ref_all, dict) and isinstance(ref_all.get("segments"), list):
                seq_any = ref_all.get("segments")
            elif isinstance(ref_all, list):
                seq_any = ref_all
            else:
                seq_any = []
            seq_any_list: list = list(seq_any or [])
            tmp: list[dict] = []
            for x in seq_any_list:
                if not isinstance(x, dict):
                    continue
                ts = 0
                for k in ("t_start", "t", "start"):
                    if k in x:
                        try:
                            ts = int(round(float(x[k])))
                            break
                        except Exception:
                            continue
                txt = str(x.get("text", ""))
                if not txt.strip():
                    continue
                tmp.append({"t_start": ts, "text": txt})
            ref_seq_for_blocks = tmp
        except Exception:
            ref_seq_for_blocks = []

    # Optional: remove Krisp preamble not present in Teams (leading drift)
    def _has_overlap_with_teams(t: int, window: int = 12) -> bool:
        lo = t - window
        hi = t + window
        for ts in t_segments:
            tt = int(ts.get("t_start") or 0)
            if lo <= tt <= hi:
                return True
        return False

    removed = []
    kept = []
    started = False
    for seg in k_segments:
        ts = int(seg.get("t_start") or 0)
        if not started and not _has_overlap_with_teams(ts, window=20):
            removed.append(seg)
        else:
            started = True
            kept.append(seg)
    # Always write a report; write removed text only if any
    (run_dir / "preamble_report.json").write_text(json.dumps({"removed": len(removed), "kept": len(kept)}), encoding="utf-8")
    if removed:
        (run_dir / "preamble_removed_krisp.txt").write_text("\n".join([r.get("text","") for r in removed]), encoding="utf-8")
        k_segments = kept

    # Partition into blocks by Teams timeline (as base)
    minutes_per_block = int(config.get("minutes_per_block", 12))
    blocks = partition_by_minutes(t_segments, minutes_per_block)
    total_blocks = len(blocks)
    logger.log("partition", {"minutes_per_block": minutes_per_block, "total_blocks": total_blocks})

    # Determine block range
    if args.only_block is not None:
        start_idx = end_idx = max(0, min(args.only_block, total_blocks - 1))
    else:
        start_idx = max(0, int(args.start_block) if args.start_block is not None else 0)
        end_idx = min(total_blocks - 1, int(args.end_block) if args.end_block is not None else total_blocks - 1)

    # Write per-block stubs for downstream steps
    rolling_glossary: list[str] = []  # retained for backward compat; not used when static glossary is provided
    cleanup_summary: dict = {"enabled": bool(args.cleanup_enabled), "model": args.cleanup_model, "max_tokens": int(args.cleanup_max_tokens), "blocks": [], "total_batches": 0}
    for idx in range(start_idx, end_idx + 1):
        block = select_block(blocks, idx)  # Teams segments in this block
        block_path = run_dir / f"block_{idx:03d}.json"
        if args.skip_existing and block_path.exists():
            logger.log("skip_block", {"block_index": idx, "reason": "exists"})
            # Optionally still fuse if requested and fused file missing
            pass
        # Build Teams-anchored payload; limit other sources to this time window
        if len(block) > 0:
            block_start = int(block[0].get("t_start") or 0)
            block_end = int(block[-1].get("t_start") or block_start)
        else:
            block_start = 0
            block_end = 0
        teams_in_range = [t for t in t_segments if block_start - 5 <= int(t.get("t_start") or 0) <= block_end + 5]
        krisp_in_range = [k for k in k_segments if block_start - 30 <= int(k.get("t_start") or 0) <= block_end + 30]
        charla_in_range = [c for c in c_segments if block_start - 30 <= int(c.get("t_start") or 0) <= block_end + 30] if c_segments else []
        # Slice GPT-ref for this block if available
        ref_in_range: list[dict] = []
        if ref_seq_for_blocks:
            for r in ref_seq_for_blocks:
                try:
                    rt = int(r.get("t_start") or 0)
                except Exception:
                    rt = 0
                if (block_start - 15) <= rt <= (block_end + 15):
                    ref_in_range.append({"t_start": rt, "text": str(r.get("text", ""))})

        # --- Block-level offset estimation between Krisp and Teams ---
        # Use broad window to find nearest Teams for each Krisp and compute time deltas
        broad_win = 30
        deltas: list[int] = []
        t_times = [int(t.get("t_start") or 0) for t in teams_in_range]
        t_times.sort()

        def _nearest_teams_time(ts: int) -> int | None:
            if not t_times:
                return None
            # binary search nearest
            lo, hi = 0, len(t_times) - 1
            while lo < hi:
                mid = (lo + hi) // 2
                if t_times[mid] < ts:
                    lo = mid + 1
                else:
                    hi = mid
            cand_idx = lo
            best = t_times[cand_idx]
            if cand_idx > 0 and abs(t_times[cand_idx - 1] - ts) < abs(best - ts):
                best = t_times[cand_idx - 1]
            if cand_idx + 1 < len(t_times) and abs(t_times[cand_idx + 1] - ts) < abs(best - ts):
                best = t_times[cand_idx + 1]
            return best

        for k in krisp_in_range:
            kt = int(k.get("t_start") or 0)
            nt = _nearest_teams_time(kt)
            if nt is None:
                continue
            if abs(kt - nt) <= broad_win:
                deltas.append(kt - nt)

        median_delta = 0
        if len(deltas) >= 5:
            try:
                median_delta = int(round(statistics.median(deltas)))
            except Exception:
                median_delta = 0
        # Create shifted Krisp list for alignment matching (do not mutate originals)
        krisp_for_match: list[dict] = []
        if median_delta != 0:
            for k in krisp_in_range:
                ktmp = dict(k)
                ktmp["t_align"] = int(k.get("t_start") or 0) - median_delta
                krisp_for_match.append(ktmp)
        else:
            # still supply t_align identical to t_start for uniform logic
            for k in krisp_in_range:
                ktmp = dict(k)
                ktmp["t_align"] = int(k.get("t_start") or 0)
                krisp_for_match.append(ktmp)

        win = int(config.get("duplicate_window_sec", 4))
        win_strict = int(config.get("time_only_window_sec", 6))
        def _near(tref: int, lst: list[dict], w: int) -> list[dict]:
            out = []
            for it in lst:
                tt = int(it.get("t_align") or it.get("t_start") or it.get("t") or 0)
                if abs(tt - tref) <= w:
                    out.append(it)
            return out

        # --- Content similarity helpers (word/char order-aware) ---
        def _normalize_text(s: str) -> str:
            s2 = (s or "").lower()
            for ch in ",.!?:;·•—-\"'()[]{}\n\t":
                s2 = s2.replace(ch, " ")
            return " ".join(t for t in s2.split() if t)

        def _lcs_ratio(a: list[str], b: list[str]) -> float:
            if not a or not b:
                return 0.0
            na, nb = len(a), len(b)
            dp = [0] * (nb + 1)
            for i in range(1, na + 1):
                prev = 0
                for j in range(1, nb + 1):
                    tmp = dp[j]
                    if a[i - 1] == b[j - 1]:
                        dp[j] = prev + 1
                    else:
                        dp[j] = dp[j] if dp[j] >= dp[j - 1] else dp[j - 1]
                    prev = tmp
            lcs = dp[nb]
            return lcs / float(max(na, nb))

        def _content_similarity(a_text: str, b_text: str) -> float:
            a_norm = _normalize_text(a_text)
            b_norm = _normalize_text(b_text)
            if not a_norm or not b_norm:
                return 0.0
            char_ratio = difflib.SequenceMatcher(None, a_norm, b_norm).ratio()
            a_tok = a_norm.split()
            b_tok = b_norm.split()
            lcs_r = _lcs_ratio(a_tok, b_tok)
            return max(char_ratio, lcs_r)

        def _partial_phrase_match(a_text: str, b_text: str, min_tokens: int, threshold: float) -> bool:
            a_norm = _normalize_text(a_text)
            b_norm = _normalize_text(b_text)
            if not a_norm or not b_norm:
                return False
            a_tok = a_norm.split()
            b_tok = b_norm.split()
            if len(a_tok) < min_tokens:
                # fallback to full similarity for very short teams text
                return _content_similarity(a_text, b_text) >= threshold
            max_window = min(len(a_tok), max(min_tokens + 6, min_tokens))
            for w in range(min_tokens, max_window + 1):
                for i in range(0, len(a_tok) - w + 1):
                    phrase = a_tok[i : i + w]
                    # partial LCS ratio normalized by phrase length
                    lcs = _lcs_ratio(phrase, b_tok)
                    # _lcs_ratio returns normalized by max(len(phrase), len(b_tok)), but we want by len(phrase)
                    # Recompute quickly using dynamic programming only on phrase vs b_tok length via existing impl scaled
                    # Approximation: scale up by factor max(len(phrase), len(b_tok))/len(phrase)
                    scale = float(max(len(phrase), len(b_tok))) / float(len(phrase))
                    partial_score = lcs * scale
                    if partial_score >= threshold:
                        return True
            return False

        def _build_aligned(w: int) -> list[dict]:
            aligned: list[dict] = []
            team_ts = sorted([int(x.get("t_start") or 0) for x in teams_in_range])
            for tseg in sorted(teams_in_range, key=lambda x: int(x.get("t_start") or 0)):
                tref = int(tseg.get("t_start") or 0)
                # Midpoint boundary to avoid leaking GPT_ref into the next Teams segment
                next_ts_candidates = [ts for ts in team_ts if ts > tref]
                next_tref = next_ts_candidates[0] if next_ts_candidates else None
                boundary_mid = (tref + next_tref) // 2 if next_tref is not None else None
                # Stage 1: strict time-only window
                k_matches = _near(tref, krisp_for_match, win_strict)
                c_matches = _near(tref, charla_in_range, w) if c_segments else []
                # Gather GPT-ref candidates for this Teams ts
                g_candidates: list[dict] = []
                if ref_in_range:
                    # First try tight time window
                    tight_ref = [
                        r for r in ref_in_range
                        if abs(int(r.get("t_start") or 0) - tref) <= w
                        and (boundary_mid is None or int(r.get("t_start") or 0) <= boundary_mid)
                    ]
                    if tight_ref:
                        # Stitch adjacent tight refs and validate
                        tight_sorted_ref = sorted(tight_ref, key=lambda x: int(x.get("t_start") or 0))
                        g_tight_merged = " ".join(str(r.get("text", "")).strip() for r in tight_sorted_ref if str(r.get("text", "")).strip())
                        sim_threshold = float(config.get("per_segment_similarity_threshold", 0.66))
                        min_phrase = int(config.get("per_segment_min_phrase_tokens", 6))
                        if g_tight_merged and _partial_phrase_match(tseg.get("text", ""), g_tight_merged, min_phrase, sim_threshold):
                            g_candidates.append({"source": "gpt_ref", "t_start": tref, "text": g_tight_merged})
                        else:
                            # fallback to single items meeting similarity
                            for r in tight_sorted_ref:
                                if _content_similarity(tseg.get("text", ""), str(r.get("text", ""))) >= sim_threshold:
                                    g_candidates.append({"source": "gpt_ref", "t_start": int(r.get("t_start") or 0), "text": str(r.get("text", ""))})
                    else:
                        # broaden with similarity and optional stitching like Krisp
                        sim_threshold = float(config.get("per_segment_similarity_threshold", 0.66))
                        broad_band_ref = [
                            r for r in ref_in_range
                            if abs(int(r.get("t_start") or 0) - tref) <= broad_win
                            and (boundary_mid is None or int(r.get("t_start") or 0) <= boundary_mid)
                        ]
                        broad_sorted_ref = sorted(broad_band_ref, key=lambda x: int(x.get("t_start") or 0))
                        g_broad_merged = " ".join(str(r.get("text", "")).strip() for r in broad_sorted_ref if str(r.get("text", "")).strip())
                        min_phrase = int(config.get("per_segment_min_phrase_tokens", 6))
                        if g_broad_merged and _partial_phrase_match(tseg.get("text", ""), g_broad_merged, min_phrase, sim_threshold):
                            g_candidates.append({"source": "gpt_ref", "t_start": tref, "text": g_broad_merged})
                        else:
                            g_broaden: list[dict] = []
                            for r in broad_sorted_ref:
                                if _content_similarity(tseg.get("text", ""), str(r.get("text", ""))) >= sim_threshold:
                                    g_broaden.append({"source": "gpt_ref", "t_start": int(r.get("t_start") or 0), "text": str(r.get("text", ""))})
                            # dedupe by text
                            seen_g = set()
                            for m in g_broaden:
                                key = m.get("text", "")
                                if key not in seen_g:
                                    seen_g.add(key)
                                    g_candidates.append(m)
                # remove helper field before passing downstream
                k_clean = []
                for m in k_matches:
                    m2 = dict(m)
                    m2.pop("t_align", None)
                    k_clean.append(m2)
                # Step 1: if time-window matches exist, keep them as-is (original behavior)
                if k_clean:
                    aligned.append({"t": tseg, "k_all": k_clean, "c_all": c_matches, "g_all": g_candidates})
                    continue
                # Step 2 & 3: tight/broad fallback with similarity and stitching
                sim_threshold = float(config.get("per_segment_similarity_threshold", 0.66))
                min_phrase = int(config.get("per_segment_min_phrase_tokens", 6))
                # Tight window similarity+stitching
                tight_band = [m for m in krisp_for_match if abs(int(m.get("t_align") or m.get("t_start") or 0) - tref) <= w]
                tight_sorted = sorted(tight_band, key=lambda x: int(x.get("t_align") or x.get("t_start") or 0))
                chosen: list[dict] = []
                if tight_sorted:
                    tight_merged = " ".join(str(m.get("text", "")).strip() for m in tight_sorted if str(m.get("text", "")).strip())
                    if tight_merged and _partial_phrase_match(tseg.get("text", ""), tight_merged, min_phrase, sim_threshold):
                        chosen.append({"source": "krisp", "t_start": tref, "t_end": None, "speaker": tseg.get("speaker", ""), "text": tight_merged, "tokens": None})
                    else:
                        for m in tight_sorted:
                            if _content_similarity(tseg.get("text", ""), m.get("text", "")) >= sim_threshold:
                                m2 = dict(m)
                                m2.pop("t_align", None)
                                chosen.append(m2)
                # Broad window with similarity and optional stitching if still empty
                if not chosen:
                    band = [m for m in krisp_for_match if abs(int(m.get("t_align") or m.get("t_start") or 0) - tref) <= broad_win]
                    band_sorted = sorted(band, key=lambda x: int(x.get("t_align") or x.get("t_start") or 0))
                    merged_text = " ".join(str(m.get("text", "")).strip() for m in band_sorted if str(m.get("text", "")).strip())
                    if merged_text and _partial_phrase_match(tseg.get("text", ""), merged_text, min_phrase, sim_threshold):
                        chosen.append({"source": "krisp", "t_start": tref, "t_end": None, "speaker": tseg.get("speaker", ""), "text": merged_text, "tokens": None})
                    else:
                        broaden: list[dict] = []
                        for m in band_sorted:
                            if _content_similarity(tseg.get("text", ""), m.get("text", "")) >= sim_threshold:
                                m2 = dict(m)
                                m2.pop("t_align", None)
                                broaden.append(m2)
                        # dedupe by text
                        seen = set()
                        for m in broaden:
                            key = m.get("text", "")
                            if key not in seen:
                                seen.add(key)
                                chosen.append(m)
                aligned.append({"t": tseg, "k_all": chosen, "c_all": c_matches, "g_all": g_candidates})
            return aligned

        aligned_teams: list[dict] = _build_aligned(win)

        # Adaptive widen: if too sparse Krisp matches, widen window and retry
        total_items = max(1, len(aligned_teams))
        segments_with_krisp = sum(1 for a in aligned_teams if a.get("k_all"))
        if segments_with_krisp / total_items < 0.2:
            widened = max(win, 12)
            aligned_teams = _build_aligned(widened)
            logger.log("align_adaptive_widen", {"block_index": idx, "median_delta": median_delta, "win_initial": win, "win_used": widened})
        else:
            logger.log("align_offset", {"block_index": idx, "median_delta": median_delta, "win_used": win})

        k_with_names = krisp_in_range  # Teams carries speakers; Krisp text used for wording only
        block_payload = {
            "teams_base": True,
            "aligned": aligned_teams,
            "krisp": k_with_names,
        }

        # Include GPT-ref slice for this block if available (always include key when ref sequence exists)
        if ref_seq_for_blocks is not None:
            try:
                print(f"[fusion] ref slice block={idx+1} total_ref={len(ref_seq_for_blocks)} in_range={len(ref_in_range)}", flush=True)
            except Exception:
                pass
            block_payload["ref"] = ref_in_range

        # Add simple consensus hint scores (token overlap ratios)
        def _tokenize(s: str) -> set:
            return set([w.lower() for w in s.split() if w and w.isascii()])
        kr_text = " ".join([x.get("text","") for x in k_with_names])
        tm_text = " ".join([x.get("text","") for x in teams_in_range])
        kr_vs_tm = 0.0
        if kr_text and tm_text:
            a = _tokenize(kr_text)
            b = _tokenize(tm_text)
            inter = len(a & b)
            uni = max(1, len(a | b))
            kr_vs_tm = inter / uni
        kr_vs_ref = None
        if block_payload.get("ref"):
            ref_text = " ".join([x.get("text","") for x in block_payload.get("ref", [])])
            if ref_text:
                a = _tokenize(kr_text)
                b = _tokenize(ref_text)
                inter = len(a & b)
                uni = max(1, len(a | b))
                kr_vs_ref = inter / uni
        block_payload["consensus_hint"] = {"kr_vs_tm": kr_vs_tm, "kr_vs_ref": kr_vs_ref, "low_consensus_threshold": float(args.low_consensus_threshold)}
        block_path.write_text(json.dumps(block_payload, indent=2), encoding="utf-8")
        logger.log("write_block", {"block_index": idx, "teams_count": len(teams_in_range)})
        # Diagnostics: capture candidate selection rationale when enabled
        if bool(getattr(args, "diagnostics", False)):
            try:
                diag = {
                    "block_index": idx,
                    "win_strict": win_strict,
                    "win_similarity": win,
                    "broad_win": broad_win,
                    "median_delta": median_delta,
                    "per_segment_similarity_threshold": float(config.get("per_segment_similarity_threshold", 0.66)),
                    "per_segment_min_phrase_tokens": int(config.get("per_segment_min_phrase_tokens", 6)),
                    "segments": [],
                }
                for a in aligned_teams:
                    tseg = a.get("t", {})
                    tref = int(tseg.get("t_start") or 0)
                    t_text = str(tseg.get("text", ""))
                    # --- Krisp diagnostics ---
                    # collect bands
                    k_strict = [
                        {"t": int(m.get("t_start") or 0), "text": str(m.get("text", ""))[:200]}
                        for m in krisp_in_range
                        if abs(int(m.get("t_start") or 0) - tref) <= win_strict
                    ]
                    k_tight = [
                        {"t": int(m.get("t_start") or 0), "text": str(m.get("text", ""))[:200]}
                        for m in krisp_in_range
                        if abs(int(m.get("t_start") or 0) - tref) <= win
                    ]
                    k_broad = [
                        {"t": int(m.get("t_start") or 0), "text": str(m.get("text", ""))[:200]}
                        for m in krisp_in_range
                        if abs(int(m.get("t_start") or 0) - tref) <= broad_win
                    ]
                    # selected from pipeline output
                    k_selected = [
                        {"t": int(k.get("t_start") or 0), "text": str(k.get("text", ""))[:200]}
                        for k in a.get("k_all", [])
                    ]
                    # attempt to classify stage and whether stitch matched
                    sim_th = float(config.get("per_segment_similarity_threshold", 0.66))
                    min_phrase = int(config.get("per_segment_min_phrase_tokens", 6))
                    # tight merge
                    tight_band = [m for m in krisp_in_range if abs(int(m.get("t_start") or 0) - tref) <= win]
                    tight_merge = " ".join(str(m.get("text", "")).strip() for m in sorted(tight_band, key=lambda x: int(x.get("t_start") or 0)))
                    tight_stitch_ok = bool(tight_merge and _partial_phrase_match(t_text, tight_merge, min_phrase, sim_th))
                    # broad merge
                    broad_band = [m for m in krisp_in_range if abs(int(m.get("t_start") or 0) - tref) <= broad_win]
                    broad_merge = " ".join(str(m.get("text", "")).strip() for m in sorted(broad_band, key=lambda x: int(x.get("t_start") or 0)))
                    broad_stitch_ok = bool(broad_merge and _partial_phrase_match(t_text, broad_merge, min_phrase, sim_th))

                    # --- GPT-ref diagnostics ---
                    g_tight_refs = []
                    g_broad_refs = []
                    g_selected = []
                    g_tight_stitched_ok = False
                    g_broad_stitched_ok = False
                    if 'ref' in block_payload and block_payload['ref']:
                        for r in block_payload['ref']:
                            rt = int(r.get("t_start") or 0)
                            entry = {"t": rt, "text": str(r.get("text", ""))[:200]}
                            if abs(rt - tref) <= win:
                                g_tight_refs.append(entry)
                            elif abs(rt - tref) <= broad_win:
                                g_broad_refs.append(entry)
                        # stitched flags
                        if g_tight_refs:
                            g_tight_merge = " ".join(e["text"].strip() for e in sorted(g_tight_refs, key=lambda x: x["t"]))
                            g_tight_stitched_ok = bool(g_tight_merge and _partial_phrase_match(t_text, g_tight_merge, min_phrase, sim_th))
                        if g_broad_refs:
                            g_broad_merge = " ".join(e["text"].strip() for e in sorted(g_broad_refs, key=lambda x: x["t"]))
                            g_broad_stitched_ok = bool(g_broad_merge and _partial_phrase_match(t_text, g_broad_merge, min_phrase, sim_th))
                        # recompute selected per logic
                        if g_tight_refs:
                            g_selected = [e for e in g_tight_refs]
                        else:
                            # broad with similarity
                            for e in g_broad_refs:
                                if _content_similarity(t_text, e["text"]) >= sim_th:
                                    g_selected.append(e)

                    diag["segments"].append({
                        "t_start": tref,
                        "speaker": tseg.get("speaker", ""),
                        "teams_text": t_text[:200],
                        "krisp": {
                            "strict_refs": k_strict,
                            "tight_refs": k_tight,
                            "broad_refs": k_broad,
                            "tight_stitched_ok": tight_stitch_ok,
                            "broad_stitched_ok": broad_stitch_ok,
                            "selected": k_selected,
                        },
                        "gpt_ref": {
                            "tight_refs": g_tight_refs,
                            "broad_refs": g_broad_refs,
                            "tight_stitched_ok": g_tight_stitched_ok,
                            "broad_stitched_ok": g_broad_stitched_ok,
                            "selected": g_selected,
                        },
                    })
                (run_dir / f"diagnostics_block_{idx:03d}.json").write_text(json.dumps(diag, indent=2), encoding="utf-8")
            except Exception:
                pass

        if args.cleanup_enabled:
            # Prepare cleanup batches anchored to Teams; do not split a Teams segment
            # Simple token estimate: len(text)//4 per segment, plus overhead
            def _estimate_tokens(seg_list: list[dict]) -> int:
                total = 200  # system + overhead
                for s in seg_list:
                    ttxt = str(s.get("t", {}).get("text", ""))
                    gtxt = " ".join([alt.get("text", "") for alt in s.get("g", [])])
                    ktxt = " ".join([alt.get("text", "") for alt in s.get("k", [])])
                    total += (len(ttxt) + len(gtxt) + len(ktxt)) // 4
                return total

            # Build normalized items for batching (canonical per-Teams segment with candidate texts)
            items = []
            for a in aligned_teams:
                tseg = a.get("t", {})
                tref = int(tseg.get("t_start") or 0)
                # GPT reference texts near this Teams timestamp (respect midpoint boundary)
                g_texts: list[str] = []
                # compute midpoint boundary to avoid leaking into next Teams segment
                next_ts_candidates = [int(x.get("t_start") or 0) for x in teams_in_range if int(x.get("t_start") or 0) > tref]
                next_tref = min(next_ts_candidates) if next_ts_candidates else None
                boundary_mid = (tref + next_tref) // 2 if next_tref is not None else None
                # Prefer stitched/selected GPT_ref built during alignment (g_all)
                try:
                    gal = a.get("g_all", [])
                    if isinstance(gal, list) and gal:
                        for g in gal:
                            txt = str(g.get("text", ""))
                            if txt:
                                g_texts.append(txt)
                except Exception:
                    pass
                # Fallback to direct ref slice logic if g_all is empty
                if not g_texts and block_payload.get("ref"):
                    sim_threshold = float(config.get("per_segment_similarity_threshold", 0.66))
                    tight_any = any(abs(int(r.get("t_start") or 0) - tref) <= win and (boundary_mid is None or int(r.get("t_start") or 0) <= boundary_mid) for r in block_payload.get("ref", []))
                    if tight_any:
                        tight_sorted_ref = sorted([
                            r for r in block_payload.get("ref", [])
                            if abs(int(r.get("t_start") or 0) - tref) <= win and (boundary_mid is None or int(r.get("t_start") or 0) <= boundary_mid)
                        ], key=lambda x: int(x.get("t_start") or 0))
                        # Try stitched merged first
                        g_tight_merged = " ".join(str(r.get("text", "")).strip() for r in tight_sorted_ref if str(r.get("text", "")).strip())
                        min_phrase = int(config.get("per_segment_min_phrase_tokens", 6))
                        if g_tight_merged and _partial_phrase_match(tseg.get("text", ""), g_tight_merged, min_phrase, sim_threshold):
                            g_texts.append(g_tight_merged)
                        else:
                            for r in tight_sorted_ref:
                                txt = str(r.get("text", ""))
                                if _content_similarity(tseg.get("text", ""), txt) >= sim_threshold:
                                    g_texts.append(txt)
                    else:
                        # Broad window with stitching and high-sim fallbacks
                        broad_sorted_ref = sorted([
                            r for r in block_payload.get("ref", [])
                            if abs(int(r.get("t_start") or 0) - tref) <= broad_win and (boundary_mid is None or int(r.get("t_start") or 0) <= boundary_mid)
                        ], key=lambda x: int(x.get("t_start") or 0))
                        g_broad_merged = " ".join(str(r.get("text", "")).strip() for r in broad_sorted_ref if str(r.get("text", "")).strip())
                        min_phrase = int(config.get("per_segment_min_phrase_tokens", 6))
                        if g_broad_merged and _partial_phrase_match(tseg.get("text", ""), g_broad_merged, min_phrase, sim_threshold):
                            g_texts.append(g_broad_merged)
                        else:
                            broaden_matches: list[str] = []
                            for r in broad_sorted_ref:
                                txt = str(r.get("text", ""))
                                if _content_similarity(tseg.get("text", ""), txt) >= sim_threshold:
                                    broaden_matches.append(txt)
                            if broaden_matches:
                                seen = set(); g_texts = []
                                for s in broaden_matches:
                                    if s not in seen:
                                        seen.add(s); g_texts.append(s)
                # Krisp texts already aligned for this Teams segment
                k_texts: list[str] = [str(k.get("text", "")) for k in a.get("k_all", [])]
                items.append({
                    "teams": {"t_start": tref, "speaker": tseg.get("speaker", ""), "text": tseg.get("text", "")},
                    "g_texts": g_texts,
                    "k_texts": k_texts,
                })

            batches: list[list[dict]] = []
            cur: list[dict] = []
            cur_tokens = 0
            for it in items:
                est = (len(it["teams"]["text"]) + sum(len(x) for x in it.get("g_texts", [])) + sum(len(x) for x in it.get("k_texts", []))) // 4 + 25
                if cur and (cur_tokens + est) > int(args.cleanup_max_tokens):
                    batches.append(cur)
                    cur = []
                    cur_tokens = 0
                cur.append(it)
                cur_tokens += est
            if cur:
                batches.append(cur)

            print(f"[fusion] cleanup block {idx+1}/{total_blocks} - batching...", flush=True)
            cleaned_lines: list[str] = []
            issues_accum: list[dict] = []
            prev_cleaned_tail: list[dict] = []  # rolling cache of last 1–2 cleaned segments

            # --- Parallel or sequential batch processing ---
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _process_one_batch(bidx: int, batch: list[dict], use_tail: bool) -> tuple[int, list[str], list[dict], str | None]:
                system_prompt = (
                    "You improve wording in call transcripts WITHOUT altering structure.\n\n"
                    "Hard rules:\n"
                    "1) You MUST return JSON matching the schema:\n"
                    "   {\n"
                    "     \"cleaned_segments\":[{\"t_start\":number,\"speaker\":string,\"text\":string}],\n"
                    "     \"issues\"?: [{\"t_start\":number,\"type\":string,\"detail\":string}],\n"
                    "     \"qa_notes\"?: string\n"
                    "   }\n"
                    "2) The number of cleaned_segments MUST equal the number of input segments.\n"
                    "3) For each index i: cleaned_segments[i].t_start == input.segments[i].t_start AND\n"
                    "   cleaned_segments[i].speaker == input.segments[i].speaker. NO CHANGES ALLOWED.\n"
                    "4) Improve ONLY the \"text\": keep natural human speech; do NOT sanitize heavily.\n"
                    "5) Use evidence from Teams (anchor), Krisp, and GPT_ref candidates + the static glossary.\n"
                    "   - Prefer terms from glossary_static when plausible.\n"
                    "   - If evidence conflicts (e.g., \"Dexter/Dextra/Texten\"), pick the most plausible based on\n"
                    "     local context, BUT if still uncertain, keep the Teams form AND add an entry in \"issues\".\n"
                    "6) Do NOT merge, split, add, or drop segments. Do NOT invent timestamps or speakers.\n"
                    "7) Preserve language conventions (e.g., German capitalization, abbreviations like ERP, PDL).\n"
                    "8) Return ONLY the JSON. No prose outside JSON.\n"
                    "9) If no candidates (Krisp/GPT_ref) are provided for a segment, only correct an obvious single-word error when context makes the alternative highly probable; otherwise keep the Teams text exactly as-is.\n"
                    "10) Inputs may mix German and English words or phonetic spellings; prefer consistent, correct language usage but keep semantics.\n"
                    "10) Candidate snippets from Krisp/GPT_ref are approximate and may include a few extra words before or after the core phrase; treat them as noisy hints and prioritize the Teams anchor when uncertain.\n"
                )
                # Build canonical payload per requested contract
                def _context_text(source: list[dict], center_t: int, direction: str) -> str:
                    if not source:
                        return ""
                    if direction == "prev":
                        neighbors = [s for s in teams_in_range if int(s.get("t_start") or 0) < center_t]
                        neighbors = neighbors[-5:]
                    else:
                        neighbors = [s for s in teams_in_range if int(s.get("t_start") or 0) > center_t]
                        neighbors = neighbors[:5]
                    return (" ".join([str(s.get("text", "")) for s in neighbors]))[:250]

                # Identify filler-only segments (skip sending them to LLM to save tokens)
                filler_tokens = {"hm", "hmm", "mhm", "mmh", "ja", "okay", "ok", "mhm,", "hm,", "ja.", "ok."}
                def _is_filler_only(txt: str) -> bool:
                    s = (txt or "").lower()
                    # strip simple punctuation
                    for ch in ",.!?:;·•—-\"'()[]{}":
                        s = s.replace(ch, " ")
                    toks = [t for t in s.split() if t]
                    if not toks:
                        return True
                    return all(t in filler_tokens for t in toks) and len(toks) <= 4

                # --- Candidate prefilter and length-aware trimming helpers ---
                import re

                def _word_spans(text: str) -> list[tuple[int, int, str]]:
                    spans: list[tuple[int, int, str]] = []
                    for m in re.finditer(r"\w+", text, flags=re.UNICODE):
                        spans.append((m.start(), m.end(), text[m.start():m.end()].lower()))
                    return spans

                courtesy_tokens = {
                    "dank", "danke", "vielen", "vielen", "dankeschön", "thank", "thanks",
                    "ähm", "ahm", "uhm", "hm", "hmm", "mhm", "mmh", "ja", "okay", "ok"
                }

                def _strip_courtesy_edges(text: str) -> str:
                    s = text or ""
                    spans = _word_spans(s)
                    if not spans:
                        return s.strip()
                    i = 0
                    j = len(spans)
                    # trim from left
                    while i < j and spans[i][2] in courtesy_tokens:
                        i += 1
                    # trim from right
                    while i < j and spans[j - 1][2] in courtesy_tokens:
                        j -= 1
                    if i >= j:
                        return ""
                    start = spans[i][0]
                    end = spans[j - 1][1]
                    return s[start:end].strip()

                def _best_subspan_with_buffer(candidate_text: str, teams_text: str, trim_window_words: int, min_kept_tokens: int, pre_buffer: int, post_buffer: int) -> str:
                    s = candidate_text or ""
                    spans = _word_spans(s)
                    ttoks = _normalize_text(teams_text or "").split()
                    L = len(ttoks)
                    if not spans:
                        return s.strip()
                    # bounds
                    lb = max(min_kept_tokens, L - int(trim_window_words))
                    ub = max(lb, L + int(trim_window_words))
                    N = len(spans)
                    # If candidate already short, keep as-is
                    if N <= ub:
                        # still allow small buffer if available
                        i0 = 0
                        j0 = N
                        i0 = max(0, i0 - pre_buffer)
                        j0 = min(N, j0 + post_buffer)
                        start = spans[i0][0]
                        end = spans[j0 - 1][1]
                        return s[start:end].strip()
                    # Search best window
                    best_i = 0
                    best_j = min(N, ub)
                    best_score = -1.0
                    # Build a helper to join tokens from spans for scoring
                    words = [s[a:b] for (a, b, _) in spans]
                    for length in range(lb, min(ub, N) + 1):
                        for i in range(0, N - length + 1):
                            j = i + length
                            cand = " ".join(words[i:j])
                            score = _content_similarity(teams_text, cand)
                            if score > best_score:
                                best_score = score
                                best_i, best_j = i, j
                    # apply buffer
                    pre = min(pre_buffer, best_i)
                    post = min(post_buffer, N - best_j)
                    i2 = best_i - pre
                    j2 = best_j + post
                    start = spans[i2][0]
                    end = spans[j2 - 1][1]
                    return s[start:end].strip()

                send_mask: list[bool] = []
                segments_payload = []
                for it in batch:
                    tinfo = it.get("teams", {})
                    t_start_v = int(tinfo.get("t_start") or 0)
                    t_text_v = tinfo.get("text", "")
                    is_fill = _is_filler_only(t_text_v)
                    send_mask.append(not is_fill)
                # Defaults to avoid UnboundLocalError if code structure changes
                k_proc: list[str] = []
                g_proc: list[str] = []
                    if not is_fill:
                        # Prepare Krisp/GPT candidates: courtesy-edge strip + best-subspan trimming
                        trim_window_words = int(config.get("trim_window_words", 5))
                        min_kept_tokens = int(config.get("trim_min_kept_tokens", 4))
                        pre_buffer = int(config.get("trim_pre_buffer_tokens", 3))
                        post_buffer = int(config.get("trim_post_buffer_tokens", 3))
                        min_similarity_floor = float(config.get("min_candidate_similarity_floor", 0.45))
                        short_anchor_terms = {"so", "ja", "okay", "ok", "hm", "hmm", "mhm", "mmh", "ähm", "ahm", "uhm"}

                        def _prep_list(cands: list[str]) -> list[str]:
                            out: list[str] = []
                            seen: set[str] = set()
                            for raw in cands or []:
                                base = _strip_courtesy_edges(str(raw))
                                if not base:
                                    continue
                                # choose subspan only if longer than Teams length window
                                base_spans = _word_spans(base)
                                ttoks_len = len(_normalize_text(t_text_v).split())
                                if len(base_spans) > (ttoks_len + trim_window_words):
                                    trimmed = _best_subspan_with_buffer(base, t_text_v, trim_window_words, min_kept_tokens, pre_buffer, post_buffer)
                                else:
                                    # keep as-is (already short), but still apply small buffer implicitly via as-is
                                    trimmed = base
                                trimmed = trimmed.strip()
                                # similarity floor to avoid unrelated picks
                                if trimmed and _content_similarity(t_text_v, trimmed) < min_similarity_floor:
                                    continue
                                if trimmed and trimmed not in seen:
                                    seen.add(trimmed)
                                    out.append(trimmed)
                            return out

                        # For very short anchors like "So.", avoid attaching long, unrelated candidates
                        ttoks_norm = _normalize_text(t_text_v).split()
                        if (len(ttoks_norm) <= 1 and (ttoks_norm[0] if ttoks_norm else "") in short_anchor_terms) or (0 < len(ttoks_norm) <= 2 and all(t in short_anchor_terms for t in ttoks_norm)):
                            k_proc = []
                            g_proc = []
                        else:
                            k_proc = _prep_list(list(it.get("k_texts", [])))
                            g_proc = _prep_list(list(it.get("g_texts", [])))
                if not is_fill:
                    segments_payload.append({
                        "t_start": t_start_v,
                        "speaker": tinfo.get("speaker", ""),
                        "teams_text": t_text_v,
                        "candidates": {
                            "krisp": k_proc,
                            "gpt_ref": g_proc,
                        },
                    })

                # Determine static glossary from CLI, else config
                static_glossary = []
                try:
                    if getattr(args, "glossary", None):
                        static_glossary = [s.strip() for s in str(args.glossary).split(",") if s.strip()]
                    else:
                        static_glossary = list(config.get("glossary_static", []))
                except Exception:
                    static_glossary = []

                # Fallback for prev_cleaned_tail: use raw Teams segments if cleaned not available (parallel mode)
                tail_for_context: list[dict] = []
                if use_tail and prev_cleaned_tail:
                    tail_for_context = prev_cleaned_tail[-2:]
                elif batch:
                    # Use last 1–2 raw Teams segments before this batch (stitch to ~8+ words if needed)
                    first_t = int(batch[0]["teams"]["t_start"])
                    prior = [s for s in teams_in_range if int(s.get("t_start") or 0) < first_t]
                    if prior:
                        prior_sorted = sorted(prior, key=lambda x: int(x.get("t_start") or 0))
                        tail_candidates = prior_sorted[-3:]  # take last 3 to build ~8+ words
                        merged_text = " ".join(str(s.get("text", "")).strip() for s in tail_candidates).strip()
                        merged_words = merged_text.split()
                        if len(merged_words) >= 8:
                            # use last 2 segments
                            tail_for_context = [
                                {"t_start": int(s.get("t_start") or 0), "speaker": str(s.get("speaker", "")), "text": str(s.get("text", ""))}
                                for s in prior_sorted[-2:]
                            ]
                        elif len(merged_words) >= 4:
                            # use last 1 segment if at least 4 words
                            tail_for_context = [
                                {"t_start": int(prior_sorted[-1].get("t_start") or 0), "speaker": str(prior_sorted[-1].get("speaker", "")), "text": str(prior_sorted[-1].get("text", ""))}
                            ]
                payload = {
                    "glossary_static": static_glossary,
                    "language": str(config.get("language", "de")),
                    "segments": segments_payload,
                    "meta": {
                        "session_id": run_dir.name,
                        "chunk_index": idx,
                        "chunk_count": total_blocks,
                        "prev_tail_context": _context_text(teams_in_range, int(batch[0]["teams"]["t_start"]) if batch else 0, "prev"),
                        "next_head_context": _context_text(teams_in_range, int(batch[-1]["teams"]["t_start"]) if batch else 0, "next"),
                    },
                    "context": {
                        # Read-only continuity, not counted toward SEGMENT_COUNT
                        "prev_cleaned_tail": tail_for_context,
                    },
                }
                print(f"[fusion] cleanup block {idx+1}/{total_blocks} batch {bidx+1}/{len(batches)}", flush=True)
                # Use temperature only if provided via CLI or config; otherwise omit
                temp_cfg = args.temperature if getattr(args, "temperature", None) is not None else config.get("temperature", None)
                temp_val = float(temp_cfg) if isinstance(temp_cfg, (int, float, str)) and str(temp_cfg).strip() != "" else None
                resp = cleanup_segments_via_llm(payload, args.cleanup_model, temp_val, system_prompt)  # type: ignore[arg-type]
                parsed = None
                raw = resp.get("raw") if isinstance(resp, dict) else None
                if isinstance(raw, str):
                    try:
                        parsed = json.loads(raw)
                    except Exception:
                        parsed = None
                # Post-LLM validator with one auto-retry on failure
                def _validate_output(inp: list[dict], outp: dict | None) -> tuple[bool, str]:
                    if not isinstance(outp, dict):
                        return False, "Output not a JSON object"
                    cleaned = outp.get("cleaned_segments")
                    if not isinstance(cleaned, list):
                        return False, "cleaned_segments missing or not an array"
                    if len(cleaned) != len(inp):
                        return False, f"Segment count mismatch: expected {len(inp)}, got {len(cleaned)}"
                    for i, (ins, outs) in enumerate(zip(inp, cleaned)):
                        try:
                            t_in = int(ins.get("teams", {}).get("t_start") or 0)
                            s_in = str(ins.get("teams", {}).get("speaker", ""))
                            t_out = int(outs.get("t_start"))
                            s_out = str(outs.get("speaker"))
                        except Exception:
                            return False, f"Row {i}: invalid types for t_start/speaker"
                        if t_in != t_out or s_in != s_out:
                            return False, f"Row {i}: t_start/speaker changed"
                        if not isinstance(outs.get("text", ""), str):
                            return False, f"Row {i}: text not string"
                    return True, "ok"

                # Validate against the number of non-filler items only
                ok, reason = _validate_output([it for it, send in zip(batch, send_mask) if send], parsed)
                if not ok:
                    retry_hint = (
                        f"Your previous output violated rules: {reason}.\n"
                        f"Return the SAME number of segments ({len([1 for s in send_mask if s])}); copy t_start and speaker exactly.\n"
                        "Output JSON ONLY. No commentary."
                    )
                    resp = cleanup_segments_via_llm(payload, args.cleanup_model, temp_val, system_prompt, retry_hint)  # type: ignore[arg-type]
                    raw = resp.get("raw") if isinstance(resp, dict) else None
                    parsed = None
                    if isinstance(raw, str):
                        try:
                            parsed = json.loads(raw)
                        except Exception:
                            parsed = None
                out_lines: list[str] = []
                out_issues: list[dict] = []
                if isinstance(parsed, dict) and isinstance(parsed.get("cleaned_segments"), list):
                    # Update glossary (cap 50)
                    # Retire dynamic glossary updates; collect issues instead
                    try:
                        if isinstance(parsed.get("issues"), list):
                            for it in parsed.get("issues", []):
                                if isinstance(it, dict):
                                    out_issues.append({
                                        "t_start": int(it.get("t_start") or 0),
                                        "type": str(it.get("type", "")),
                                        "detail": str(it.get("detail", "")),
                                    })
                    except Exception:
                        pass
                    # Reconstruct full batch lines interleaving filler-only passthrough
                    cleaned_list = parsed.get("cleaned_segments", [])
                    ci = 0
                    _tail_candidates_clean: list[dict] = []
                    for it, send in zip(batch, send_mask):
                        t = int(it["teams"]["t_start"]) ; mm = f"{t//60:02d}"; ss = f"{t%60:02d}"
                        if send:
                            seg = cleaned_list[ci]
                            ci += 1
                            spk = str(seg.get("speaker", "")).strip()
                            txt = str(seg.get("text", "")).strip()
                            out_lines.append(f"[{mm}:{ss}] {spk}: {txt}")
                            _tail_candidates_clean.append({"t_start": t, "speaker": spk, "text": txt})
                        else:
                            # Drop filler-only segments from master output
                            # (we intentionally do not append them to out_lines)
                            pass
                    # Return tail for optional sequential continuity
                    tail_update = _tail_candidates_clean[-2:]
                else:
                    # Fallback: keep Teams text as-is for this batch
                    _tail_candidates_fallback: list[dict] = []
                    for it, send in zip(batch, send_mask):
                        t = int(it["teams"]["t_start"]) ; mm = f"{t//60:02d}"; ss = f"{t%60:02d}"
                        if send:
                            spk = it['teams'].get('speaker','')
                            txt = it['teams'].get('text','')
                            out_lines.append(f"[{mm}:{ss}] {spk}: {txt}")
                            _tail_candidates_fallback.append({"t_start": t, "speaker": spk, "text": txt})
                        else:
                            # Drop filler-only segments in fallback path as well
                            pass
                    tail_update = _tail_candidates_fallback[-2:]

                # Persist per-batch artifacts
                (run_dir / f"cleanup_batch_{idx:03d}_{bidx:02d}.json").write_text(raw or "{}", encoding="utf-8")
                return bidx, out_lines, out_issues, json.dumps(tail_update)

            conc = max(1, int(getattr(args, "cleanup_concurrency", 1)))
            if conc == 1:
                # Sequential with continuity
                for bidx, batch in enumerate(batches):
                    _, out_lines, out_issues, tail_json = _process_one_batch(bidx, batch, use_tail=True)
                    try:
                        tail = json.loads(tail_json) if tail_json else []
                    except Exception:
                        tail = []
                    cleaned_lines.extend(out_lines)
                    issues_accum.extend(out_issues)
                    prev_cleaned_tail = (prev_cleaned_tail + list(tail))[-2:]
            else:
                # Parallel; disable prev_tail continuity for independence
                futures = []
                with ThreadPoolExecutor(max_workers=conc) as ex:
                    for bidx, batch in enumerate(batches):
                        futures.append(ex.submit(_process_one_batch, bidx, batch, False))
                    # Collect and order by bidx
                    results = []
                    for fut in as_completed(futures):
                        results.append(fut.result())
                results.sort(key=lambda x: x[0])
                for _, out_lines, out_issues, _ in results:
                    cleaned_lines.extend(out_lines)
                    issues_accum.extend(out_issues)
            # Update summary for this block
            cleanup_summary["total_batches"] += len(batches)
            # Persist issues for this block
            try:
                (run_dir / f"issues_block_{idx:03d}.json").write_text(json.dumps(issues_accum, indent=2), encoding="utf-8")
            except Exception:
                pass

            cleanup_summary["blocks"].append({
                "block_index": idx,
                "batches": len(batches),
                "segments_cleaned": len(cleaned_lines),
                "issues": len(issues_accum),
            })

            # Write master/qa
            if cleaned_lines:
                with (run_dir / f"master_block_{idx:03d}.txt").open("w", encoding="utf-8") as fmb:
                    fmb.write("\n".join(cleaned_lines) + "\n")
                with (run_dir / "master.txt").open("a", encoding="utf-8") as f_master:
                    f_master.write("\n".join(cleaned_lines) + "\n")
            logger.log("cleanup_block", {"block_index": idx, "batches": len(batches), "glossary_size": len(rolling_glossary)})
            print(f"[fusion] cleanup block {idx+1}/{total_blocks} done - batches={len(batches)} cleaned_lines={len(cleaned_lines)}", flush=True)
            # No rolling glossary persisted; using static glossary only

        elif args.fuse:
            prompt_path = Path("prompts/prompt_fuse_block.md")
            prompt_md = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
            try:
                fused_json_path = run_dir / f"fused_{idx:03d}.json"
                if args.skip_existing and fused_json_path.exists():
                    logger.log("fuse_block", {"block_index": idx, "status": "skipped", "reason": "exists"})
                    continue
                print(f"[fusion] fuse block {idx+1}/{total_blocks}", flush=True)
                temp_cfg = args.temperature if getattr(args, "temperature", None) is not None else config.get("temperature", None)
                temp_val = float(temp_cfg) if isinstance(temp_cfg, (int, float, str)) and str(temp_cfg).strip() != "" else None
                resp = fuse_block_via_llm(block_payload, prompt_md, config.get("model", "gpt-4.1"), temp_val)
                fused_json_path.write_text(json.dumps(resp, indent=2), encoding="utf-8")

                # Parse model output and write artifacts
                parsed = None
                raw = resp.get("raw") if isinstance(resp, dict) else None
                if isinstance(raw, str):
                    try:
                        parsed = json.loads(raw)
                    except Exception as e:
                        logger.log("fuse_block", {"block_index": idx, "status": "parse_error", "reason": str(e)})
                elif isinstance(resp, dict):
                    parsed = resp

                if isinstance(parsed, dict):
                    master_text = str(parsed.get("master_block", ""))
                    qa_text = str(parsed.get("qa_block", ""))
                    (run_dir / f"master_block_{idx:03d}.txt").write_text(master_text, encoding="utf-8")
                    (run_dir / f"qa_block_{idx:03d}.txt").write_text(qa_text, encoding="utf-8")
                    print(f"[fusion] fuse block {idx+1}/{total_blocks} done - master_len={len(master_text)} qa_len={len(qa_text)}", flush=True)

                    # Append cumulative files within this run directory
                    with (run_dir / "master.txt").open("a", encoding="utf-8") as f_master:
                        if master_text:
                            f_master.write(master_text.rstrip() + "\n")
                    with (run_dir / "qa.txt").open("a", encoding="utf-8") as f_qa:
                        if qa_text:
                            f_qa.write(qa_text.rstrip() + "\n")

                    logger.log("fuse_block", {"block_index": idx, "status": "ok", "master_len": len(master_text), "qa_len": len(qa_text), "prompt_sha": sha256_text(prompt_md), "payload_sha": sha256_text(json.dumps(block_payload, ensure_ascii=False))})
                else:
                    logger.log("fuse_block", {"block_index": idx, "status": "no_parse"})
            except Exception as e:
                logger.log("fuse_block", {"block_index": idx, "status": "error", "reason": str(e)})

    print(json.dumps({"status": "ok", "run_dir": str(run_dir), "blocks": total_blocks, "range": [start_idx, end_idx]}, indent=2))
    # Write cleanup summary if enabled
    if args.cleanup_enabled:
        try:
            (run_dir / "cleanup_summary.json").write_text(json.dumps(cleanup_summary, indent=2), encoding="utf-8")
        except Exception:
            pass
    # Optional: export DOCX if requested and master.txt exists
    if args.export_docx:
        master_path = run_dir / "master.txt"
        if master_path.exists():
            def _parse_master_line(line: str) -> dict | None:
                line = line.strip()
                if not line.startswith("["):
                    return None
                try:
                    ts_end = line.index("]")
                    ts = line[1:ts_end]
                    rest = line[ts_end+1:].strip()
                    if ":" in rest:
                        spk, txt = rest.split(":", 1)
                    else:
                        spk, txt = "", rest
                    mm, ss = ts.split(":")
                    t = int(mm) * 60 + int(ss)
                    return {"t": t, "speaker": spk.strip(), "text": txt.strip()}
                except Exception:
                    return None

            lines = []
            for raw in master_path.read_text(encoding="utf-8").splitlines():
                item = _parse_master_line(raw)
                if item:
                    lines.append(item)
            out_docx = run_dir / "master.docx"
            try:
                write_master_docx(lines, out_docx, int(config["export"].get("docx_chapter_minutes", 5)))
                logger.log("export_docx", {"path": str(out_docx), "lines": len(lines)})
            except PermissionError:
                # Fallback if the file is open/locked in Word
                alt_docx = run_dir / "master_new.docx"
                write_master_docx(lines, alt_docx, int(config["export"].get("docx_chapter_minutes", 5)))
                logger.log("export_docx", {"path": str(alt_docx), "lines": len(lines), "note": "wrote alternative due to PermissionError"})
        else:
            logger.log("export_docx", {"status": "skipped", "reason": "missing master.txt"})

    # Optional: product extraction
    if args.extract_products:
        master_path = run_dir / "master.txt"
        if master_path.exists():
            prod_prompt = Path("prompts/prompt_extract_product.md").read_text(encoding="utf-8")
            payload = {"master_block_or_full_text": master_path.read_text(encoding="utf-8")}
            try:
                temp_cfg = args.temperature if getattr(args, "temperature", None) is not None else config.get("temperature", None)
                temp_val = float(temp_cfg) if isinstance(temp_cfg, (int, float, str)) and str(temp_cfg).strip() != "" else None
                resp = fuse_block_via_llm(payload, prod_prompt, config.get("model", "gpt-4.1"), temp_val)
                (run_dir / "products.json").write_text(json.dumps(resp, indent=2), encoding="utf-8")
                # Best-effort extract of quotes/summary to markdown
                raw = resp.get("raw") if isinstance(resp, dict) else None
                if isinstance(raw, str):
                    try:
                        parsed = json.loads(raw)
                        # Support both top-level and nested master_block formats
                        block = parsed.get("master_block") if isinstance(parsed, dict) else None
                        if not isinstance(block, dict):
                            block = parsed if isinstance(parsed, dict) else {}
                        quotes = block.get("quotes", [])
                        summary = block.get("summary", parsed.get("summary", ""))
                        md = ["# Product Extraction", "", "## Quotes", ""]
                        for q in quotes:
                            md.append(f"- [{q.get('t','')}] {q.get('text','')}")
                        md += ["", "## Summary", "", summary]
                        (run_dir / "products.md").write_text("\n".join(md), encoding="utf-8")
                    except Exception:
                        pass
                logger.log("extract_products", {"status": "ok"})
            except Exception as e:
                logger.log("extract_products", {"status": "error", "reason": str(e)})
        else:
            logger.log("extract_products", {"status": "skipped", "reason": "missing master.txt"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
