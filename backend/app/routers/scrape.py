import asyncio
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from ..models.api import ScrapeRequest, VideoUrlRequest, JobStatusOut
from ..jobs import create_job, get_job
from ..services.scraper import run_scrape_job
from ..services.youtube import fetch_video_info
from ..database import get_conn
from ..auth import require_approved_user

router = APIRouter(prefix="/api/scrape", tags=["scrape"])


@router.post("")
async def start_scrape(
    req: ScrapeRequest,
    background_tasks: BackgroundTasks,
    _user: dict = Depends(require_approved_user),
):
    job_id = create_job("scrape", total=len(req.video_ids))
    background_tasks.add_task(run_scrape_job, job_id, req.video_ids)
    return {"job_id": job_id, "status": "queued", "total": len(req.video_ids)}


@router.post("/from-url")
async def scrape_from_url(
    req: VideoUrlRequest,
    background_tasks: BackgroundTasks,
    _user: dict = Depends(require_approved_user),
):
    try:
        info = await asyncio.to_thread(fetch_video_info, req.url)
    except RuntimeError as e:
        raise HTTPException(400, str(e))

    with get_conn() as conn:
        channel_row = conn.execute(
            "SELECT id FROM channels WHERE url = '__standalone__'"
        ).fetchone()
        if channel_row is None:
            raise HTTPException(500, "Standalone channel not initialized")
        channel_id = channel_row["id"]

        video_row = conn.execute(
            """
            INSERT INTO videos (channel_id, youtube_id, title, duration_sec, upload_date)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (youtube_id) DO UPDATE SET title = EXCLUDED.title
            RETURNING id, scraped_at
            """,
            (channel_id, info["youtube_id"], info["title"], info["duration_sec"], info["upload_date"]),
        ).fetchone()
        video_id = video_row["id"]
        already_scraped = video_row["scraped_at"] is not None

    job_id = create_job("scrape", total=1)
    background_tasks.add_task(run_scrape_job, job_id, [video_id])
    return {
        "job_id": job_id,
        "video_id": video_id,
        "already_scraped": already_scraped,
        "status": "queued",
    }


@router.get("/status/{job_id}", response_model=JobStatusOut)
async def scrape_status(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return JobStatusOut(**job)
