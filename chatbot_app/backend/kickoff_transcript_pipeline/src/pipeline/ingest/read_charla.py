from pathlib import Path
from typing import Dict, List
import re

# Pattern 1: [mm:ss] Speaker: Text (if exists) — allow optional leading spaces and 1–2 digit minutes
_TIME_LINE_RE = re.compile(r"^\s*\[(\d{1,2}):(\d{2})\]\s*(.+?):\s*(.*)$")
# Pattern 2: (mm:ss-mm:ss) chunk header, followed by free text — allow optional leading spaces and 1–2 digit minutes
_CHUNK_RE = re.compile(r"^\s*\((\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})\)\s*$")


def _mmss_to_seconds(mm: str, ss: str) -> int:
    return int(mm) * 60 + int(ss)


def read_charla_txt(path: Path) -> List[Dict]:
    segments: List[Dict] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # First pass: [mm:ss] Speaker: Text
    for line in lines:
        m = _TIME_LINE_RE.match(line.strip())
        if m:
            mm, ss, speaker, content = m.groups()
            t = _mmss_to_seconds(mm, ss)
            segments.append({
                "source": "charla",
                "t_start": t,
                "t_end": None,
                "speaker": speaker.strip(),
                "text": content.strip(),
                "tokens": None,
            })
    if segments:
        return segments

    # Fallback: (mm:ss-mm:ss) then content till next chunk header
    current_start = None
    buffer: List[str] = []
    for raw in lines:
        line = raw.rstrip()
        m2 = _CHUNK_RE.match(line)
        if m2:
            if current_start is not None:
                segments.append({
                    "source": "charla",
                    "t_start": current_start,
                    "t_end": None,
                    "speaker": "",
                    "text": " ".join(x.strip() for x in buffer if x.strip()),
                    "tokens": None,
                })
            buffer = []
            current_start = _mmss_to_seconds(m2.group(1), m2.group(2))
        else:
            if line:
                buffer.append(line)
    if current_start is not None:
        segments.append({
            "source": "charla",
            "t_start": current_start,
            "t_end": None,
            "speaker": "",
            "text": " ".join(x.strip() for x in buffer if x.strip()),
            "tokens": None,
        })

    return segments
