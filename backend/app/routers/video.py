from fastapi import APIRouter, Depends, HTTPException
from ..database import get_conn
from ..models.api import AISearchRequest
from ..services.ai_search import ai_search
from ..auth import require_approved_user

router = APIRouter(prefix="/api/video", tags=["video"])
videos_router = APIRouter(prefix="/api/videos", tags=["videos"])


@videos_router.get("/scraped")
async def list_scraped_videos(limit: int = 100, offset: int = 0):
    """List videos that have been scraped, most recent first."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT v.id, v.youtube_id, v.title, v.duration_sec, v.upload_date,
                   v.scraped_at, v.channel_id, c.name AS channel_name,
                   COUNT(ch.id) AS chunk_count
            FROM videos v
            JOIN channels c ON c.id = v.channel_id
            LEFT JOIN chunks ch ON ch.video_id = v.id
            WHERE v.scraped_at IS NOT NULL
            GROUP BY v.id, c.name
            ORDER BY v.scraped_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) AS total FROM videos WHERE scraped_at IS NOT NULL"
        ).fetchone()["total"]

    return {
        "videos": [
            {
                "id": r["id"],
                "youtube_id": r["youtube_id"],
                "title": r["title"],
                "duration_sec": r["duration_sec"],
                "upload_date": r["upload_date"],
                "scraped_at": r["scraped_at"],
                "channel_id": r["channel_id"],
                "channel_name": r["channel_name"],
                "chunk_count": r["chunk_count"],
            }
            for r in rows
        ],
        "total": total,
    }


@router.get("/{video_id}/transcript")
async def get_transcript(video_id: int):
    with get_conn() as conn:
        video = conn.execute(
            """
            SELECT v.id, v.youtube_id, v.title, v.duration_sec, v.upload_date,
                   v.scraped_at, v.channel_id, c.name AS channel_name
            FROM videos v
            JOIN channels c ON c.id = v.channel_id
            WHERE v.id = %s
            """,
            (video_id,),
        ).fetchone()

        if video is None:
            raise HTTPException(404, "Video not found")
        if video["scraped_at"] is None:
            raise HTTPException(400, "Video not yet scraped")

        chunks = conn.execute(
            """
            SELECT chunk_index, start_sec, end_sec, text
            FROM chunks
            WHERE video_id = %s
            ORDER BY chunk_index ASC
            """,
            (video_id,),
        ).fetchall()

    return {
        "video_id": video["id"],
        "youtube_id": video["youtube_id"],
        "title": video["title"],
        "duration_sec": video["duration_sec"],
        "upload_date": video["upload_date"],
        "scraped_at": video["scraped_at"],
        "channel_id": video["channel_id"],
        "channel_name": video["channel_name"],
        "chunks": [
            {
                "index": c["chunk_index"],
                "start_sec": c["start_sec"],
                "end_sec": c["end_sec"],
                "text": c["text"],
            }
            for c in chunks
        ],
    }


@router.post("/{video_id}/ai-search")
async def video_ai_search(
    video_id: int,
    body: AISearchRequest,
    _user: dict = Depends(require_approved_user),
):
    with get_conn() as conn:
        video = conn.execute(
            """
            SELECT v.id, v.youtube_id, v.title, v.scraped_at
            FROM videos v
            WHERE v.id = %s
            """,
            (video_id,),
        ).fetchone()

        if video is None:
            raise HTTPException(404, "Video not found")
        if video["scraped_at"] is None:
            raise HTTPException(400, "Video not yet scraped")

        rows = conn.execute(
            """
            SELECT chunk_index, start_sec, end_sec, text
            FROM chunks
            WHERE video_id = %s
            ORDER BY chunk_index ASC
            """,
            (video_id,),
        ).fetchall()

    chunks = [
        {
            "index": r["chunk_index"],
            "start_sec": r["start_sec"],
            "end_sec": r["end_sec"],
            "text": r["text"],
        }
        for r in rows
    ]

    try:
        result = await ai_search(body.question, video["title"], chunks, body.model)
    except Exception as e:
        cause = e
        # Tenacity RetryError wraps the real exception in last_attempt.exception()
        last_attempt = getattr(e, "last_attempt", None)
        if last_attempt is not None:
            try:
                cause = last_attempt.exception() or e
            except Exception:
                cause = e
        msg = f"{type(cause).__name__}: {cause}"
        raise HTTPException(502, f"AI search failed: {msg[:300]}")

    return result
