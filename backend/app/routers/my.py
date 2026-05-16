from fastapi import APIRouter, Depends, HTTPException, Request
from ..database import get_conn
from ..auth import require_approved_user

router = APIRouter(prefix="/api/my", tags=["my"])


@router.get("/channels")
def my_channels(user: dict = Depends(require_approved_user)):
    """Return channels that belong to the current user."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.url, c.name, c.fetched_at,
                   COUNT(v.id) AS video_count,
                   COUNT(v.scraped_at) AS scraped_count
            FROM channels c
            LEFT JOIN videos v ON v.channel_id = c.id
            WHERE c.user_id = %s
            GROUP BY c.id
            ORDER BY c.fetched_at DESC
            """,
            (user["user_id"],),
        ).fetchall()
    return {
        "channels": [
            {
                "id": r["id"],
                "url": r["url"],
                "name": r["name"],
                "fetched_at": r["fetched_at"],
                "video_count": r["video_count"],
                "scraped_count": r["scraped_count"],
            }
            for r in rows
        ]
    }


@router.get("/searches")
def my_searches(user: dict = Depends(require_approved_user)):
    """Return AI searches made by the current user."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.question, s.answer, s.created_at,
                   v.id AS video_id, v.title AS video_title, v.youtube_id,
                   c.name AS channel_name
            FROM ai_searches s
            JOIN videos v ON v.id = s.video_id
            JOIN channels c ON c.id = v.channel_id
            WHERE s.user_id = %s
            ORDER BY s.created_at DESC
            LIMIT 100
            """,
            (user["user_id"],),
        ).fetchall()
    return {
        "searches": [
            {
                "id": r["id"],
                "question": r["question"],
                "answer": r["answer"],
                "created_at": r["created_at"],
                "video_id": r["video_id"],
                "video_title": r["video_title"],
                "youtube_id": r["youtube_id"],
                "channel_name": r["channel_name"],
            }
            for r in rows
        ]
    }


@router.post("/session/claim")
async def claim_session(request: Request, user: dict = Depends(require_approved_user)):
    """Claim anonymous session records (channels + searches) to the authenticated user."""
    body = await request.json()
    session_token = body.get("session_token")
    if not session_token:
        raise HTTPException(400, "session_token required")

    user_id = user["user_id"]
    with get_conn() as conn:
        conn.execute(
            "UPDATE channels SET user_id = %s WHERE session_token = %s AND user_id IS NULL",
            (user_id, session_token),
        )
        conn.execute(
            "UPDATE ai_searches SET user_id = %s WHERE session_token = %s AND user_id IS NULL",
            (user_id, session_token),
        )
        conn.execute(
            "UPDATE queries SET user_id = %s WHERE session_token = %s AND user_id IS NULL",
            (user_id, session_token),
        )
    return {"claimed": True}
