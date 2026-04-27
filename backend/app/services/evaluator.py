import asyncio
import json
from datetime import datetime, timezone
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ..database import get_conn
from ..jobs import update_job

SEMAPHORE_LIMIT = 5
_semaphore = asyncio.Semaphore(SEMAPHORE_LIMIT)

SYSTEM_PROMPT = """You are a relevance classifier for YouTube transcript search.
Given a search intent and a transcript chunk, decide whether the chunk
ACTUALLY DISCUSSES the topic the user is searching for.

Output ONLY valid JSON:
{"relevant": true | false, "topic": "<short label, max 5 words>", "reasoning": "<one sentence, max 20 words>"}

Be conservative: mark `true` only if the chunk substantively addresses the
intent. A passing keyword mention or vaguely related context is NOT enough.
The `topic` field should describe the specific sub-theme of the chunk in the
language of the user's intent (used to group results in the UI)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(4),
)
async def _score_chunk(
    client: AsyncAnthropic,
    intent: str,
    chunk: dict,
    model: str,
) -> dict:
    async with _semaphore:
        user_msg = (
            f"Search intent: {intent}\n\n"
            f"Video: {chunk['video_title']}\n"
            f"Timestamp: {chunk['start_sec']:.0f}s – {chunk['end_sec']:.0f}s\n"
            f"Transcript:\n{chunk['text']}"
        )
        response = await client.messages.create(
            model=model,
            max_tokens=160,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
        relevant = bool(parsed.get("relevant"))
        return {
            "score": 10 if relevant else 0,
            "topic": (parsed.get("topic") or "").strip()[:60] or None,
            "reasoning": (parsed.get("reasoning") or "").strip(),
        }


async def run_query_job(
    job_id: str,
    query_id: int,
    intent: str,
    model: str,
    video_ids: list[int] | None,
) -> None:
    update_job(job_id, status="running")

    # Fetch chunks to evaluate (skip already evaluated ones)
    with get_conn() as conn:
        if video_ids:
            rows = conn.execute(
                """
                SELECT c.id, c.start_sec, c.end_sec, c.text, v.youtube_id, v.title AS video_title
                FROM chunks c
                JOIN videos v ON v.id = c.video_id
                WHERE v.id = ANY(%s)
                  AND v.scraped_at IS NOT NULL
                  AND c.id NOT IN (
                      SELECT chunk_id FROM results WHERE query_id = %s
                  )
                """,
                (list(video_ids), query_id),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT c.id, c.start_sec, c.end_sec, c.text, v.youtube_id, v.title AS video_title
                FROM chunks c
                JOIN videos v ON v.id = c.video_id
                WHERE v.scraped_at IS NOT NULL
                  AND c.id NOT IN (
                      SELECT chunk_id FROM results WHERE query_id = %s
                  )
                """,
                (query_id,),
            ).fetchall()

    chunks = [dict(r) for r in rows]
    update_job(job_id, total=len(chunks))

    if not chunks:
        update_job(job_id, status="done")
        return

    client = AsyncAnthropic()
    evaluated = 0

    async def process_one(chunk: dict) -> None:
        nonlocal evaluated
        try:
            result = await _score_chunk(client, intent, chunk, model)
            with get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO results (query_id, chunk_id, score, reasoning, topic, evaluated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (query_id, chunk_id) DO UPDATE SET
                        score = EXCLUDED.score,
                        reasoning = EXCLUDED.reasoning,
                        topic = EXCLUDED.topic,
                        evaluated_at = EXCLUDED.evaluated_at
                    """,
                    (query_id, chunk["id"], result["score"], result["reasoning"], result["topic"], _now()),
                )
        except Exception as e:
            with get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO results (query_id, chunk_id, score, reasoning, topic, evaluated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (query_id, chunk_id) DO UPDATE SET
                        score = EXCLUDED.score,
                        reasoning = EXCLUDED.reasoning,
                        topic = EXCLUDED.topic,
                        evaluated_at = EXCLUDED.evaluated_at
                    """,
                    (query_id, chunk["id"], 0, f"Evaluation error: {str(e)[:80]}", None, _now()),
                )
        evaluated += 1
        update_job(job_id, completed=evaluated)

    await asyncio.gather(*[process_one(c) for c in chunks])
    update_job(job_id, status="done")
