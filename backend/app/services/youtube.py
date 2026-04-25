import subprocess
import json
import time
import http.cookiejar
import requests
from pathlib import Path
from typing import Optional
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
from ..config import settings


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


def fetch_transcript(youtube_id: str) -> Optional[list[dict]]:
    """Fetch transcript segments for a video via youtube-transcript-api.

    Returns list of {start, end, text} dicts, or None if no transcript available.
    Prefers manual subtitles, falls back to auto-generated.
    """
    session = _make_session()
    api = YouTubeTranscriptApi(http_client=session) if session else YouTubeTranscriptApi()

    preferred_langs = ["en", "it", "en-orig", "it-orig"]

    try:
        transcript_list = api.list(youtube_id)
    except (TranscriptsDisabled, NoTranscriptFound):
        return None
    except Exception:
        return None

    # Try manual first, then auto-generated, in preferred language order
    transcript = None
    for generated in (False, True):
        for lang in preferred_langs:
            try:
                candidates = [
                    t for t in transcript_list
                    if t.language_code.startswith(lang) and t.is_generated == generated
                ]
                if candidates:
                    transcript = candidates[0].fetch()
                    break
            except Exception:
                continue
        if transcript is not None:
            break

    # Last resort: any available transcript
    if transcript is None:
        try:
            for t in transcript_list:
                try:
                    transcript = t.fetch()
                    break
                except Exception:
                    continue
        except Exception:
            return None

    if transcript is None:
        return None

    cues = []
    for seg in transcript:
        start = float(seg.start)
        duration = float(seg.duration)
        cues.append({
            "start": start,
            "end": start + duration,
            "text": seg.text.strip(),
        })
    return cues
