from pathlib import Path
from typing import Dict, List
import re

_CUE_TIME_RE = re.compile(r"^(?P<start>\d{1,2}:\d{2}:\d{2}\.\d{3}|\d{1,2}:\d{2}\.\d{3})\s+-->\s+(?P<end>\d{1,2}:\d{2}:\d{2}\.\d{3}|\d{1,2}:\d{2}\.\d{3}).*$")
_SPEAKER_LINE_RE = re.compile(r"^(?P<speaker>[^:]{1,60}):\s*(?P<text>.+)$")
_V_TAG_RE = re.compile(r"<v\s+([^>]+)>(.*?)</v>", re.IGNORECASE)


def _time_to_seconds(t: str) -> int:
    # t like HH:MM:SS.mmm or MM:SS.mmm
    if t.count(":") == 2:
        h, m, s_ms = t.split(":", 2)
        s = float(s_ms)
        return int(h) * 3600 + int(m) * 60 + int(s)
    else:
        m, s_ms = t.split(":", 1)
        s = float(s_ms)
        return int(m) * 60 + int(s)


def read_teams_vtt(path: Path) -> List[Dict]:
    segments: List[Dict] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    # Skip optional WEBVTT header
    if i < len(lines) and lines[i].strip().upper().startswith("WEBVTT"):
        i += 1

    while i < len(lines):
        # Skip empty and note lines
        if not lines[i].strip() or lines[i].strip().startswith("NOTE"):
            i += 1
            continue

        # Optional cue id
        cue_id_line = lines[i].strip()
        # Next line could be time or time may be on this line (some exports omit id)
        m_time = _CUE_TIME_RE.match(cue_id_line)
        if not m_time:
            i += 1
            if i >= len(lines):
                break
            m_time = _CUE_TIME_RE.match(lines[i].strip())
        if not m_time:
            # Not a cue, move on
            continue
        cue_id = None
        if not _CUE_TIME_RE.match(cue_id_line) and "-->" not in cue_id_line:
            cue_id = cue_id_line

        start_str = m_time.group("start")
        end_str = m_time.group("end")
        t_start = _time_to_seconds(start_str)
        t_end = _time_to_seconds(end_str)
        i += 1

        # Collect text lines until blank line or next cue
        text_buf: List[str] = []
        while i < len(lines) and lines[i].strip():
            text_buf.append(lines[i].strip())
            i += 1

        # Skip trailing blank line
        while i < len(lines) and not lines[i].strip():
            i += 1

        # Join and attempt to split speaker; also parse <v Name> ... </v>
        full_text = " ".join(text_buf).strip()
        speaker = ""
        text_out = full_text
        # Prefer WebVTT <v Name> tags
        v_matches = list(_V_TAG_RE.finditer(full_text))
        if v_matches:
            # If multiple tags, pick the first name; concatenate inner texts
            speaker = v_matches[0].group(1).strip()
            inner_texts = [m.group(2).strip() for m in v_matches]
            text_out = " ".join(t for t in inner_texts if t)
        else:
            m_sp = _SPEAKER_LINE_RE.match(full_text)
            if m_sp:
                speaker = m_sp.group("speaker").strip()
                text_out = m_sp.group("text").strip()
        # Strip any remaining <v> tags if present
        text_out = _V_TAG_RE.sub(lambda m: m.group(2), text_out)

        segments.append({
            "source": "teams",
            "t_start": t_start,
            "t_end": t_end,
            "speaker": speaker,
            "text": text_out,
            "tokens": None,
            "cue_id": cue_id,
        })

    return segments


