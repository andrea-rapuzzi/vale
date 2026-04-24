import subprocess
import json
from pathlib import Path
from typing import Optional
from ..config import settings


def fetch_channel_videos(url: str) -> tuple[str, list[dict]]:
    """Return (channel_name, list of video metadata dicts) for all videos in channel."""
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-single-json",
        "--no-warnings",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr[:500]}")

    data = json.loads(result.stdout)
    channel_name = data.get("channel") or data.get("uploader") or data.get("title") or "Unknown"
    entries = data.get("entries") or []

    videos = []
    for e in entries:
        if not e or e.get("_type") == "playlist":
            continue
        yt_id = e.get("id") or e.get("url", "").split("v=")[-1]
        if not yt_id:
            continue
        videos.append({
            "youtube_id": yt_id,
            "title": e.get("title") or "Untitled",
            "duration_sec": e.get("duration"),
            "upload_date": e.get("upload_date"),
        })

    return channel_name, videos


def download_vtt(youtube_id: str) -> Optional[Path]:
    """Download auto-generated English VTT for a video. Returns path or None."""
    vtt_dir = settings.vtt_dir_resolved
    vtt_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(vtt_dir / "%(id)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--write-auto-sub",
        "--sub-lang", "en",
        "--sub-format", "vtt",
        "--skip-download",
        "--no-warnings",
        "-o", out_template,
        f"https://www.youtube.com/watch?v={youtube_id}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    # yt-dlp writes {id}.en.vtt
    candidate = vtt_dir / f"{youtube_id}.en.vtt"
    if candidate.exists():
        return candidate

    # Some languages come out as {id}.en-orig.vtt
    for f in vtt_dir.glob(f"{youtube_id}.*.vtt"):
        return f

    return None
