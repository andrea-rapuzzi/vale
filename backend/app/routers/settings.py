import base64
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import require_approved_user
from ..database import get_conn

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class CookiesUploadRequest(BaseModel):
    content: str  # base64-encoded cookies.txt


@router.post("/cookies")
def upload_cookies(
    req: CookiesUploadRequest,
    _user: dict = Depends(require_approved_user),
):
    try:
        decoded = base64.b64decode(req.content).decode()
    except Exception:
        raise HTTPException(400, "Contenuto non è base64 valido")

    if not decoded.strip().startswith("# Netscape HTTP Cookie File"):
        raise HTTPException(400, "File non valido: deve iniziare con '# Netscape HTTP Cookie File'")

    line_count = sum(
        1 for line in decoded.splitlines()
        if line.strip() and not line.startswith("#")
    )
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES ('cookies_content', %s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
            """,
            (req.content, now),
        )

    from ..services.youtube import _invalidate_cookies_cache
    _invalidate_cookies_cache()

    return {"status": "saved", "uploaded_at": now, "line_count": line_count}


@router.get("/cookies")
def get_cookies_status(_user: dict = Depends(require_approved_user)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value, updated_at FROM app_settings WHERE key = 'cookies_content'"
        ).fetchone()

    if row is None:
        return {"exists": False}

    try:
        decoded = base64.b64decode(row["value"]).decode()
        line_count = sum(
            1 for line in decoded.splitlines()
            if line.strip() and not line.startswith("#")
        )
    except Exception:
        line_count = 0

    return {"exists": True, "uploaded_at": row["updated_at"], "line_count": line_count}


@router.delete("/cookies")
def delete_cookies(_user: dict = Depends(require_approved_user)):
    with get_conn() as conn:
        conn.execute("DELETE FROM app_settings WHERE key = 'cookies_content'")

    from ..services.youtube import _invalidate_cookies_cache
    _invalidate_cookies_cache()

    return {"status": "deleted"}
