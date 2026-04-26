import asyncio
import json
from datetime import datetime, timezone
from ..database import get_conn
from ..jobs import update_job
from .youtube import fetch_transcript
from .vtt_parser import chunk_cues


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_scrape_job(job_id: str, video_ids: list[int]) -> None:
    update_job(job_id, status="running", total=len(video_ids))
    errors = []
    completed = 0

    for vid_id in video_ids:
        try:
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT id, youtube_id, scraped_at FROM videos WHERE id = %s",
                    (vid_id,),
                ).fetchone()

            if row is None:
                errors.append({"video_id": vid_id, "error": "Video not found in DB"})
                completed += 1
                update_job(job_id, completed=completed)
                continue

            youtube_id = row["youtube_id"]

            if row["scraped_at"] is not None:
                completed += 1
                update_job(job_id, completed=completed)
                continue

            cues = await asyncio.to_thread(fetch_transcript, youtube_id)

            if cues is None:
                errors.append({"video_id": vid_id, "youtube_id": youtube_id, "error": "No transcript available"})
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
            errors.append({"video_id": vid_id, "error": str(e)})

        completed += 1
        update_job(job_id, completed=completed)

    update_job(
        job_id,
        status="done",
        error_json=json.dumps(errors) if errors else None,
    )
