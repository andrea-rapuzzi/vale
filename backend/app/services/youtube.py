import subprocess
import json
import time
import tempfile
import logging
import http.cookiejar
import requests
from pathlib import Path
from typing import Optional
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
from ..config import settings
from .vtt_parser import parse_vtt

log = logging.getLogger(__name__)


def _cookies_file() -> Optional[Path]:
    """Return path to cookies file if a browser is configured, else None."""
    browser = settings.cookies_browser.strip()
    if not browser:
        return None
    return settings.cookies_file_resolved


def _refresh_cookies_if_needed() -> Optional[Path]:
    """Export browser cookies to Netscape file if missing or stale. Returns path or None."""
    cookies_path = _cookies_file()
    if cookies_path is None:
        return None

    max_age_sec = settings.cookies_max_age_hours * 3600
    if cookies_path.exists() and (time.time() - cookies_path.stat().st_mtime) < max_age_sec:
        return cookies_path

    browser = settings.cookies_browser.strip()
    cookies_path.parent.mkdir(parents=True, exist_ok=True)

    # Export cookies by fetching a minimal playlist; --flat-playlist keeps it fast
    cmd = [
        "yt-dlp",
        "--cookies-from-browser", browser,
        "--cookies", str(cookies_path),
        "--flat-playlist",
        "--playlist-end", "1",
        "--skip-download",
        "--quiet",
        "--no-warnings",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        pass  # cookies may still have been written
    return cookies_path if cookies_path.exists() else None


def _make_session() -> Optional[requests.Session]:
    """Build a requests.Session with browser cookies loaded, or None."""
    cookies_path = _refresh_cookies_if_needed()
    if cookies_path is None:
        return None

    cj = http.cookiejar.MozillaCookieJar(str(cookies_path))
    try:
        cj.load(ignore_discard=True, ignore_expires=True)
    except Exception:
        return None

    session = requests.Session()
    session.cookies.update(cj)
    return session


def _yt_dlp_cookies_args() -> list[str]:
    """Return yt-dlp cookie file arguments if a cookies file is ready."""
    cookies_path = _cookies_file()
    if cookies_path and cookies_path.exists():
        return ["--cookies", str(cookies_path)]
    browser = settings.cookies_browser.strip()
    if browser:
        return ["--cookies-from-browser", browser]
    return []


def fetch_channel_videos(url: str) -> tuple[str, list[dict]]:
    """Return (channel_name, list of video metadata dicts) for all videos in channel."""
    _refresh_cookies_if_needed()
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-single-json",
        "--no-warnings",
        *_yt_dlp_cookies_args(),
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr[:500]}")

    data = json.loads(result.stdout)
    channel_name = data.get("channel") or data.get("uploader") or data.get("title") or "Unknown"
    entries = data.get("entries") or []

    flat: list[dict] = []
    for e in entries:
        if not e:
            continue
        if e.get("_type") == "playlist":
            flat.extend(e.get("entries") or [])
        else:
            flat.append(e)

    seen: set[str] = set()
    videos = []
    for e in flat:
        if not e or e.get("_type") == "playlist":
            continue
        yt_id = e.get("id") or e.get("url", "").split("v=")[-1]
        if not yt_id or yt_id in seen:
            continue
        seen.add(yt_id)
        videos.append({
            "youtube_id": yt_id,
            "title": e.get("title") or "Untitled",
            "duration_sec": e.get("duration"),
            "upload_date": e.get("upload_date"),
        })

    return channel_name, videos


PREFERRED_LANGS = ["it", "en", "it-orig", "en-orig"]


def _classify_error(msg: str) -> str:
    """Map a raw error string to one of the known reason codes."""
    m = msg.lower()
    if "429" in m or "too many requests" in m or "blocking requests" in m or "ip" in m and "block" in m:
        return "ip_blocked"
    if "private" in m or "unavailable" in m or "removed" in m:
        return "video_unavailable"
    if "subtitles" in m and ("disabled" in m or "no subtitles" in m):
        return "transcripts_disabled"
    return "unknown"


