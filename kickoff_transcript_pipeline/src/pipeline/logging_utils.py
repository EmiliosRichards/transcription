import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
import hashlib


class RunLogger:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # Touch file to ensure it exists
        if not self.log_path.exists():
            self.log_path.write_text("", encoding="utf-8")

    def log(self, event: str, payload: Dict[str, Any]) -> None:
        record = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "event": event,
            **payload,
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def sha256_text(text: str) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    return h.hexdigest()
