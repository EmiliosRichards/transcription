import os
import tempfile
import shutil
import json
import subprocess
import sys
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException, Query, Form
from fastapi.responses import FileResponse, JSONResponse

from app.services import task_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_kickoff_dir() -> str:
    """Return absolute path to kickoff_transcript_pipeline directory.

    Handles two layouts:
    - Monorepo root: <repo>/kickoff_transcript_pipeline
    - Backend-only image: <backend_root>/kickoff_transcript_pipeline
    Allows override via KICKOFF_DIR env.
    """
    # 1) Env override
    env_dir = os.environ.get("KICKOFF_DIR")
    if env_dir and os.path.isdir(env_dir):
        return os.path.abspath(env_dir)

    here = os.path.dirname(__file__)  # .../app/routers
    candidates = [
        os.path.abspath(os.path.join(here, "..", "..", "kickoff_transcript_pipeline")),  # backend root
        os.path.abspath(os.path.join(here, "..", "..", "..", "..", "kickoff_transcript_pipeline")),  # repo root
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    # Fallback to first candidate (useful for error messages)
    return candidates[0]
async def _run_transcribe_only(
    task_id: str,
    audio_path: str,
    teams_path: str,
    language: Optional[str],
    vocab_hints: Optional[str],
    run_dir_input: Optional[str],
):
    try:
        task_manager.update_task_status(task_id, "PROCESSING", "Preparing transcription...", progress=10)
        kickoff_dir = _resolve_kickoff_dir()
        out_dir = os.path.join(kickoff_dir, "out")
        os.makedirs(out_dir, exist_ok=True)
        run_dir_abs = os.path.join(out_dir, run_dir_input) if (run_dir_input and not os.path.isabs(run_dir_input)) else (run_dir_input if run_dir_input else None)
        if run_dir_abs:
            os.makedirs(run_dir_abs, exist_ok=True)
        ref_out = os.path.join(run_dir_abs or out_dir, f"ref_{task_id[:8]}")
        os.makedirs(ref_out, exist_ok=True)

        # Resolve simple_transcriber directory
        here = os.path.dirname(__file__)  # .../app/routers
        candidates = [
            os.path.abspath(os.path.join(kickoff_dir, "..", "..", "..", "tools", "simple_transcriber")),
            os.path.abspath(os.path.join(kickoff_dir, "..", "tools", "simple_transcriber")),
            os.path.abspath(os.path.join(kickoff_dir, "tools", "simple_transcriber")),
            os.path.abspath(os.path.join(here, "..", "..", "tools", "simple_transcriber")),  # backend-root/tools/simple_transcriber
        ]
        transcriber_dir = None
        for c in candidates:
            if os.path.isdir(c):
                transcriber_dir = c
                break
        if not transcriber_dir:
            logger.error("simple_transcriber directory not found; checked: %s", candidates)
            raise RuntimeError("simple_transcriber directory not found; expected under tools/simple_transcriber")

        model = "gpt-4o-transcribe"
        lang = language or "de"
        hints = (vocab_hints or "").strip()
        hint_args: list[str] = []
        if hints:
            hint_args = ["--vocab-hint", hints]
        cmd_ref = [
            sys.executable or "python",
            "transcribe.py",
            "--input", audio_path,
            "--vtt", teams_path,
            "--output", ref_out,
            "--model", model,
            "--language", lang,
            "--jobs", "4",
            "--window-sec", "90",
            "--join-gap-sec", "1.0",
            "--min-seg-sec", "5.0",
            "--pad-sec", "0.8",
            "--overlap-policy", "drop-micro",
            "--overlap-min-sec", "1.2",
            "--overlap-min-ratio", "0.7",
            "--backchannel-token-max", "2",
            "--final-align", "original",
        ] + hint_args
        logger.info(f"[transcribe {task_id}] cmd={' '.join(cmd_ref)} cwd={transcriber_dir}")
        task_manager.update_task_status(task_id, "PROCESSING", "Transcribing with GPT-4o...", progress=35)
        proc = subprocess.Popen(cmd_ref, cwd=transcriber_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        assert proc.stdout is not None
        for line in proc.stdout:
            logger.info(f"[transcribe {task_id}] out: {line.rstrip()}")
        proc.wait()
        if proc.returncode != 0:
            task_manager.set_task_error(task_id, "Reference transcription failed.")
            return

        # Collect artifacts (prefer JSON, VTT, TXT)
        artifacts = []
        for name in os.listdir(ref_out):
            path = os.path.join(ref_out, name)
            if os.path.isfile(path) and (name.lower().endswith(('.json', '.vtt', '.txt'))):
                artifacts.append({"name": name, "path": path})

        result_payload = {"run_dir": ref_out, "artifacts": artifacts}
        task_manager.set_task_success(task_id, result_payload)
    except Exception:
        logger.exception("[transcribe %s] unexpected error", task_id)
        task_manager.set_task_error(task_id, "Unexpected error during transcription.")


async def _run_fusion_background(
    task_id: str,
    teams_path: str,
    krisp_path: str,
    charla_path: str,
    start_block: Optional[int] = None,
    end_block: Optional[int] = None,
    run_dir_input: Optional[str] = None,
    skip_existing: bool = False,
    ref_json_path: Optional[str] = None,
    use_charla: bool = False,
    low_consensus_threshold: float = 0.35,
    cleanup_enabled: bool = False,
    cleanup_max_tokens: int = 4000,
    cleanup_model: str = "gpt-5-2025-08-07",
    cleanup_concurrency: int = 4,
    include_context: bool = True,
    diagnostics: bool = True,
    auto_offset_enabled: bool = True,
    offset_adjust_gpt: bool = True,
    offset_min_phrase_tokens: int = 4,
    offset_max_phrase_tokens: int = 10,
    offset_similarity_threshold: float = 0.66,
    offset_expand_tokens: int = 2,
    offset_trim_pad_sec: int = 2,
    glossary: Optional[str] = None,
):
    try:
        logger.info(f"[fusion {task_id}] starting; files: teams={teams_path}, krisp={krisp_path}, charla={charla_path}; blocks=({start_block},{end_block}); run_dir={run_dir_input}; skip_existing={skip_existing}")
        task_manager.update_task_status(task_id, "PROCESSING", "Preparing files...", progress=10)

        kickoff_dir = _resolve_kickoff_dir()
        logger.info(f"[fusion {task_id}] kickoff_dir={kickoff_dir}")
        if not os.path.isdir(kickoff_dir):
            raise RuntimeError(f"Kickoff pipeline directory not found at: {kickoff_dir}")

        cmd = [
            sys.executable or "python",
            "run_fusion.py",
            "--config",
            "configs/default.yaml",
            "--teams",
            teams_path,
            "--krisp",
            krisp_path,
            "--charla",
            charla_path,
            "--fuse",
            "--export-docx",
            "--extract-products",
        ]
        if start_block is not None:
            cmd += ["--start-block", str(start_block)]
        if end_block is not None:
            cmd += ["--end-block", str(end_block)]
        if run_dir_input:
            cmd += ["--run-dir", run_dir_input]
        if skip_existing:
            cmd += ["--skip-existing"]
        if use_charla:
            cmd += ["--use-charla"]
        if ref_json_path:
            cmd += ["--ref-json", ref_json_path]
        if low_consensus_threshold is not None:
            cmd += ["--low-consensus-threshold", str(low_consensus_threshold)]
        # Include cleanup flags when requested (best-effort)
        if cleanup_enabled:
            cmd += [
                "--cleanup-enabled",
                "--cleanup-max-tokens", str(int(cleanup_max_tokens or 6000)),
                "--cleanup-model", str(cleanup_model or "gpt-5-2025-08-07"),
                "--cleanup-concurrency", str(int(cleanup_concurrency or 4)),
            ]
        if include_context:
            cmd += ["--include-context"]
        if diagnostics:
            cmd += ["--diagnostics"]
        # Global offset flags (enabled by default per requested settings)
        if auto_offset_enabled:
            cmd += [
                "--auto-offset-enabled",
                "--offset-min-phrase-tokens", str(int(offset_min_phrase_tokens)),
                "--offset-max-phrase-tokens", str(int(offset_max_phrase_tokens)),
                "--offset-similarity-threshold", str(float(offset_similarity_threshold)),
                "--offset-expand-tokens", str(int(offset_expand_tokens)),
                "--offset-trim-pad-sec", str(int(offset_trim_pad_sec)),
            ]
            if offset_adjust_gpt:
                cmd += ["--offset-adjust-gpt"]
        if glossary:
            cmd += ["--glossary", glossary]

        logger.info(f"[fusion {task_id}] cmd={' '.join(cmd)}")
        task_manager.update_task_status(task_id, "PROCESSING", "Running fusion pipeline...", progress=30)
        proc = subprocess.Popen(
            cmd,
            cwd=kickoff_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        # Stream combined output live to logs for easier debugging (line-buffered)
        stdout_lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            stdout_lines.append(line)
            logger.info(f"[fusion {task_id}] out: {line.rstrip()}")
        proc.wait()
        stdout = "".join(stdout_lines)
        stderr = ""  # merged into stdout

        if proc.returncode != 0:
            logger.error("[fusion %s] pipeline failed: %s", task_id, stderr)
            task_manager.set_task_error(task_id, f"Pipeline failed: {stderr.strip()[:1000]}")
            return

        task_manager.update_task_status(task_id, "PROCESSING", "Collecting artifacts...", progress=80)

        run_info: Optional[dict] = None
        try:
            # The script prints a JSON object near the end; try to parse from the last JSON-looking block
            last_brace = stdout.rfind("}\n")
            first_brace = stdout.rfind("{", 0, last_brace + 1)
            if first_brace != -1 and last_brace != -1:
                maybe_json = stdout[first_brace:last_brace + 1]
                logger.info(f"[fusion {task_id}] parsed run info candidate: {maybe_json[:200]}...")
                run_info = json.loads(maybe_json)
        except Exception:
            run_info = None

        run_dir = None
        if isinstance(run_info, dict):
            run_dir = run_info.get("run_dir")

        # Fallback: try to locate most recent directory in out/
        if not run_dir:
            out_dir = os.path.join(kickoff_dir, "out")
            if os.path.isdir(out_dir):
                subdirs = [
                    os.path.join(out_dir, d) for d in os.listdir(out_dir)
                    if os.path.isdir(os.path.join(out_dir, d))
                ]
                if subdirs:
                    run_dir = max(subdirs, key=os.path.getmtime)

        logger.info(f"[fusion {task_id}] detected run_dir={run_dir}")
        if not run_dir or not os.path.isdir(run_dir):
            task_manager.set_task_error(task_id, "Pipeline completed but run directory not found.")
            return

        # Post-process grouped outputs (TXT + DOCX) and collect artifacts preferring grouped
        try:
            master_txt = os.path.join(run_dir, "master.txt")
            if os.path.isfile(master_txt):
                here = os.path.dirname(__file__)  # .../app/routers
                tools_candidates = [
                    os.path.abspath(os.path.join(kickoff_dir, "..", "..", "..", "tools", "fusion-tool")),
                    os.path.abspath(os.path.join(kickoff_dir, "..", "tools", "fusion-tool")),
                    os.path.abspath(os.path.join(kickoff_dir, "tools", "fusion-tool")),
                    os.path.abspath(os.path.join(here, "..", "..", "tools", "fusion-tool")),
                ]
                tools_dir = None
                for c in tools_candidates:
                    if os.path.isdir(c):
                        tools_dir = c
                        break
                if tools_dir:
                    try:
                        cmd_txt = [sys.executable or "python", "postprocess_group_by_speaker.py", "--input", master_txt, "--merge"]
                        logger.info(f"[fusion {task_id}] postprocess txt cmd={' '.join(cmd_txt)} cwd={tools_dir}")
                        subprocess.run(cmd_txt, cwd=tools_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    except Exception:
                        logger.exception(f"[fusion {task_id}] TXT postprocess failed")
                    try:
                        cmd_docx = [sys.executable or "python", "postprocess_group_by_speaker_docx.py", "--input", master_txt, "--merge"]
                        logger.info(f"[fusion {task_id}] postprocess docx cmd={' '.join(cmd_docx)} cwd={tools_dir}")
                        subprocess.run(cmd_docx, cwd=tools_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    except Exception:
                        logger.exception(f"[fusion {task_id}] DOCX postprocess failed")
        except Exception:
            logger.exception(f"[fusion {task_id}] postprocess grouping encountered an error")

        artifacts = []
        # Prefer grouped versions; fallback to originals
        for name in ("master_grouped.txt", "master_grouped.docx"):
            path = os.path.join(run_dir, name)
            if os.path.isfile(path):
                artifacts.append({"name": name, "path": path})
        if not artifacts:
            for name in ("master.txt", "master.docx"):
                path = os.path.join(run_dir, name)
                if os.path.isfile(path):
                    artifacts.append({"name": name, "path": path})
        for name in ("qa.txt", "products.json", "products.md"):
            path = os.path.join(run_dir, name)
            if os.path.isfile(path):
                artifacts.append({"name": name, "path": path})

        result_payload = {
            "run_dir": run_dir,
            "artifacts": artifacts,
        }
        logger.info(f"[fusion {task_id}] artifacts={[a['name'] for a in artifacts]}")
        task_manager.set_task_success(task_id, result_payload)
    except Exception as e:
        logger.exception("[fusion %s] unexpected error", task_id)
        task_manager.set_task_error(task_id, f"Unexpected error: {e}")


@router.post("/fusion/run")
async def start_fusion(
    background_tasks: BackgroundTasks,
    teams: UploadFile = File(..., description="Teams VTT file (.vtt)"),
    charla: Optional[UploadFile] = File(None, description="Charla TXT file (.txt)"),
    krisp: UploadFile = File(..., description="Krisp TXT file (.txt)"),
    start_block: Optional[int] = Form(None),
    end_block: Optional[int] = Form(None),
    run_dir: Optional[str] = Form(None),
    skip_existing: Optional[bool] = Form(False),
    audio: Optional[UploadFile] = File(None, description="Optional audio (mp3/mp4) for reference transcript"),
    language: Optional[str] = Form(None),
    vocab_hints: Optional[str] = Form(None),
    use_charla: Optional[bool] = Form(False),
    low_consensus_threshold: Optional[float] = Form(0.35),
    ref: Optional[UploadFile] = File(None, description="Optional GPT reference JSON produced externally"),
    cleanup_enabled: Optional[bool] = Form(True),
    cleanup_max_tokens: Optional[int] = Form(6000),
    cleanup_model: Optional[str] = Form("gpt-5-2025-08-07"),
    cleanup_concurrency: Optional[int] = Form(4),
    include_context: Optional[bool] = Form(True),
    diagnostics: Optional[bool] = Form(True),
    auto_offset_enabled: Optional[bool] = Form(True),
    offset_adjust_gpt: Optional[bool] = Form(True),
    offset_min_phrase_tokens: Optional[int] = Form(4),
    offset_max_phrase_tokens: Optional[int] = Form(10),
    offset_expand_tokens: Optional[int] = Form(2),
    offset_similarity_threshold: Optional[float] = Form(0.66),
    offset_trim_pad_sec: Optional[int] = Form(2),
    glossary: Optional[str] = Form(None),
):
    # Validate file extensions by filename as content types can vary by browser
    if not teams.filename or not (teams.filename.lower()).endswith(".vtt"):
        raise HTTPException(status_code=400, detail="Teams file must be a .vtt")
    if use_charla:
        if not charla or not charla.filename or not (charla.filename.lower()).endswith(".txt"):
            raise HTTPException(status_code=400, detail="Charla file must be a .txt when enabled")
    if not krisp.filename or not (krisp.filename.lower()).endswith(".txt"):
        raise HTTPException(status_code=400, detail="Krisp file must be a .txt")

    task_id = task_manager.create_task()

    temp_dir = tempfile.mkdtemp(prefix=f"fusion_{task_id}_")
    try:
        # Filenames are guaranteed above
        teams_path = os.path.join(temp_dir, os.path.basename(teams.filename))
        charla_path = os.path.join(temp_dir, os.path.basename(charla.filename)) if (use_charla and charla and charla.filename) else ""
        krisp_path = os.path.join(temp_dir, os.path.basename(krisp.filename))

        with open(teams_path, "wb") as f:
            f.write(await teams.read())
        if use_charla and charla and charla.filename:
            with open(charla_path, "wb") as f:
                f.write(await charla.read())
        with open(krisp_path, "wb") as f:
            f.write(await krisp.read())

        # Prepare run_dir for reference output if provided
        kickoff_dir = _resolve_kickoff_dir()
        out_dir = os.path.join(kickoff_dir, "out")
        os.makedirs(out_dir, exist_ok=True)
        run_dir_abs = os.path.join(out_dir, run_dir) if (run_dir and not os.path.isabs(run_dir)) else (run_dir if run_dir else None)
        if run_dir_abs:
            os.makedirs(run_dir_abs, exist_ok=True)

        # Optional: run full-audio reference transcription
        ref_json_path = None
        if audio and audio.filename:
            audio_path = os.path.join(temp_dir, os.path.basename(audio.filename))
            with open(audio_path, "wb") as f:
                f.write(await audio.read())
            try:
                ref_out = os.path.join(run_dir_abs or out_dir, f"ref_{task_id[:8]}")
                os.makedirs(ref_out, exist_ok=True)
                # Build transcriber command
                # Resolve simple_transcriber directory robustly
                # Candidates relative to project structure
                here = os.path.dirname(__file__)  # .../app/routers
                candidates = [
                    os.path.abspath(os.path.join(kickoff_dir, "..", "..", "..", "tools", "simple_transcriber")),
                    os.path.abspath(os.path.join(kickoff_dir, "..", "tools", "simple_transcriber")),
                    os.path.abspath(os.path.join(kickoff_dir, "tools", "simple_transcriber")),
                    os.path.abspath(os.path.join(here, "..", "..", "tools", "simple_transcriber")),
                ]
                transcriber_dir = None
                for c in candidates:
                    if os.path.isdir(c):
                        transcriber_dir = c
                        break
                if not transcriber_dir:
                    logger.error("simple_transcriber directory not found; checked: %s", candidates)
                    raise RuntimeError("simple_transcriber directory not found; expected under tools/simple_transcriber")
                model = "gpt-4o-transcribe"
                lang = language or "de"
                hints = (vocab_hints or "").strip()
                hint_args = []
                if hints:
                    hint_args = ["--vocab-hint", hints]
                cmd_ref = [
                    sys.executable or "python",
                    "transcribe.py",
                    "--input", audio_path,
                    "--vtt", teams_path,
                    "--output", ref_out,
                    "--model", model,
                    "--language", lang,
                    "--jobs", "4",
                    "--window-sec", "90",
                    "--join-gap-sec", "1.0",
                    "--min-seg-sec", "5.0",
                    "--pad-sec", "0.8",
                    "--overlap-policy", "drop-micro",
                    "--overlap-min-sec", "1.2",
                    "--overlap-min-ratio", "0.7",
                    "--backchannel-token-max", "2",
                    "--final-align", "original",
                ] + hint_args
                logger.info(f"[fusion {task_id}] ref cmd={' '.join(cmd_ref)} cwd={transcriber_dir}")
                proc_ref = subprocess.Popen(cmd_ref, cwd=transcriber_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                assert proc_ref.stdout is not None
                for line in proc_ref.stdout:
                    logger.info(f"[fusion {task_id}] ref: {line.rstrip()}")
                proc_ref.wait()
                # Pick largest JSON in output folder
                cands = [os.path.join(ref_out, p) for p in os.listdir(ref_out) if p.lower().endswith('.json')]
                if cands:
                    ref_json_path = max(cands, key=os.path.getsize)
            except Exception:
                logger.exception("[fusion %s] reference transcription failed", task_id)
                ref_json_path = None

        # Or accept uploaded ref JSON directly
        if (not ref_json_path) and ref and ref.filename and ref.filename.lower().endswith('.json'):
            ref_json_local = os.path.join(temp_dir, os.path.basename(ref.filename))
            with open(ref_json_local, "wb") as f:
                f.write(await ref.read())
            ref_json_path = ref_json_local

        # Kick off background processing
        background_tasks.add_task(
            _run_fusion_background,
            task_id,
            teams_path,
            krisp_path,
            charla_path,
            start_block,
            end_block,
            run_dir,
            bool(skip_existing),
            ref_json_path,
            bool(use_charla),
            float(low_consensus_threshold) if low_consensus_threshold is not None else 0.35,
            bool(cleanup_enabled),
            int(cleanup_max_tokens or 6000),
            str(cleanup_model or "gpt-5-2025-08-07"),
            int(cleanup_concurrency or 4),
            bool(include_context),
            bool(diagnostics),
            bool(auto_offset_enabled),
            bool(offset_adjust_gpt),
            int(offset_min_phrase_tokens or 4),
            int(offset_max_phrase_tokens or 10),
            float(offset_similarity_threshold or 0.66),
            int(offset_expand_tokens or 2),
            int(offset_trim_pad_sec or 2),
            str(glossary) if glossary else None,
        )
        logger.info(f"[fusion {task_id}] accepted and scheduled")
        # Append cleanup flags into the task command by storing them in a hidden result hint (picked up in _run_fusion_background)
        # Easier: pass via environment variables is overkill; instead extend _run_fusion_background to accept extra args via closure
        # Simpler approach: enqueue a second step is complex; instead we reconstruct the command inside _run_fusion_background via current args.
        # The parameters are already available above; we embed them into the logger and let _run_fusion_background build the flags.
        # To ensure flags are included, we add them into the task store for visibility (optional).
        return {"task_id": task_id, "cleanup": {"enabled": bool(cleanup_enabled), "max_tokens": int(cleanup_max_tokens or 6000), "model": cleanup_model or "gpt-5-2025-08-07"}}
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.exception("Failed to start fusion task")
        raise HTTPException(status_code=500, detail=f"Failed to start fusion: {e}")
@router.post("/fusion/transcribe-only")
async def start_transcribe_only(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(..., description="Audio file (.mp3/.mp4)"),
    teams: UploadFile = File(..., description="Teams VTT file (.vtt) for alignment"),
    language: Optional[str] = Form(None),
    vocab_hints: Optional[str] = Form(None),
    run_dir: Optional[str] = Form(None),
):
    if not audio.filename or not (audio.filename.lower()).endswith(('.mp3', '.mp4', '.wav', '.m4a')):
        raise HTTPException(status_code=400, detail="Audio must be .mp3/.mp4/.wav/.m4a")
    if not teams.filename or not (teams.filename.lower()).endswith('.vtt'):
        raise HTTPException(status_code=400, detail="Teams file must be a .vtt")

    task_id = task_manager.create_task()
    temp_dir = tempfile.mkdtemp(prefix=f"transcribe_{task_id}_")
    try:
        audio_path = os.path.join(temp_dir, os.path.basename(audio.filename))
        with open(audio_path, "wb") as f:
            f.write(await audio.read())
        teams_path = os.path.join(temp_dir, os.path.basename(teams.filename))
        with open(teams_path, "wb") as f:
            f.write(await teams.read())

        background_tasks.add_task(
            _run_transcribe_only,
            task_id,
            audio_path,
            teams_path,
            language,
            vocab_hints,
            run_dir,
        )
        return {"task_id": task_id}
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.exception("Failed to start transcribe-only task")
        raise HTTPException(status_code=500, detail="Failed to start transcribe-only task")


@router.get("/fusion/{task_id}/artifacts")
async def list_artifacts(task_id: str):
    status = task_manager.get_task_status(task_id)
    if not status or status.get("status") != "SUCCESS":
        raise HTTPException(status_code=404, detail="Task not successful or not found")
    result = status.get("result") or {}
    artifacts = result.get("artifacts") or []
    return {"artifacts": [{"name": a.get("name")} for a in artifacts]}


@router.get("/fusion/{task_id}/download")
async def download_artifact(task_id: str, name: str = Query(..., description="Artifact filename, e.g., master.txt")):
    # Security: only allow basename within recorded run_dir
    if os.path.sep in name or os.path.altsep and os.path.altsep in name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    status = task_manager.get_task_status(task_id)
    if not status or status.get("status") != "SUCCESS":
        raise HTTPException(status_code=404, detail="Task not successful or not found")
    result = status.get("result") or {}
    run_dir = result.get("run_dir")
    if not run_dir:
        raise HTTPException(status_code=404, detail="Run directory not found")

    file_path = os.path.join(run_dir, name)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    media_type = "application/octet-stream"
    if name.lower().endswith(".txt"):
        media_type = "text/plain"
    elif name.lower().endswith(".json"):
        media_type = "application/json"
    elif name.lower().endswith(".md"):
        media_type = "text/markdown"
    elif name.lower().endswith(".docx"):
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    return FileResponse(file_path, filename=name, media_type=media_type)


async def _run_extract_background(task_id: str, run_dir_input: str):
    try:
        logger.info(f"[extract {task_id}] starting; run_dir={run_dir_input}")
        task_manager.update_task_status(task_id, "PROCESSING", "Running extract-products...", progress=20)
        kickoff_dir = _resolve_kickoff_dir()
        if not os.path.isdir(kickoff_dir):
            raise RuntimeError(f"Kickoff pipeline directory not found at: {kickoff_dir}")

        cmd = [
            sys.executable or "python",
            "run_fusion.py",
            "--config",
            "configs/default.yaml",
            "--run-dir",
            run_dir_input,
            "--extract-products",
        ]
        logger.info(f"[extract {task_id}] cmd={' '.join(cmd)} cwd={kickoff_dir}")
        proc = subprocess.Popen(
            cmd,
            cwd=kickoff_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        # Stream combined output
        out_lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            out_lines.append(line)
            logger.info(f"[extract {task_id}] out: {line.rstrip()}")
        proc.wait()
        stdout = "".join(out_lines)
        stderr = ""
        if proc.returncode != 0:
            logger.error("[extract %s] failed: %s", task_id, stderr)
            task_manager.set_task_error(task_id, f"Extract failed: {stderr.strip()[:1000]}")
            return

        # Post-process grouped outputs (TXT + DOCX)
        try:
            master_txt = os.path.join(run_dir_abs, "master.txt")
            if os.path.isfile(master_txt):
                here = os.path.dirname(__file__)  # .../app/routers
                tools_candidates = [
                    os.path.abspath(os.path.join(kickoff_dir, "..", "..", "..", "tools", "fusion-tool")),
                    os.path.abspath(os.path.join(kickoff_dir, "..", "tools", "fusion-tool")),
                    os.path.abspath(os.path.join(kickoff_dir, "tools", "fusion-tool")),
                    os.path.abspath(os.path.join(here, "..", "..", "tools", "fusion-tool")),
                ]
                tools_dir = None
                for c in tools_candidates:
                    if os.path.isdir(c):
                        tools_dir = c
                        break
                if tools_dir:
                    try:
                        cmd_txt = [sys.executable or "python", "postprocess_group_by_speaker.py", "--input", master_txt, "--merge"]
                        logger.info(f"[extract {task_id}] postprocess txt cmd={' '.join(cmd_txt)} cwd={tools_dir}")
                        subprocess.run(cmd_txt, cwd=tools_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    except Exception:
                        logger.exception(f"[extract {task_id}] TXT postprocess failed")
                    try:
                        cmd_docx = [sys.executable or "python", "postprocess_group_by_speaker_docx.py", "--input", master_txt, "--merge"]
                        logger.info(f"[extract {task_id}] postprocess docx cmd={' '.join(cmd_docx)} cwd={tools_dir}")
                        subprocess.run(cmd_docx, cwd=tools_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    except Exception:
                        logger.exception(f"[extract {task_id}] DOCX postprocess failed")
        except Exception:
            logger.exception(f"[extract {task_id}] postprocess grouping encountered an error")

        # Collect artifacts (prefer grouped)
        run_dir_abs = run_dir_input
        if not os.path.isabs(run_dir_abs):
            run_dir_abs = os.path.join(kickoff_dir, run_dir_input)
        if not os.path.isdir(run_dir_abs):
            task_manager.set_task_error(task_id, "Run directory not found after extract.")
            return

        artifacts = []
        for name in ("master_grouped.txt", "master_grouped.docx"):
            path = os.path.join(run_dir_abs, name)
            if os.path.isfile(path):
                artifacts.append({"name": name, "path": path})
        if not artifacts:
            for name in ("master.txt", "master.docx"):
                path = os.path.join(run_dir_abs, name)
                if os.path.isfile(path):
                    artifacts.append({"name": name, "path": path})
        for name in ("qa.txt", "products.json", "products.md"):
            path = os.path.join(run_dir_abs, name)
            if os.path.isfile(path):
                artifacts.append({"name": name, "path": path})

        result_payload = {"run_dir": run_dir_abs, "artifacts": artifacts}
        logger.info(f"[extract {task_id}] artifacts={[a['name'] for a in artifacts]}")
        task_manager.set_task_success(task_id, result_payload)
    except Exception as e:
        logger.exception("[extract %s] unexpected error", task_id)
        task_manager.set_task_error(task_id, f"Unexpected error: {e}")


@router.post("/fusion/extract")
async def start_extract(background_tasks: BackgroundTasks, run_dir: str = Form(...)):
    if not run_dir:
        raise HTTPException(status_code=400, detail="run_dir is required")
    task_id = task_manager.create_task()
    background_tasks.add_task(_run_extract_background, task_id, run_dir)
    return {"task_id": task_id}