def _fetch_via_transcript_api(youtube_id: str) -> tuple[Optional[list[dict]], Optional[str]]:
    """Try youtube-transcript-api. Returns (cues, reason). Reason is None on success."""
    session = _make_session()
    api = YouTubeTranscriptApi(http_client=session) if session else YouTubeTranscriptApi()

    try:
        transcript_list = api.list(youtube_id)
    except TranscriptsDisabled:
        return None, "transcripts_disabled"
    except NoTranscriptFound:
        return None, "no_transcript_found"
    except Exception as e:
        log.info("youtube-transcript-api failed for %s: %s", youtube_id, type(e).__name__)
        return None, _classify_error(f"{type(e).__name__}: {e}")

    transcript = None
    last_err: Optional[str] = None
    for generated in (False, True):
        for lang in PREFERRED_LANGS:
            try:
                candidates = [
                    t for t in transcript_list
                    if t.language_code.startswith(lang) and t.is_generated == generated
                ]
                if candidates:
                    transcript = candidates[0].fetch()
                    break
            except Exception as e:
                last_err = str(e)
                continue
        if transcript is not None:
            break

    if transcript is None:
        try:
            for t in transcript_list:
                try:
                    transcript = t.fetch()
                    break
                except Exception as e:
                    last_err = str(e)
                    continue
        except Exception as e:
            return None, _classify_error(str(e))

    if transcript is None:
        return None, _classify_error(last_err or "no_transcript_found")

    cues = []
    for seg in transcript:
        start = float(seg.start)
        duration = float(seg.duration)
        cues.append({
            "start": start,
            "end": start + duration,
            "text": seg.text.strip(),
        })
    return cues, None


def _fetch_via_ytdlp(youtube_id: str) -> tuple[Optional[list[dict]], Optional[str]]:
    """Download VTT via yt-dlp. Returns (cues, reason). Reason is None on success."""
    url = f"https://www.youtube.com/watch?v={youtube_id}"
    cookies_args = _yt_dlp_cookies_args()
    last_stderr = ""

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for lang in PREFERRED_LANGS:
            cmd = [
                "yt-dlp",
                *cookies_args,
                "--write-auto-sub",
                "--write-sub",
                "--sub-lang", lang,
                "--sub-format", "vtt",
                "--skip-download",
                "--ignore-no-formats-error",
                "--no-warnings",
                "-o", str(tmp_path / "%(id)s.%(ext)s"),
                url,
            ]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if proc.stderr:
                    last_stderr = proc.stderr
            except subprocess.TimeoutExpired:
                last_stderr = "yt-dlp timed out"
                continue

            vtt_files = list(tmp_path.glob(f"{youtube_id}*.vtt"))
            if vtt_files:
                cues = parse_vtt(vtt_files[0])
                if cues:
                    return cues, None
                for f in vtt_files:
                    f.unlink(missing_ok=True)

    if last_stderr:
        return None, _classify_error(last_stderr)
    return None, "no_transcript_found"


def fetch_transcript(youtube_id: str) -> tuple[Optional[list[dict]], Optional[str]]:
    """Fetch transcript segments for a video.

    Tries youtube-transcript-api first (fast when it works), then falls back to
    yt-dlp (more robust against IP blocks). Returns (cues, reason): cues is the
    transcript segments on success (reason=None), or None with a reason code
    on failure. Reason codes: transcripts_disabled, no_transcript_found,
    ip_blocked, video_unavailable, unknown.
    """
    cues, reason1 = _fetch_via_transcript_api(youtube_id)
    if cues:
        return cues, None
    cues, reason2 = _fetch_via_ytdlp(youtube_id)
    if cues:
        return cues, None
    # Prefer the more informative reason (the more specific one wins over generic "unknown").
    final_reason = reason1 if reason1 and reason1 != "unknown" else (reason2 or reason1 or "unknown")
    return None, final_reason
