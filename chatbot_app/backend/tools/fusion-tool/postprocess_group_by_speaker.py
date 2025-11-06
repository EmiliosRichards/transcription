import argparse
import re
from pathlib import Path
from typing import List, Optional, Tuple
import html


TIMESTAMP_SPEAKER_RE = re.compile(r"^\[(?P<ts>\d{1,2}:\d{2}(?::\d{2})?)\]\s+(?P<speaker>.+?):\s*(?P<text>.*)\s*$")


def parse_line(line: str) -> Optional[Tuple[str, str, str]]:
    match = TIMESTAMP_SPEAKER_RE.match(line)
    if not match:
        return None
    ts = match.group("ts")
    speaker = match.group("speaker")
    text = match.group("text")
    return ts, speaker, text


def format_group(
    speaker: str,
    first_ts: str,
    items: List[Tuple[str, str]],
    merge: bool,
) -> List[str]:
    header = f"[{first_ts}] {speaker}:"
    if merge:
        joined = " ".join(t.strip() for _, t in items if t.strip())
        if joined:
            return [f"{header} {joined}"]
        return [header]
    lines = [header]
    for ts, text in items:
        text = text.strip()
        if not text:
            continue
        lines.append(f"[{ts}] {text}")
    return lines


def group_transcript(
    input_text: str,
    decode_html: bool,
    merge: bool,
) -> str:
    output_lines: List[str] = []
    current_speaker: Optional[str] = None
    current_first_ts: Optional[str] = None
    current_items: List[Tuple[str, str]] = []

    def flush_group() -> None:
        nonlocal current_speaker, current_first_ts, current_items
        if current_speaker is None or current_first_ts is None or not current_items:
            # Nothing to flush
            current_speaker = None
            current_first_ts = None
            current_items = []
            return
        output_lines.extend(format_group(current_speaker, current_first_ts, current_items, merge))
        output_lines.append("")  # blank line between groups
        current_speaker = None
        current_first_ts = None
        current_items = []

    for raw_line in input_text.splitlines():
        line = raw_line.rstrip("\n\r")
        parsed = parse_line(line)
        if parsed is None:
            # Non-standard line; flush any open group and pass through as-is
            flush_group()
            if line.strip():
                output_lines.append(line)
            else:
                output_lines.append("")
            continue

        ts, speaker, text = parsed
        if decode_html:
            speaker = html.unescape(speaker)
            text = html.unescape(text)

        if current_speaker is None:
            current_speaker = speaker
            current_first_ts = ts
            current_items = [(ts, text)]
            continue

        if speaker == current_speaker:
            current_items.append((ts, text))
        else:
            flush_group()
            current_speaker = speaker
            current_first_ts = ts
            current_items = [(ts, text)]

    # Final flush
    flush_group()

    # Remove trailing blank line if present
    if output_lines and output_lines[-1] == "":
        output_lines.pop()

    return "\n".join(output_lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Group adjacent transcript lines by speaker. Input lines must look like: "
            "[mm:ss] Speaker Name: text (also supports [hh:mm:ss])."
        )
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to input transcript (e.g., master.txt)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help=(
            "Path to output file. Defaults to '<input_without_ext>_grouped.txt' in the same folder."
        ),
    )
    parser.add_argument(
        "--no-decode-html",
        action="store_true",
        help="Do not HTML-unescape speaker names/text (default is to unescape).",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help=(
            "Merge all lines of a speaker group into one paragraph line (keeps only the first timestamp)."
        ),
    )

    args = parser.parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_name(input_path.stem + "_grouped.txt")

    text = input_path.read_text(encoding="utf-8")
    grouped = group_transcript(
        input_text=text,
        decode_html=not args.no_decode_html,
        merge=args.merge,
    )
    output_path.write_text(grouped, encoding="utf-8")


if __name__ == "__main__":
    main()


