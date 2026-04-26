import uuid
from datetime import datetime, timezone
from typing import Optional
from .database import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(type_: str, total: int = 0, ref_id: Optional[int] = None) -> str:
    job_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO jobs (id, type, status, ref_id, completed, total, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (job_id, type_, "queued", ref_id, 0, total, _now()),
        )
    return job_id


def update_job(
    job_id: str,
    *,
    status: Optional[str] = None,
    completed: Optional[int] = None,
    total: Optional[int] = None,
    ref_id: Optional[int] = None,
    error_json: Optional[str] = None,
) -> None:
    fields = []
    params = []
    if status is not None:
        fields.append("status = %s")
        params.append(status)
    if completed is not None:
        fields.append("completed = %s")
        params.append(completed)
    if total is not None:
        fields.append("total = %s")
        params.append(total)
    if ref_id is not None:
        fields.append("ref_id = %s")
        params.append(ref_id)
    if error_json is not None:
        fields.append("error_json = %s")
        params.append(error_json)
    if not fields:
        return
    params.append(job_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = %s", params)


def get_job(job_id: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    if row is None:
        return None
    return dict(row)
