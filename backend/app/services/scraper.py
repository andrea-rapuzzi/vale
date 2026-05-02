import asyncio
import json
import logging
from datetime import datetime, timezone
from ..database import get_conn
from ..jobs import update_job
from .youtube import fetch_transcript
from .vtt_parser import chunk_cues

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


REASON_MESSAGES = {
    "transcripts_disabled": "I sottotitoli sono disabilitati per questo video.",
    "no_transcript_found": "Nessun sottotitolo trovato in italiano o inglese.",
    "ip_blocked": "YouTube ha bloccato la richiesta (rate-limit). Riprova tra qualche minuto.",
    "video_unavailable": "Video non disponibile (privato, rimosso o riservato).",
    "unknown": "Errore sconosciuto durante il recupero del transcript.",
    "db_missing": "Video non trovato nel database.",
    "internal": "Errore interno durante l'elaborazione.",
}

RETRYABLE_REASONS = {"ip_blocked", "unknown", "internal"}


def _human_message(reason: str) -> str:
    return REASON_MESSAGES.get(reason, REASON_MESSAGES["unknown"])


async def run_scrape_job(job_id: str, video_ids: list[int]) -> None:
    update_job(job_id, status="running", total=len(video_ids))
    errors = []
    completed = 0
    fatal: Exception | None = None
    _yt_calls = 0  # count actual YouTube fetches to space them out

    for vid_id in video_ids:
        title = None
        youtube_id = None
        try:
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT id, youtube_id, title, scraped_at FROM videos WHERE id = %s",
                    (vid_id,),
                ).fetchone()

            if row is None:
                errors.append({
                    "video_id": vid_id,
                    "youtube_id": None,
                    "title": None,
                    "reason": "db_missing",
                    "message": _human_message("db_missing"),
                    "retryable": False,
                })
                completed += 1
                update_job(job_id, completed=completed)
                continue

            youtube_id = row["youtube_id"]
            title = row["title"]

            if row["scraped_at"] is not None:
                completed += 1
                update_job(job_id, completed=completed)
                continue

            if _yt_calls > 0:
                await asyncio.sleep(1.5)
            _yt_calls += 1
            cues, reason = await asyncio.to_thread(fetch_transcript, youtube_id)

            if cues is None:
                reason = reason or "unknown"
                errors.append({
                    "video_id": vid_id,
                    "youtube_id": youtube_id,
                    "title": title,
                    "reason": reason,
                    "message": _human_message(reason),
                    "retryable": reason in RETRYABLE_REASONS,
                })
                completed += 1
                update_job(job_id, completed=completed)
                continue

            chunks = chunk_cues(cues, vid_id)

            with get_conn() as conn:
                if chunks:
                    with conn.cursor() as cur:
                        cur.executemany(
                            """
                            INSERT INTO chunks (video_id, chunk_index, start_sec, end_sec, text)
                            VALUES (%s,%s,%s,%s,%s)
                            ON CONFLICT (video_id, chunk_index) DO NOTHING
                            """,
                            [(c["video_id"], c["chunk_index"], c["start_sec"], c["end_sec"], c["text"]) for c in chunks],
                        )
                conn.execute(
                    "UPDATE videos SET scraped_at = %s WHERE id = %s",
                    (_now(), vid_id),
                )

        except Exception as e:
            errors.append({
                "video_id": vid_id,
                "youtube_id": youtube_id,
                "title": title,
                "reason": "internal",
                "message": f"{_human_message('internal')} ({str(e)[:120]})",
                "retryable": True,
            })

        completed += 1
        update_job(job_id, completed=completed)

    try:
        update_job(
            job_id,
            status="done",
            error_json=json.dumps(errors) if errors else None,
        )
    except Exception as e:
        fatal = e
        log.exception("scrape job %s: failed to write final 'done' status", job_id)
        try:
            update_job(job_id, status="failed", error_json=str(e)[:500])
        except Exception:
            log.exception("scrape job %s: also failed to write 'failed' status", job_id)
    if fatal:
        raise fatal
