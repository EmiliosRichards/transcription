import argparse
import json
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
from src.pipeline.llm.responses_client import fuse_block_via_llm


def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcript fusion pipeline (skeleton)")
    parser.add_argument("--config", required=True)
    parser.add_argument("--teams", help="Override path to Teams .docx")
    parser.add_argument("--krisp", help="Override path to Krisp .txt")
    parser.add_argument("--charla", help="Override path to Charla .txt")
    parser.add_argument("--only-block", type=int, help="Run only the specified block index")
    parser.add_argument("--start-block", type=int, help="Start block index (inclusive)")
    parser.add_argument("--end-block", type=int, help="End block index (inclusive)")
    parser.add_argument("--skip-existing", action="store_true", help="Skip writing blocks that already exist")
    parser.add_argument("--fuse", action="store_true", help="Call LLM to fuse the selected blocks")
    parser.add_argument("--export-docx", action="store_true", help="Render master.docx for this run from master.txt")
    parser.add_argument("--run-dir", help="Optional: reuse a specific run directory under out/ instead of creating a new one")
    parser.add_argument("--extract-products", action="store_true", help="Run product extraction on master.txt using prompt_extract_product.md")
    args = parser.parse_args()

    config = load_config(Path(args.config))

    teams = Path(args.teams or config["inputs"]["teams"]).resolve()
    krisp = Path(args.krisp or config["inputs"]["krisp"]).resolve()
    charla = Path(args.charla or config["inputs"]["charla"]).resolve()

    out_dir = Path(config["export"]["out_dir"]).resolve()
    if args.run_dir:
        run_dir = (out_dir / args.run_dir).resolve() if not Path(args.run_dir).is_absolute() else Path(args.run_dir).resolve()
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = out_dir / f"run_{timestamp}"
    log_path = run_dir / "run.jsonl"
    logger = RunLogger(log_path)

    t0 = time.time()
    ok, checks = preflight_check([teams, krisp, charla])
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
    c_segments = read_charla_txt(charla)
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

    # Partition into blocks by Krisp timeline (as base)
    minutes_per_block = int(config.get("minutes_per_block", 12))
    blocks = partition_by_minutes(k_segments, minutes_per_block)
    total_blocks = len(blocks)
    logger.log("partition", {"minutes_per_block": minutes_per_block, "total_blocks": total_blocks})

    # Determine block range
    if args.only_block is not None:
        start_idx = end_idx = max(0, min(args.only_block, total_blocks - 1))
    else:
        start_idx = max(0, int(args.start_block) if args.start_block is not None else 0)
        end_idx = min(total_blocks - 1, int(args.end_block) if args.end_block is not None else total_blocks - 1)

    # Write per-block stubs for downstream steps
    for idx in range(start_idx, end_idx + 1):
        block = select_block(blocks, idx)
        block_path = run_dir / f"block_{idx:03d}.json"
        if args.skip_existing and block_path.exists():
            logger.log("skip_block", {"block_index": idx, "reason": "exists"})
            # Optionally still fuse if requested and fused file missing
            pass
        # Build richer payload with time-window alignment against Teams/Charla
        # Limit Teams/Charla to the time window of this block for efficiency
        if len(block) > 0:
            block_start = int(block[0].get("t_start") or 0)
            block_end = int(block[-1].get("t_start") or block_start)
        else:
            block_start = 0
            block_end = 0
        teams_in_range = [t for t in t_segments if block_start - 30 <= int(t.get("t_start") or 0) <= block_end + 30]
        charla_in_range = [c for c in c_segments if block_start - 30 <= int(c.get("t_start") or 0) <= block_end + 30]
        aligned = align_segments(block, teams_in_range, charla_in_range, window_sec=int(config.get("duplicate_window_sec", 4)))
        # Deterministic Krisp -> real name mapping before fusion
        k_with_names = map_speakers_via_alignment(block, aligned)
        block_payload = {"aligned": aligned, "krisp": k_with_names}
        block_path.write_text(json.dumps(block_payload, indent=2), encoding="utf-8")
        logger.log("write_block", {"block_index": idx, "krisp_count": len(block)})

        if args.fuse:
            prompt_path = Path("prompts/prompt_fuse_block.md")
            prompt_md = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
            try:
                fused_json_path = run_dir / f"fused_{idx:03d}.json"
                if args.skip_existing and fused_json_path.exists():
                    logger.log("fuse_block", {"block_index": idx, "status": "skipped", "reason": "exists"})
                    continue
                resp = fuse_block_via_llm(block_payload, prompt_md, config.get("model", "gpt-4.1"), float(config.get("temperature", 0.2)))
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
                resp = fuse_block_via_llm(payload, prod_prompt, config.get("model", "gpt-4.1"), float(config.get("temperature", 0.2)))
                (run_dir / "products.json").write_text(json.dumps(resp, indent=2), encoding="utf-8")
                # Best-effort extract of quotes/summary to markdown
                raw = resp.get("raw") if isinstance(resp, dict) else None
                if isinstance(raw, str):
                    try:
                        parsed = json.loads(raw)
                        quotes = parsed.get("quotes", [])
                        summary = parsed.get("summary", "")
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
