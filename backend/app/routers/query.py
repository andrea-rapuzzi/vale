from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from ..models.api import QueryRequest, JobStatusOut, ResultOut, QueryOut
from ..database import get_conn
from ..jobs import create_job, get_job
from ..services.evaluator import run_query_job
from ..services.reporter import generate_report
from ..auth import require_approved_user

router = APIRouter(prefix="/api/query", tags=["query"])
queries_router = APIRouter(prefix="/api/queries", tags=["queries"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("")
def start_query(
    req: QueryRequest,
    background_tasks: BackgroundTasks,
    _user: dict = Depends(require_approved_user),
):
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO queries (intent, model, created_at) VALUES (%s, %s, %s) RETURNING id",
            (req.intent, req.model, _now()),
        ).fetchone()
        query_id = row["id"]

    job_id = create_job("query", ref_id=query_id)
    background_tasks.add_task(
        run_query_job, job_id, query_id, req.intent, req.model, req.video_ids
    )
    return {"query_id": query_id, "job_id": job_id, "status": "queued"}


@router.get("/status/{job_id}", response_model=JobStatusOut)
def query_status(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return JobStatusOut(**job)


@router.get("/{query_id}/results")
def get_results(
    query_id: int,
    limit: int = 200,
    offset: int = 0,
    _user: dict = Depends(require_approved_user),
):
    with get_conn() as conn:
        query_row = conn.execute("SELECT * FROM queries WHERE id = %s", (query_id,)).fetchone()
        if query_row is None:
            raise HTTPException(404, "Query not found")

        total = conn.execute(
            "SELECT COUNT(*) AS total FROM results WHERE query_id = %s AND score > 0",
            (query_id,),
        ).fetchone()["total"]

        rows = conn.execute(
            """
            SELECT r.score, r.reasoning, r.topic, c.text AS chunk_text,
                   c.start_sec, c.end_sec, v.youtube_id, v.title AS video_title
            FROM results r
            JOIN chunks c ON c.id = r.chunk_id
            JOIN videos v ON v.id = c.video_id
            WHERE r.query_id = %s AND r.score > 0
            ORDER BY r.topic NULLS LAST, v.title ASC, c.start_sec ASC
            LIMIT %s OFFSET %s
            """,
            (query_id, limit, offset),
        ).fetchall()

    results = [
        ResultOut(
            score=r["score"],
            reasoning=r["reasoning"],
            topic=r["topic"],
            chunk_text=r["chunk_text"],
            start_sec=r["start_sec"],
            end_sec=r["end_sec"],
            youtube_id=r["youtube_id"],
            video_title=r["video_title"],
            youtube_url=f"https://www.youtube.com/watch?v={r['youtube_id']}&t={int(r['start_sec'])}",
        )
        for r in rows
    ]

    return {
        "query_id": query_id,
        "intent": query_row["intent"],
        "model": query_row["model"],
        "created_at": query_row["created_at"],
        "results": [r.model_dump() for r in results],
        "total_results": total,
    }


@router.get("/{query_id}/report", response_class=PlainTextResponse)
def get_report(query_id: int, _user: dict = Depends(require_approved_user)):
    with get_conn() as conn:
        exists = conn.execute("SELECT id FROM queries WHERE id = %s", (query_id,)).fetchone()
    if exists is None:
        raise HTTPException(404, "Query not found")
    return generate_report(query_id)


@queries_router.get("")
def list_queries(limit: int = 20, offset: int = 0):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT q.id, q.intent, q.model, q.created_at,
                   COUNT(r.id) AS result_count
            FROM queries q
            LEFT JOIN results r ON r.query_id = q.id
            GROUP BY q.id
            ORDER BY q.created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        ).fetchall()
    return {
        "queries": [
            QueryOut(
                id=r["id"],
                intent=r["intent"],
                model=r["model"],
                created_at=r["created_at"],
                result_count=r["result_count"],
            ).model_dump()
            for r in rows
        ]
    }
