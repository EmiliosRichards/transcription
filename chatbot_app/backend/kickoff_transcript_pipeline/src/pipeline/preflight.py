import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


SUPPORTED_INPUTS = {
    ".docx": "teams",
    ".txt": "text",
}


@dataclass
class FileCheckResult:
    path: str
    exists: bool
    size_bytes: int
    extension: str
    sha256: str


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def preflight_check(paths: List[Path]) -> Tuple[bool, List[FileCheckResult]]:
    results: List[FileCheckResult] = []
    all_ok = True
    for p in paths:
        exists = p.exists()
        size = p.stat().st_size if exists else 0
        ext = p.suffix.lower() if exists else ""
        sha = compute_sha256(p) if exists else ""
        results.append(
            FileCheckResult(
                path=str(p), exists=exists, size_bytes=size, extension=ext, sha256=sha
            )
        )
        if not exists or size < 1024:
            all_ok = False
    return all_ok, results


def write_preflight_report(out_dir: Path, run_dir: Path, results: List[FileCheckResult]) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "preflight.json"
    serializable: List[Dict[str, str]] = [
        {
            "path": r.path,
            "exists": r.exists,
            "size_bytes": r.size_bytes,
            "extension": r.extension,
            "sha256": r.sha256,
        }
        for r in results
    ]
    report_path.write_text(json.dumps({"inputs": serializable}, indent=2), encoding="utf-8")
    return report_path
