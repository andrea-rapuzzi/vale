import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from .database import get_conn

STALE_RUNNING_AFTER_MINUTES = 10


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(type_: str, total: int = 0, ref_id: Optional[int] = None) -> str:
    job_id = str(uuid.uuid4())
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO jobs (id, type, status, ref_id, completed, total, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (job_id, type_, "queued", ref_id, 0, total, now, now),
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
    fields.append("updated_at = %s")
    params.append(_now())
    params.append(job_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = %s", params)


def _is_stale_running(row: dict) -> bool:
    if row.get("status") != "running":
        return False
    ts = row.get("updated_at") or row.get("created_at")
    if not ts:
        return False
    try:
        last = datetime.fromisoformat(ts)
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last > timedelta(minutes=STALE_RUNNING_AFTER_MINUTES)


def get_job(job_id: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
    if row is None:
        return None
    row = dict(row)
    if _is_stale_running(row):
        update_job(
            job_id,
            status="failed",
            error_json=f"Job timed out after {STALE_RUNNING_AFTER_MINUTES} minutes (worker died or stalled).",
        )
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,)).fetchone()
        row = dict(row) if row else None
    return row
