import json
from datetime import datetime, timezone
from pathlib import Path
from ..database import get_conn
from ..jobs import update_job
from ..config import settings
from .youtube import download_vtt
from .vtt_parser import parse_and_chunk


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
                    "SELECT id, youtube_id, scraped_at FROM videos WHERE id = ?",
                    (vid_id,),
                ).fetchone()

            if row is None:
                errors.append({"video_id": vid_id, "error": "Video not found in DB"})
                completed += 1
                update_job(job_id, completed=completed)
                continue

            youtube_id = row["youtube_id"]

            # Skip if already scraped
            if row["scraped_at"] is not None:
                completed += 1
                update_job(job_id, completed=completed)
                continue

            # Check if VTT already downloaded
            vtt_path = settings.vtt_dir_resolved / f"{youtube_id}.en.vtt"
            if not vtt_path.exists():
                vtt_path = download_vtt(youtube_id)

            if vtt_path is None or not vtt_path.exists():
                errors.append({"video_id": vid_id, "youtube_id": youtube_id, "error": "No subtitles available"})
                completed += 1
                update_job(job_id, completed=completed)
                continue

            chunks = parse_and_chunk(vtt_path, vid_id)

            with get_conn() as conn:
                conn.executemany(
                    "INSERT OR IGNORE INTO chunks (video_id, chunk_index, start_sec, end_sec, text) VALUES (?,?,?,?,?)",
                    [(c["video_id"], c["chunk_index"], c["start_sec"], c["end_sec"], c["text"]) for c in chunks],
                )
                conn.execute(
                    "UPDATE videos SET scraped_at = ? WHERE id = ?",
                    (_now(), vid_id),
                )

        except Exception as e:
            errors.append({"video_id": vid_id, "error": str(e)})

        completed += 1
        update_job(job_id, completed=completed)

    final_status = "done" if not errors else "done"  # done even with partial errors
    update_job(
        job_id,
        status=final_status,
        error_json=json.dumps(errors) if errors else None,
    )
