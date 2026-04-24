from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import PlainTextResponse
from ..models.api import QueryRequest, JobStatusOut, ResultOut, QueryOut
from ..database import get_conn
from ..jobs import create_job, get_job
from ..services.evaluator import run_query_job
from ..services.reporter import generate_report

router = APIRouter(prefix="/api/query", tags=["query"])
queries_router = APIRouter(prefix="/api/queries", tags=["queries"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("")
async def start_query(req: QueryRequest, background_tasks: BackgroundTasks):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO queries (intent, model, created_at) VALUES (?, ?, ?)",
            (req.intent, req.model, _now()),
        )
        query_id = cur.lastrowid

    job_id = create_job("query", ref_id=query_id)
    background_tasks.add_task(
        run_query_job, job_id, query_id, req.intent, req.model, req.video_ids
    )
    return {"query_id": query_id, "job_id": job_id, "status": "queued"}


@router.get("/status/{job_id}", response_model=JobStatusOut)
async def query_status(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return JobStatusOut(**job)


@router.get("/{query_id}/results")
async def get_results(query_id: int, min_score: int = 1, limit: int = 100, offset: int = 0):
    with get_conn() as conn:
        query_row = conn.execute("SELECT * FROM queries WHERE id = ?", (query_id,)).fetchone()
        if query_row is None:
            raise HTTPException(404, "Query not found")

        total = conn.execute(
            "SELECT COUNT(*) FROM results WHERE query_id = ? AND score >= ?",
            (query_id, min_score),
        ).fetchone()[0]

        rows = conn.execute(
            """
            SELECT r.score, r.reasoning, c.text AS chunk_text,
                   c.start_sec, c.end_sec, v.youtube_id, v.title AS video_title
            FROM results r
            JOIN chunks c ON c.id = r.chunk_id
            JOIN videos v ON v.id = c.video_id
            WHERE r.query_id = ? AND r.score >= ?
            ORDER BY r.score DESC, c.start_sec ASC
            LIMIT ? OFFSET ?
            """,
            (query_id, min_score, limit, offset),
        ).fetchall()

    results = [
        ResultOut(
            score=r["score"],
            reasoning=r["reasoning"],
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
async def get_report(query_id: int, min_score: int = 1):
    with get_conn() as conn:
        exists = conn.execute("SELECT id FROM queries WHERE id = ?", (query_id,)).fetchone()
    if exists is None:
        raise HTTPException(404, "Query not found")
    return generate_report(query_id, min_score)


@queries_router.get("")
async def list_queries(limit: int = 20, offset: int = 0):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT q.id, q.intent, q.model, q.created_at,
                   COUNT(r.id) AS result_count
            FROM queries q
            LEFT JOIN results r ON r.query_id = q.id
            GROUP BY q.id
            ORDER BY q.created_at DESC
            LIMIT ? OFFSET ?
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
