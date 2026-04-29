from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from ..models.api import ScrapeRequest, JobStatusOut
from ..jobs import create_job, get_job
from ..services.scraper import run_scrape_job
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


@router.get("/status/{job_id}", response_model=JobStatusOut)
async def scrape_status(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return JobStatusOut(**job)
