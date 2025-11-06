import os
import sys
import json
import math
import argparse
import re
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
from tempfile import TemporaryDirectory
from typing import List, Optional

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore
except Exception:  # pragma: no cover
    def load_dotenv(*args, **kwargs):  # type: ignore
        return None
    def find_dotenv(*args, **kwargs):  # type: ignore
        return ""


DEFAULTS = {
    "model": os.environ.get("TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe"),
    "language": os.environ.get("TRANSCRIPTION_LANGUAGE", None),  # e.g., "de"
    "input_dir": os.path.join(os.path.dirname(__file__), "input"),
    "output_dir": os.path.join(os.path.dirname(__file__), "output"),
    # Chunking thresholds
    "whisper_max_mb": 24.0,
    "gpt_max_mb": 95.0,
    "gpt_max_duration_sec": 1800,  # 30 minutes
    # Hard cap for a single GPT chunk (model limit ~1400s). Keep a safety margin
    "gpt_chunk_max_sec": 1380,
    # Target chunk size tuning
    "target_chunk_mb": 20.0,
    "min_chunk_sec": 120,
}


def ensure_env():
    try:
        path = find_dotenv(usecwd=True)
        if path:
            load_dotenv(path)
        else: load_dotenv()
    except Exception:
        pass


def response_to_dict(resp) -> dict:
    try:
        if hasattr(resp, "model_dump"):
            return resp.model_dump()
        if hasattr(resp, "to_dict"):
            return resp.to_dict()
    except Exception:
        pass
    try:
        return json.loads(json.dumps(resp, default=lambda o: getattr(o, "__dict__", str(o))))
    except Exception:
        return {"_note": "could_not_serialize_response"}


def list_audio_files(input_dir: str) -> List[str]:
    exts = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".webm", ".mp4"}
    files: List[str] = []
    try:
        for name in sorted(os.listdir(input_dir)):
            p = os.path.join(input_dir, name)
            if os.path.isfile(p) and os.path.splitext(name)[1].lower() in exts:
                files.append(p)
    except Exception:
        pass
    return files


def size_mb(path: str) -> float:
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except Exception:
        return 0.0


