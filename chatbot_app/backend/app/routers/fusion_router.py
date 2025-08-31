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


def _project_root_from_here() -> str:
    # This file is at chatbot_app/backend/app/routers/fusion_router.py
    here = os.path.dirname(__file__)
    app_dir = os.path.abspath(os.path.join(here, ".."))
    backend_dir = os.path.abspath(os.path.join(app_dir, ".."))
    chatbot_app_dir = os.path.abspath(os.path.join(backend_dir, ".."))
    project_root = os.path.abspath(os.path.join(chatbot_app_dir, ".."))
    return project_root


async def _run_fusion_background(
    task_id: str,
    teams_path: str,
    krisp_path: str,
    charla_path: str,
    start_block: Optional[int] = None,
    end_block: Optional[int] = None,
    run_dir_input: Optional[str] = None,
    skip_existing: bool = False,
):
    try:
        task_manager.update_task_status(task_id, "PROCESSING", "Preparing files...", progress=10)

        project_root = _project_root_from_here()
        kickoff_dir = os.path.join(project_root, "kickoff_transcript_pipeline")
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

        task_manager.update_task_status(task_id, "PROCESSING", "Running fusion pipeline...", progress=30)
        proc = subprocess.Popen(
            cmd,
            cwd=kickoff_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate()

        if proc.returncode != 0:
            logger.error("Fusion pipeline failed: %s", stderr)
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

        if not run_dir or not os.path.isdir(run_dir):
            task_manager.set_task_error(task_id, "Pipeline completed but run directory not found.")
            return

        # Collect primary artifacts
        wanted = ["master.txt", "qa.txt", "master.docx", "products.json", "products.md"]
        artifacts = []
        for name in wanted:
            path = os.path.join(run_dir, name)
            if os.path.isfile(path):
                artifacts.append({"name": name, "path": path})

        result_payload = {
            "run_dir": run_dir,
            "artifacts": artifacts,
        }
        task_manager.set_task_success(task_id, result_payload)
    except Exception as e:
        logger.exception("Unexpected error in fusion task")
        task_manager.set_task_error(task_id, f"Unexpected error: {e}")


@router.post("/fusion/run")
async def start_fusion(
    background_tasks: BackgroundTasks,
    teams: UploadFile = File(..., description="Teams VTT file (.vtt)"),
    charla: UploadFile = File(..., description="Charla TXT file (.txt)"),
    krisp: UploadFile = File(..., description="Krisp TXT file (.txt)"),
    start_block: Optional[int] = Form(None),
    end_block: Optional[int] = Form(None),
    run_dir: Optional[str] = Form(None),
    skip_existing: Optional[bool] = Form(False),
):
    # Validate file extensions by filename as content types can vary by browser
    if not teams.filename.lower().endswith(".vtt"):
        raise HTTPException(status_code=400, detail="Teams file must be a .vtt")
    if not charla.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Charla file must be a .txt")
    if not krisp.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Krisp file must be a .txt")

    task_id = task_manager.create_task()

    temp_dir = tempfile.mkdtemp(prefix=f"fusion_{task_id}_")
    try:
        teams_path = os.path.join(temp_dir, os.path.basename(teams.filename))
        charla_path = os.path.join(temp_dir, os.path.basename(charla.filename))
        krisp_path = os.path.join(temp_dir, os.path.basename(krisp.filename))

        with open(teams_path, "wb") as f:
            f.write(await teams.read())
        with open(charla_path, "wb") as f:
            f.write(await charla.read())
        with open(krisp_path, "wb") as f:
            f.write(await krisp.read())

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
        )
        return {"task_id": task_id}
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.exception("Failed to start fusion task")
        raise HTTPException(status_code=500, detail=f"Failed to start fusion: {e}")


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
        task_manager.update_task_status(task_id, "PROCESSING", "Running extract-products...", progress=20)
        project_root = _project_root_from_here()
        kickoff_dir = os.path.join(project_root, "kickoff_transcript_pipeline")
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
        proc = subprocess.Popen(cmd, cwd=kickoff_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            logger.error("Extract products failed: %s", stderr)
            task_manager.set_task_error(task_id, f"Extract failed: {stderr.strip()[:1000]}")
            return

        # Collect artifacts
        run_dir_abs = run_dir_input
        if not os.path.isabs(run_dir_abs):
            run_dir_abs = os.path.join(kickoff_dir, run_dir_input)
        if not os.path.isdir(run_dir_abs):
            task_manager.set_task_error(task_id, "Run directory not found after extract.")
            return

        wanted = ["master.txt", "qa.txt", "master.docx", "products.json", "products.md"]
        artifacts = []
        for name in wanted:
            path = os.path.join(run_dir_abs, name)
            if os.path.isfile(path):
                artifacts.append({"name": name, "path": path})

        result_payload = {"run_dir": run_dir_abs, "artifacts": artifacts}
        task_manager.set_task_success(task_id, result_payload)
    except Exception as e:
        logger.exception("Unexpected error in extract task")
        task_manager.set_task_error(task_id, f"Unexpected error: {e}")


@router.post("/fusion/extract")
async def start_extract(background_tasks: BackgroundTasks, run_dir: str = Form(...)):
    if not run_dir:
        raise HTTPException(status_code=400, detail="run_dir is required")
    task_id = task_manager.create_task()
    background_tasks.add_task(_run_extract_background, task_id, run_dir)
    return {"task_id": task_id}


