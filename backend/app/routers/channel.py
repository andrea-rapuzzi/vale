from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException
from ..models.api import ChannelFetchRequest, JobStatusOut, VideoOut
from ..database import get_conn
from ..jobs import create_job, update_job, get_job
from ..services.youtube import fetch_channel_videos

router = APIRouter(prefix="/api/channel", tags=["channel"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _fetch_job(job_id: str, url: str) -> None:
    update_job(job_id, status="running")
    try:
        channel_name, videos = fetch_channel_videos(url)
    except Exception as e:
        update_job(job_id, status="failed", error_json=str(e))
        return

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO channels (url, name, fetched_at) VALUES (?, ?, ?) ON CONFLICT(url) DO UPDATE SET name=excluded.name, fetched_at=excluded.fetched_at",
            (url, channel_name, _now()),
        )
        channel_id = conn.execute("SELECT id FROM channels WHERE url = ?", (url,)).fetchone()["id"]
        conn.executemany(
            """
            INSERT INTO videos (channel_id, youtube_id, title, duration_sec, upload_date)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(youtube_id) DO NOTHING
            """,
            [(channel_id, v["youtube_id"], v["title"], v["duration_sec"], v["upload_date"]) for v in videos],
        )

    update_job(job_id, status="done", ref_id=channel_id, total=len(videos), completed=len(videos))


@router.post("/fetch")
async def fetch_channel(req: ChannelFetchRequest, background_tasks: BackgroundTasks):
    job_id = create_job("channel_fetch")
    background_tasks.add_task(_fetch_job, job_id, req.url)
    return {"job_id": job_id, "status": "queued"}


@router.get("/fetch/status/{job_id}", response_model=JobStatusOut)
async def fetch_status(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return JobStatusOut(**job)


@router.get("/{channel_id}/videos")
async def list_videos(
    channel_id: int,
    limit: int = 50,
    offset: int = 0,
    scraped: str = "all",
):
    with get_conn() as conn:
        channel = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
        if channel is None:
            raise HTTPException(404, "Channel not found")

        base = "FROM videos WHERE channel_id = ?"
        params: list = [channel_id]

        if scraped == "true":
            base += " AND scraped_at IS NOT NULL"
        elif scraped == "false":
            base += " AND scraped_at IS NULL"

        total = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
        scraped_count = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE channel_id = ? AND scraped_at IS NOT NULL",
            (channel_id,),
        ).fetchone()[0]

        rows = conn.execute(
            f"SELECT * {base} ORDER BY upload_date DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    videos = [
        VideoOut(
            id=r["id"],
            youtube_id=r["youtube_id"],
            title=r["title"],
            duration_sec=r["duration_sec"],
            upload_date=r["upload_date"],
            scraped=r["scraped_at"] is not None,
        )
        for r in rows
    ]

    return {
        "channel_id": channel_id,
        "channel_name": channel["name"],
        "videos": [v.model_dump() for v in videos],
        "total": total,
        "scraped_count": scraped_count,
        "limit": limit,
        "offset": offset,
    }