def ffprobe_duration_sec(path: str) -> float:
    ffprobe = shutil_which("ffprobe")
    if not ffprobe:
        return 0.0
    try:
        out = subprocess.check_output([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", path], stderr=subprocess.STDOUT)
        return float(out.decode("utf-8", errors="ignore").strip())
    except Exception:
        return 0.0


def shutil_which(name: str) -> Optional[str]:
    try:
        import shutil
        return shutil.which(name)
    except Exception:
        return None


def normalize_language(lang: Optional[str]) -> Optional[str]:
    if not lang:
        return None
    s = lang.strip().lower()
    if s in {"de", "de-de", "de_de", "german", "deutsch"}:
        return "de"
    return s


# ---- VTT utilities ----
def _parse_timestamp_to_seconds(ts: str) -> float:
    s = ts.strip().replace(',', '.')
    parts = s.split(':')
    try:
        if len(parts) == 3:
            hh = int(parts[0])
            mm = int(parts[1])
            ss = float(parts[2])
            return hh * 3600 + mm * 60 + ss
        if len(parts) == 2:
            mm = int(parts[0])
            ss = float(parts[1])
            return mm * 60 + ss
    except Exception:
        return 0.0
    return 0.0


def _format_seconds_to_timestamp(sec: float) -> str:
    if sec < 0:
        sec = 0.0
    ms = int(round((sec - int(sec)) * 1000))
    total = int(sec)
    hh = total // 3600
    mm = (total % 3600) // 60
    ss = total % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}.{ms:03d}"


def parse_vtt(vtt_path: str) -> List[dict]:
    cues: List[dict] = []
    try:
        with open(vtt_path, 'r', encoding='utf-8') as f:
            lines = [ln.rstrip('\n') for ln in f]
    except Exception:
        return cues

    i = 0
    n = len(lines)
    time_pat = re.compile(r"^(\d{1,2}:\d{2}:\d{2}[\.,]\d{3}|\d{1,2}:\d{2}[\.,]\d{3})\s+-->\s+(\d{1,2}:\d{2}:\d{2}[\.,]\d{3}|\d{1,2}:\d{2}[\.,]\d{3})")
    while i < n:
        line = lines[i].strip()
        i += 1
        if not line or line.upper().startswith('WEBVTT'):
            continue
        m = time_pat.match(line)
        if not m:
            continue
        start_ts, end_ts = m.group(1), m.group(2)
        txt_lines: List[str] = []
        while i < n and lines[i].strip() != "":
            txt_lines.append(lines[i].rstrip())
            i += 1
        # skip blank separator
        while i < n and lines[i].strip() == "":
            i += 1

        raw_text = " ".join(t.strip() for t in txt_lines if t.strip())
        speaker = ""
        text = raw_text
        # Prefer Teams <v Speaker>…</v> tags
        v_matches = re.findall(r"<\s*v\s+([^>]+)>(.*?)<\s*/\s*v\s*>", raw_text, flags=re.IGNORECASE)
        if v_matches:
            speaker = v_matches[0][0].strip()
            # Join all text parts inside <v> tags; if none, fallback to raw
            joined = " ".join(part.strip() for _, part in v_matches if part.strip())
            text = joined or text
        else:
            # Fallback: "Speaker: text"
            msp = re.match(r"^\s*([^:]{1,80}):\s*(.*)$", raw_text)
            if msp:
                speaker = msp.group(1).strip()
                text = msp.group(2).strip()
        # Strip any residual HTML/XML tags
        text = re.sub(r"<[^>]+>", "", text).strip()
        start_sec = _parse_timestamp_to_seconds(start_ts)
        end_sec = _parse_timestamp_to_seconds(end_ts)
        if end_sec <= start_sec:
            end_sec = start_sec
        cues.append({
            "start": start_sec,
            "end": end_sec,
            "speaker": speaker or "Unknown",
            "text": text,
        })
    return cues


def _normalize_token_list(text: str) -> List[str]:
    return [t.lower() for t in re.findall(r"\w+", text or "", flags=re.UNICODE)]


def filter_cues_by_overlap_policy(
    cues: List[dict],
    *,
    policy: str,
    overlap_min_sec: float,
    overlap_min_ratio: float,
    backchannel_token_max: int,
    backchannel_patterns: List[str],
) -> List[dict]:
    if policy == "keep" or not cues:
        return cues
    patterns_set = {p.strip().lower() for p in backchannel_patterns if p.strip()}
    n = len(cues)
    # Precompute overlaps
    result: List[dict] = []
    for i in range(n):
        c = cues[i]
        c_start = float(c["start"]) ; c_end = float(c["end"]) ; c_dur = max(0.0, c_end - c_start)
        tokens = _normalize_token_list(c.get("text", ""))
        is_backchannel = False
        if tokens and len(tokens) <= max(0, int(backchannel_token_max)):
            # single short token or two short tokens common in backchannels
            if all((tok in patterns_set) for tok in tokens) or any((tok in patterns_set) for tok in tokens):
                is_backchannel = True
        # compute max overlap ratio against other speakers
        max_ratio = 0.0
        for j in range(n):
            if i == j:
                continue
            d = cues[j]
            if d["speaker"] == c["speaker"]:
                continue
            d_start = float(d["start"]) ; d_end = float(d["end"]) ;
            ov = max(0.0, min(c_end, d_end) - max(c_start, d_start))
            if c_dur > 0:
                max_ratio = max(max_ratio, ov / c_dur)
        short_and_overlapped = (c_dur <= max(0.0, overlap_min_sec)) and (max_ratio >= max(0.0, min(1.0, overlap_min_ratio)))
        micro = short_and_overlapped or is_backchannel
        if policy in {"drop-micro", "collapse-to-primary"} and micro:
            # skip this cue entirely
            continue
        result.append(c)
    return result


def _split_range_by_limit(start: float, end: float, limit: float) -> List[tuple]:
    if end <= start or limit <= 0:
        return []
    segments = []
    cur = start
    while cur < end - 1e-6:
        nxt = min(end, cur + limit)
        segments.append((cur, nxt))
        cur = nxt
    return segments


def build_segments(cues: List[dict], mode: str, window_sec: int, pad_sec: float, media_duration: float, *, is_gpt: bool, join_gap_sec: float = 0.5, min_seg_sec: float = 0.0) -> List[dict]:
    if not cues:
        return []
    cues = sorted(cues, key=lambda c: (c["start"], c["end"]))
    max_chunk = DEFAULTS["gpt_chunk_max_sec"] if is_gpt else max(window_sec, DEFAULTS["min_chunk_sec"])
    segments: List[dict] = []

    if mode == "speaker-strict":
        cur = None
        for c in cues:
            if cur is None:
                cur = {"speaker": c["speaker"], "start": c["start"], "end": c["end"], "src_count": 1}
                continue
            # merge if same speaker and contiguous/overlapping and within window
            same_speaker = (c["speaker"] == cur["speaker"])
            proposed_end = max(cur["end"], c["end"])
            # allow a configurable small gap between utterances for merges
            if same_speaker and (c["start"] <= cur["end"] + max(0.0, join_gap_sec)) and (proposed_end - cur["start"] <= window_sec):
                cur["end"] = proposed_end
                cur["src_count"] = cur.get("src_count", 1) + 1
            else:
                # split cur if above hard cap
                if cur["end"] - cur["start"] > max_chunk:
                    for s, e in _split_range_by_limit(cur["start"], cur["end"], max_chunk):
                        segments.append({"speaker": cur["speaker"], "start": s, "end": e, "src_count": cur.get("src_count", 1)})
                else:
                    segments.append(cur)
                cur = {"speaker": c["speaker"], "start": c["start"], "end": c["end"], "src_count": 1}
        if cur is not None:
            if cur["end"] - cur["start"] > max_chunk:
                for s, e in _split_range_by_limit(cur["start"], cur["end"], max_chunk):
                    segments.append({"speaker": cur["speaker"], "start": s, "end": e, "src_count": cur.get("src_count", 1)})
            else:
                segments.append(cur)
    else:
        # no-dup: create a single non-overlapping timeline; for simplicity merge by time
        timeline: List[tuple] = []
        for c in cues:
            timeline.append((c["start"], 'start'))
            timeline.append((c["end"], 'end'))
        # not used in this implementation; default to simple time slicing across cues
        last = cues[0]["start"]
        for c in cues:
            if c["start"] > last:
                segments.append({"speaker": c["speaker"], "start": last, "end": c["start"]})
            segments.append({"speaker": c["speaker"], "start": c["start"], "end": c["end"]})
            last = c["end"]

    # ensure minimum length by merging forward within same speaker when possible
    if min_seg_sec and min_seg_sec > 0:
        merged: List[dict] = []
        for seg in segments:
            if merged and seg["speaker"] == merged[-1]["speaker"] and (seg["start"] <= merged[-1]["end"] + max(0.0, join_gap_sec)):
                # if previous is shorter than min, extend it by merging
                prev = merged[-1]
                if (prev["end"] - prev["start"]) < min_seg_sec:
                    prev["end"] = seg["end"]
                    prev["src_count"] = prev.get("src_count", 1) + seg.get("src_count", 1)
                    continue
            merged.append(seg)
        segments = merged

    # apply padding and clamp
    out: List[dict] = []
    for s in segments:
        st = max(0.0, s["start"] - pad_sec)
        en = min(media_duration, s["end"] + pad_sec)
        if en > st:
            out.append({"speaker": s["speaker"], "start": st, "end": en, "src_count": s.get("src_count", 1)})
    return out


def clip_audio_segment(src_path: str, start: float, end: float, out_dir: str) -> Optional[str]:
    ffmpeg = shutil_which("ffmpeg")
    if not ffmpeg:
        return None
    base = f"seg_{int(start*1000):010d}_{int(end*1000):010d}"
    m4a_path = os.path.join(out_dir, base + ".m4a")
    wav_path = os.path.join(out_dir, base + ".wav")
    # Try stream copy to m4a first
    cmd_copy = [ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", f"{start}", "-to", f"{end}", "-i", src_path, "-vn", "-acodec", "copy", m4a_path]
    try:
        subprocess.run(cmd_copy, check=True)
        if os.path.exists(m4a_path) and size_mb(m4a_path) > 0:
            return m4a_path
    except Exception:
        pass
    # Fallback to WAV transcode
    cmd_wav = [ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error", "-ss", f"{start}", "-to", f"{end}", "-i", src_path, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav_path]
    try:
        subprocess.run(cmd_wav, check=True)
        if os.path.exists(wav_path) and size_mb(wav_path) > 0:
            return wav_path
    except Exception:
        return None
    return None


def _process_segment_for_transcription(seg: dict, *, src_path: str, model: str, language: Optional[str], want_ts: bool, debug: bool, vocab_hint: Optional[str]) -> dict:
    from tempfile import TemporaryDirectory as _TD
    with _TD() as td:
        out = {
            "speaker": seg["speaker"],
            "start": seg["start"],
            "end": seg["end"],
            "text": "",
        }
        # Enrichment
        try:
            out["duration"] = float(max(0.0, seg["end"] - seg["start"]))
        except Exception:
            out["duration"] = 0.0
        out["source_cue_count"] = int(seg.get("src_count", 1))
        clipped = clip_audio_segment(src_path, seg["start"], seg["end"], td)
        if not clipped:
            out["error"] = "clip_failed"
            return out
        try:
            from openai import OpenAI  # type: ignore
            client = OpenAI()
            resp = transcribe_one(client, model, clipped, language, want_ts, prompt=vocab_hint)
            data = response_to_dict(resp)
            text = None
            if isinstance(data, dict):
                text = data.get("text") or None
                if not text:
                    segs = data.get("segments")
                    if isinstance(segs, list):
                        try:
                            text = "\n".join(str(s.get("text", "")).strip() for s in segs)
                        except Exception:
                            text = None
            out["text"] = text or ""
            out["raw"] = data
        except Exception as e:
            out["error"] = str(e)
        return out


def transcribe_segments_vtt(src_path: str, segments: List[dict], *, model: str, language: Optional[str], jobs: int, debug: bool, vocab_hint: Optional[str]) -> List[dict]:
    want_ts = False
    results: List[dict] = []
    if jobs <= 1:
        for seg in segments:
            results.append(_process_segment_for_transcription(seg, src_path=src_path, model=model, language=language, want_ts=want_ts, debug=debug, vocab_hint=vocab_hint))
        return results
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        futs = [ex.submit(_process_segment_for_transcription, seg, src_path=src_path, model=model, language=language, want_ts=want_ts, debug=debug, vocab_hint=vocab_hint) for seg in segments]
        for f in as_completed(futs):
            try:
                results.append(f.result())
            except Exception as e:
                results.append({"error": str(e)})
    # preserve chronological order
    results.sort(key=lambda r: (r.get("start", 0.0), r.get("end", 0.0)))
    return results


def _redistribute_text_over_cues(text: str, cues: List[dict]) -> List[str]:
    # Split text into tokens and allocate to cues proportionally by duration
    tokens = re.findall(r"\S+", text or "")
    total = len(tokens)
    if total == 0 or not cues:
        return [""] * len(cues)
    durs = [max(0.0, c["end"] - c["start"]) for c in cues]
    total_dur = sum(durs) or len(cues)
    alloc = [int((d / total_dur) * total) for d in durs]
    # distribute remainder
    remainder = total - sum(alloc)
    i = 0
    while remainder > 0:
        alloc[i % len(alloc)] += 1
        remainder -= 1
        i += 1
    out = []
    idx = 0
    for n in alloc:
        out.append(" ".join(tokens[idx: idx + n]))
        idx += n
    # In case of rounding, append leftovers to last cue
    if idx < total:
        out[-1] = (out[-1] + (" " if out[-1] else "") + " ".join(tokens[idx:])).strip()
    return out


def write_outputs_vtt(base_out: str, *, model: str, vtt_source: str, segments: List[dict], original_cues: Optional[List[dict]] = None) -> None:
    # If original_cues provided, realign output to exact Teams cue timings and speakers
    if original_cues:
        # Build empty text buckets per original cue
        cue_texts: List[str] = [""] * len(original_cues)
        # For each segment, distribute its text across overlapping original cues for the same speaker
        for s in sorted(segments, key=lambda x: (float(x.get("start", 0.0)), float(x.get("end", 0.0)))):
            sp = s.get("speaker", "")
            s_start = float(s.get("start", 0.0))
            s_end = float(s.get("end", 0.0))
            # gather overlapping cues indices
            cue_idxs = [i for i, c in enumerate(original_cues) if c["speaker"] == sp and c["start"] < s_end and c["end"] > s_start]
            if not cue_idxs:
                continue
            cues_subset = [original_cues[i] for i in cue_idxs]
            pieces = _redistribute_text_over_cues(s.get("text", "") or "", cues_subset)
            for idx_local, ci in enumerate(cue_idxs):
                if pieces[idx_local]:
                    cue_texts[ci] = (cue_texts[ci] + (" " if cue_texts[ci] else "") + pieces[idx_local]).strip()
        # Build final segments aligned to original cue times (no padding)
        segments_for_output = [{"speaker": c["speaker"], "start": c["start"], "end": c["end"], "text": cue_texts[i]} for i, c in enumerate(original_cues)]
    else:
        segments_for_output = segments

    data = {"model": model, "vtt_source": vtt_source, "segments": segments_for_output, "text": "\n\n".join([s.get("text", "") for s in segments_for_output if s.get("text")])}
    json_path = base_out + ".vtt_guided.json"
    txt_path = base_out + ".vtt_guided.txt"
    vtt_path = base_out + ".vtt_guided.vtt"
    try:
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, 'w', encoding='utf-8') as jf:
            json.dump(data, jf, ensure_ascii=False, indent=2)
        with open(txt_path, 'w', encoding='utf-8') as tf:
            for s in segments_for_output:
                t0 = _format_seconds_to_timestamp(float(s.get("start", 0.0)))
                sp = str(s.get("speaker", ""))
                line = str(s.get("text", "")).strip()
                tf.write(f"{t0} - {sp}: {line}\n")
        with open(vtt_path, 'w', encoding='utf-8') as vf:
            vf.write("WEBVTT\n\n")
            for idx, s in enumerate(segments_for_output, start=1):
                t0 = _format_seconds_to_timestamp(float(s.get("start", 0.0)))
                t1 = _format_seconds_to_timestamp(float(s.get("end", 0.0)))
                sp = str(s.get("speaker", ""))
                line = str(s.get("text", "")).strip()
                vf.write(f"{idx}\n")
                vf.write(f"{t0} --> {t1}\n")
                vf.write(f"{sp}: {line}\n\n")
    except Exception as e:
        print(f"Writing VTT-guided outputs failed: {e}", file=sys.stderr)


def transcribe_with_vtt(path: str, vtt_path: str, out_dir: str, *, model: str, language: Optional[str], vtt_mode: str, window_sec: int, pad_sec: float, jobs: int, debug: bool, vocab_hint: Optional[str], join_gap_sec: float = 0.5, min_seg_sec: float = 0.0, overlap_policy: str = "drop-micro", overlap_min_sec: float = 1.2, overlap_min_ratio: float = 0.7, backchannel_token_max: int = 2, backchannel_patterns: Optional[List[str]] = None, final_align: str = "segment") -> int:
    dur = ffprobe_duration_sec(path)
    cues = parse_vtt(vtt_path)
    if not cues:
        print("No cues parsed from VTT.")
        return 2
    # Overlap/micro suppression
    if backchannel_patterns is None:
        backchannel_patterns = ["hm", "mhm", "ja", "ok", "okay", "äh", "ähm", "hmm", "genau", "ne", "nee", "jo"]
    cues = filter_cues_by_overlap_policy(
        cues,
        policy=overlap_policy,
        overlap_min_sec=overlap_min_sec,
        overlap_min_ratio=overlap_min_ratio,
        backchannel_token_max=backchannel_token_max,
        backchannel_patterns=backchannel_patterns,
    )
    model_lc = model.lower()
    is_gpt = ("gpt-4o" in model_lc) and ("transcribe" in model_lc)
    segments = build_segments(cues, vtt_mode, window_sec, pad_sec, dur, is_gpt=is_gpt, join_gap_sec=join_gap_sec, min_seg_sec=min_seg_sec)
    if not segments:
        print("No segments generated from VTT.")
        return 2
    results = transcribe_segments_vtt(path, segments, model=model, language=language, jobs=jobs, debug=debug, vocab_hint=vocab_hint)
    base = os.path.splitext(os.path.basename(path))[0]
    base_out = os.path.join(out_dir, base)
    # Final alignment mode
    if final_align == "original":
        write_outputs_vtt(base_out, model=model, vtt_source=os.path.basename(vtt_path), segments=results, original_cues=cues)
    else:
        write_outputs_vtt(base_out, model=model, vtt_source=os.path.basename(vtt_path), segments=results)
    print(f"Saved:\n- JSON: {base_out}.vtt_guided.json\n- TXT:  {base_out}.vtt_guided.txt\n- VTT:  {base_out}.vtt_guided.vtt")
    return 0

def transcribe_one(client, model: str, path: str, language: Optional[str], want_timestamps: bool, prompt: Optional[str] = None):
    # Load bytes into memory to avoid file-handle lifecycle issues on Windows/threads
    with open(path, "rb") as f:
        data = f.read()
    bio = io.BytesIO(data)
    setattr(bio, "name", os.path.basename(path))
    kwargs = {"model": model, "file": bio}
    model_lc = model.lower()
    is_whisper = model_lc.startswith("whisper")
    is_gpt = ("gpt-4o" in model_lc) and ("transcribe" in model_lc)
    # Choose format per model support
    kwargs["response_format"] = "verbose_json" if (want_timestamps and is_whisper) else "json"
    lang_norm = normalize_language(language)
    if lang_norm:
        kwargs["language"] = lang_norm
    if want_timestamps and is_gpt:
        kwargs["timestamp_granularities"] = ["segment"]
        if prompt:
            kwargs["prompt"] = str(prompt)
    try:
        return client.audio.transcriptions.create(**kwargs)
    except Exception:
        # Retry without granularities and force json
        kwargs.pop("timestamp_granularities", None)
        kwargs["response_format"] = "json"
        kwargs.pop("prompt", None)  # in case model doesn't support it
        # Recreate BytesIO to reset stream position
        bio2 = io.BytesIO(data)
        setattr(bio2, "name", os.path.basename(path))
        kwargs["file"] = bio2
        return client.audio.transcriptions.create(**kwargs)


def transcribe_file(path: str, out_dir: str, *, model: str, language: Optional[str], debug: bool, vocab_hint: Optional[str] = None) -> int:
    # Initialize client
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        print("openai package is required. pip install openai>=1.0.0", file=sys.stderr)
        print(str(e), file=sys.stderr)
        return 2
    client = OpenAI()

    here = os.path.dirname(os.path.abspath(__file__))
    ffmpeg = shutil_which("ffmpeg")
    ffprobe = shutil_which("ffprobe")
    if debug:
        try:
            import openai as _openai_pkg  # type: ignore
            ver = getattr(_openai_pkg, "__version__", "unknown")
        except Exception:
            ver = "unknown"
        print(f"[debug] openai-py version: {ver}")
        print(f"[debug] ffmpeg: {'present' if ffmpeg else 'missing'}; ffprobe: {'present' if ffprobe else 'missing'}")

    model_lc = model.lower()
    is_whisper = model_lc.startswith("whisper")
    is_gpt = ("gpt-4o" in model_lc) and ("transcribe" in model_lc)
    want_ts = bool(is_gpt)

    src_path = path
    sz_mb = size_mb(src_path)

    # First attempt: audio-only extraction (no re-encode) to reduce size
    if ffmpeg:
        audio_only = os.path.join(os.path.dirname(src_path), f"{os.path.splitext(os.path.basename(src_path))[0]}_audio.m4a")
        try:
            subprocess.run([ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", src_path, "-vn", "-acodec", "copy", audio_only], check=True)
            a_mb = size_mb(audio_only)
            if a_mb > 0:
                src_path = audio_only
                sz_mb = a_mb
            if debug:
                dur = ffprobe_duration_sec(src_path)
                print(f"[debug] audio-only path: {src_path}; size_mb={sz_mb:.2f}; duration_sec={dur:.1f}")
        except Exception:
            pass

    # Decide if chunking is needed
    dur_sec = ffprobe_duration_sec(src_path) if ffprobe else 0.0
    size_threshold = DEFAULTS["whisper_max_mb"] if is_whisper else DEFAULTS["gpt_max_mb"] if is_gpt else 50.0
    needs_chunk = (sz_mb >= size_threshold) or (is_gpt and dur_sec > DEFAULTS["gpt_max_duration_sec"])

    if ffmpeg and needs_chunk:
        n = max(2, int(math.ceil(sz_mb / max(1.0, DEFAULTS["target_chunk_mb"])) ))
        base_seg_time = max(DEFAULTS["min_chunk_sec"], int(math.ceil((dur_sec or 600) / n)))
        # Ensure GPT chunks respect model's max duration cap
        seg_time = min(base_seg_time, DEFAULTS["gpt_chunk_max_sec"]) if is_gpt else base_seg_time
        with TemporaryDirectory() as td:
            out_pat = os.path.join(td, "chunk_%03d.m4a")
            cmd_copy = [ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", src_path, "-vn", "-acodec", "copy", "-f", "segment", "-segment_time", str(seg_time), "-reset_timestamps", "1", out_pat]
            ok = True
            try:
                subprocess.run(cmd_copy, check=True)
            except Exception:
                ok = False
            if not ok:
                cmd_enc = [ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", src_path, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "aac", "-b:a", "96k", "-f", "segment", "-segment_time", str(seg_time), "-reset_timestamps", "1", out_pat]
                try:
                    subprocess.run(cmd_enc, check=True)
                except Exception:
                    out_pat = ""

            chunk_paths: List[str] = []
            if out_pat:
                try:
                    names = sorted([n for n in os.listdir(td) if n.startswith("chunk_")])
                    for nm in names:
                        chunk_paths.append(os.path.join(td, nm))
                except Exception:
                    chunk_paths = []

            if chunk_paths:
                print(f"Chunking enabled: {len(chunk_paths)} chunks (~{seg_time}s each)")
                raw_chunks = []
                texts: List[str] = []
                for idx, cp in enumerate(chunk_paths):
                    try:
                        resp = transcribe_one(client, model, cp, language, want_ts, prompt=vocab_hint)
                        data_i = response_to_dict(resp)
                        raw_chunks.append({"index": idx, "file": os.path.basename(cp), "response": data_i})
                        t_i = None
                        if isinstance(data_i, dict):
                            t_i = data_i.get("text") or None
                            segs_i = data_i.get("segments")
                            if not t_i and isinstance(segs_i, list):
                                t_i = "\n".join(str(s.get("text", "")).strip() for s in segs_i)
                        texts.append(t_i or "")
                    except Exception as e:
                        raw_chunks.append({"index": idx, "file": os.path.basename(cp), "error": str(e)})
                        texts.append("")

                combined_text = ("\n\n").join([t for t in texts if t])
                base = os.path.splitext(os.path.basename(path))[0]
                out_json = os.path.join(out_dir, f"{base}.json")
                out_txt = os.path.join(out_dir, f"{base}.txt")
                data = {
                    "model": model,
                    "chunking": {"strategy": "segment_time", "segment_time_sec": seg_time},
                    "chunks": raw_chunks,
                    "text": combined_text,
                }
                try:
                    os.makedirs(out_dir, exist_ok=True)
                    with open(out_json, "w", encoding="utf-8") as jf:
                        json.dump(data, jf, ensure_ascii=False, indent=2)
                    with open(out_txt, "w", encoding="utf-8") as tf:
                        tf.write(combined_text)
                except Exception as e:
                    print(f"Writing outputs failed: {e}", file=sys.stderr)
                    return 2
                print(f"Saved:\n- JSON: {out_json}\n- TXT:  {out_txt}")
                return 0

    # Single-shot path with fallbacks
    model_lc = model.lower()
    is_whisper = model_lc.startswith("whisper")
    is_gpt = ("gpt-4o" in model_lc) and ("transcribe" in model_lc)
    try:
        resp = transcribe_one(client, model, src_path, language, want_ts, prompt=vocab_hint)
    except Exception as e:
        detail = str(e)
        if is_whisper and sz_mb >= DEFAULTS["whisper_max_mb"] and ffmpeg:
            try:
                small_path = os.path.join(os.path.dirname(src_path), f"{os.path.splitext(os.path.basename(src_path))[0]}_small.m4a")
                subprocess.run([ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", src_path, "-ac", "1", "-ar", "16000", "-c:a", "aac", "-b:a", "48k", small_path], check=True)
                resp = transcribe_one(client, model, small_path, language, want_ts, prompt=vocab_hint)
            except Exception:
                print(f"Transcription failed: {detail}", file=sys.stderr)
                return 2
        elif is_gpt and ffmpeg and not src_path.lower().endswith(".wav"):
            try:
                wav_path = os.path.join(os.path.dirname(src_path), f"{os.path.splitext(os.path.basename(src_path))[0]}_audio.wav")
                subprocess.run([ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", src_path, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav_path], check=True)
                resp = transcribe_one(client, model, wav_path, language, want_ts, prompt=vocab_hint)
            except Exception:
                print(f"Transcription failed: {detail}", file=sys.stderr)
                return 2
        else:
            print(f"Transcription failed: {detail}", file=sys.stderr)
            return 2

    data = response_to_dict(resp)
    base = os.path.splitext(os.path.basename(path))[0]
    out_json = os.path.join(out_dir, f"{base}.json")
    out_txt = os.path.join(out_dir, f"{base}.txt")

    text = None
    if isinstance(data, dict):
        text = data.get("text")
        if not text:
            segs = data.get("segments")
            if isinstance(segs, list):
                try:
                    text = "\n".join(str(s.get("text", "")).strip() for s in segs)
                except Exception:
                    text = None
    if not text:
        text = ""

    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(out_json, "w", encoding="utf-8") as jf:
            json.dump(data, jf, ensure_ascii=False, indent=2)
        with open(out_txt, "w", encoding="utf-8") as tf:
            tf.write(text)
    except Exception as e:
        print(f"Writing outputs failed: {e}", file=sys.stderr)
        return 2
    print(f"Saved:\n- JSON: {out_json}\n- TXT:  {out_txt}")
    return 0


def main() -> int:
    ensure_env()
    parser = argparse.ArgumentParser(description="Simple transcriber with chunking and safe fallbacks")
    parser.add_argument("--input", default=DEFAULTS["input_dir"], help="Input folder or single audio file path")
    parser.add_argument("--output", default=DEFAULTS["output_dir"], help="Output folder for JSON/TXT")
    parser.add_argument("--model", default=DEFAULTS["model"], help="Model: whisper-1, gpt-4o-transcribe, gpt-4o-mini-transcribe")
    parser.add_argument("--language", default=DEFAULTS["language"], help="Optional language hint (e.g., de)")
    parser.add_argument("--debug", action="store_true", help="Print diagnostics and extra checks")
    # VTT-guided options
    parser.add_argument("--vtt", default=None, help="Optional path to Teams VTT to guide segmentation")
    parser.add_argument("--vtt-mode", default="speaker-strict", choices=["no-dup", "speaker-strict"], help="Overlap handling mode for VTT-driven segmentation")
    parser.add_argument("--window-sec", type=int, default=90, help="Target max window seconds for merging consecutive same-speaker cues")
    parser.add_argument("--pad-sec", type=float, default=0.5, help="Padding seconds added on both sides of each VTT-guided segment")
    parser.add_argument("--jobs", type=int, default=2, help="Parallel segment transcriptions")
    parser.add_argument("--vocab-hint", default=None, help="Comma-separated preferred terms/names to help recognition")
    parser.add_argument("--join-gap-sec", type=float, default=0.5, help="Merge same-speaker gaps up to N seconds")
    parser.add_argument("--min-seg-sec", type=float, default=0.0, help="Best-effort minimum segment length for same-speaker windows")
    parser.add_argument("--overlap-policy", default="drop-micro", choices=["keep", "drop-micro", "collapse-to-primary"], help="How to handle micro overlapping cues")
    parser.add_argument("--overlap-min-sec", type=float, default=1.2, help="Duration threshold for micro-overlap detection")
    parser.add_argument("--overlap-min-ratio", type=float, default=0.7, help="Minimum overlap ratio (0-1) vs other speaker to count as micro")
    parser.add_argument("--backchannel-token-max", type=int, default=2, help="Max tokens to consider a cue a backchannel")
    parser.add_argument("--backchannel-patterns", default="hm,mhm,ja,ok,okay,äh,ähm,hmm,genau,ne,nee,jo", help="Comma-separated list of backchannel tokens")
    parser.add_argument("--final-align", default="segment", choices=["segment", "original"], help="Final alignment mode for outputs")
    args = parser.parse_args()

    inp = args.input
    out_dir = args.output
    model = args.model
    language = args.language
    debug = args.debug
    vocab_hint = args.vocab_hint
    join_gap_sec = args.join_gap_sec
    min_seg_sec = args.min_seg_sec
    overlap_policy = args.overlap_policy
    overlap_min_sec = args.overlap_min_sec
    overlap_min_ratio = args.overlap_min_ratio
    backchannel_token_max = args.backchannel_token_max
    backchannel_patterns = [t.strip() for t in str(args.backchannel_patterns).split(',') if t.strip()]
    final_align = args.final_align

    # Normalize input: file vs directory
    inputs: List[str] = []
    if os.path.isdir(inp):
        inputs = list_audio_files(inp)
        if not inputs:
            print(f"No supported audio files found in '{inp}'.")
            return 1
    elif os.path.isfile(inp):
        inputs = [inp]
    else:
        print(f"Input not found: {inp}")
        return 2

    os.makedirs(out_dir, exist_ok=True)

    # If VTT is provided, require a single file and run VTT-guided path
    if args.vtt:
        if len(inputs) != 1:
            print("When using --vtt, please provide a single file via --input.")
            return 2
        return transcribe_with_vtt(
            inputs[0], args.vtt, out_dir,
            model=model, language=language,
            vtt_mode=args.vtt_mode,
            window_sec=args.window_sec, pad_sec=args.pad_sec, jobs=args.jobs, debug=debug,
            vocab_hint=vocab_hint, join_gap_sec=join_gap_sec, min_seg_sec=min_seg_sec,
            overlap_policy=overlap_policy, overlap_min_sec=overlap_min_sec, overlap_min_ratio=overlap_min_ratio,
            backchannel_token_max=backchannel_token_max, backchannel_patterns=backchannel_patterns,
            final_align=final_align,
        )
    errs = 0
    for p in inputs:
        print(f"\n=== Processing: {p}")
        rc = transcribe_file(p, out_dir, model=model, language=language, debug=debug, vocab_hint=vocab_hint)
        if rc != 0:
            errs += 1

    if errs:
        print(f"\nCompleted with {errs} error(s).")
        return 2
    print("\nAll files processed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

