from pathlib import Path
from typing import Dict, List
import re

# Pattern 1: [mm:ss] Speaker: Text (existing)
_TIME_LINE_RE = re.compile(r"^\[(\d{2}):(\d{2})\]\s*(.+?):\s*(.*)$")
# Pattern 2: Speaker Name | mm:ss (header line), with text on subsequent lines
_HEADER_RE = re.compile(r"^(?P<speaker>.+?)\s*\|\s*(?P<mm>\d{2}):(?P<ss>\d{2})\s*$")


def _mmss_to_seconds(mm: str, ss: str) -> int:
    return int(mm) * 60 + int(ss)


def read_krisp_txt(path: Path) -> List[Dict]:
    segments: List[Dict] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # First pass: try [mm:ss] format quickly
    for line in lines:
        m = _TIME_LINE_RE.match(line.strip())
        if m:
            mm, ss, speaker, content = m.groups()
            t = _mmss_to_seconds(mm, ss)
            segments.append({
                "source": "krisp",
                "t_start": t,
                "t_end": None,
                "speaker": speaker.strip(),
                "text": content.strip(),
                "tokens": None,
            })
    if segments:
        return segments

    # Fallback: parse header blocks 'Speaker | mm:ss' with text until next header
    current = None
    buffer: List[str] = []
    for raw in lines:
        line = raw.rstrip()
        m2 = _HEADER_RE.match(line)
        if m2:
            # flush previous
            if current is not None:
                segments.append({
                    "source": "krisp",
                    "t_start": current["t_start"],
                    "t_end": None,
                    "speaker": current["speaker"],
                    "text": " ".join(x.strip() for x in buffer if x.strip()),
                    "tokens": None,
                })
            buffer = []
            mm = m2.group("mm"); ss = m2.group("ss")
            speaker = m2.group("speaker").strip()
            current = {"t_start": _mmss_to_seconds(mm, ss), "speaker": speaker}
        else:
            buffer.append(line)
    if current is not None:
        segments.append({
            "source": "krisp",
            "t_start": current["t_start"],
            "t_end": None,
            "speaker": current["speaker"],
            "text": " ".join(x.strip() for x in buffer if x.strip()),
            "tokens": None,
        })

    return segments
