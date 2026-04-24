import re
from pathlib import Path

CHUNK_DURATION = 45.0
OVERLAP = 10.0
STEP = CHUNK_DURATION - OVERLAP  # 35s


def _parse_timestamp(ts: str) -> float:
    """Convert HH:MM:SS.mmm or MM:SS.mmm to seconds."""
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(parts[0])


def _clean_text(raw: str) -> str:
    text = re.sub(r"<\d{2}:\d{2}:\d{2}\.\d{3}>", "", raw)
    text = re.sub(r"</?c>", "", text)
    text = re.sub(r"\balign:\S+\s*position:\S+", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(text.split())


def parse_vtt(path: Path) -> list[dict]:
    """Parse a VTT file into list of {start, end, text} dicts."""
    content = path.read_text(encoding="utf-8", errors="replace")
    cues = []

    # Split on blank lines
    blocks = re.split(r"\n{2,}", content)
    timing_re = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{2}:\d{2}[.,]\d{3})"
        r"\s+-->\s+"
        r"(\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{2}:\d{2}[.,]\d{3})"
    )

    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue
        timing_line = None
        text_lines = []
        for i, line in enumerate(lines):
            m = timing_re.search(line)
            if m:
                timing_line = m
                text_lines = lines[i + 1:]
                break
        if timing_line is None:
            continue
        raw_text = " ".join(text_lines)
        text = _clean_text(raw_text)
        if not text:
            continue
        cues.append({
            "start": _parse_timestamp(timing_line.group(1)),
            "end": _parse_timestamp(timing_line.group(2)),
            "text": text,
        })

    return cues


def _deduplicate(cues: list[dict]) -> list[dict]:
    """Remove rolling-caption duplicates where cue N text is a suffix of cue N-1."""
    if not cues:
        return cues
    result = [cues[0]]
    for cue in cues[1:]:
        prev = result[-1]["text"]
        curr = cue["text"]
        # Skip if curr is identical or a suffix of prev
        if prev.endswith(curr) or prev == curr:
            continue
        result.append(cue)
    return result


def parse_and_chunk(vtt_path: Path, video_id: int) -> list[dict]:
    """Parse VTT and return list of chunk dicts ready for DB insertion."""
    cues = parse_vtt(vtt_path)
    cues = _deduplicate(cues)
    if not cues:
        return []

    total_duration = cues[-1]["end"]
    chunks = []
    chunk_index = 0
    window_start = 0.0

    while window_start < total_duration:
        window_end = window_start + CHUNK_DURATION
        window_cues = [
            c for c in cues
            if c["start"] < window_end and c["end"] > window_start
        ]
        if window_cues:
            text = " ".join(c["text"] for c in window_cues)
            chunks.append({
                "video_id": video_id,
                "chunk_index": chunk_index,
                "start_sec": window_start,
                "end_sec": min(window_end, total_duration),
                "text": text,
            })
            chunk_index += 1
        window_start += STEP

    return chunks
