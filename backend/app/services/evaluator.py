import asyncio
import json
import logging
from datetime import datetime, timezone
from anthropic import AsyncAnthropic, RateLimitError, InternalServerError, APITimeoutError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ..database import get_conn
from ..jobs import update_job

log = logging.getLogger(__name__)

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
    retry=retry_if_exception_type((RateLimitError, InternalServerError, APITimeoutError)),
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
    """Run AI evaluation job with proper resource cleanup and error handling."""
    try:
        await asyncio.to_thread(update_job, job_id, status="running")

        # Fetch chunks to evaluate (skip already evaluated ones), off the event loop
        def _load_chunks() -> list:
            with get_conn() as conn:
                if video_ids:
                    return conn.execute(
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
                    return conn.execute(
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

        rows = await asyncio.to_thread(_load_chunks)
        chunks = [dict(r) for r in rows]
        await asyncio.to_thread(update_job, job_id, total=len(chunks))

        if not chunks:
            await asyncio.to_thread(update_job, job_id, status="done")
            return

        # Create client with explicit timeout
        client = AsyncAnthropic(timeout=90.0)
        evaluated = 0

        def _write_result(chunk_id: int, result: dict) -> None:
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
                    (query_id, chunk_id, result["score"], result["reasoning"], result["topic"], _now()),
                )

        def _write_error(chunk_id: int, error_msg: str) -> None:
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
                    (query_id, chunk_id, 0, f"Evaluation error: {error_msg[:80]}", None, _now()),
                )

        async def process_one(chunk: dict) -> None:
            nonlocal evaluated
            try:
                result = await _score_chunk(client, intent, chunk, model)
                await asyncio.to_thread(_write_result, chunk["id"], result)
            except Exception as e:
                log.exception("Error evaluating chunk %s: %s", chunk["id"], e)
                await asyncio.to_thread(_write_error, chunk["id"], str(e))
            finally:
                evaluated += 1
                await asyncio.to_thread(update_job, job_id, completed=evaluated)

        await asyncio.gather(*[process_one(c) for c in chunks])
        await asyncio.to_thread(update_job, job_id, status="done")

    except Exception as e:
        log.exception("Query job %s failed: %s", job_id, e)
        try:
            await asyncio.to_thread(
                update_job,
                job_id,
                status="failed",
                error_json=f"Job failed: {str(e)[:200]}",
            )
        except Exception as update_err:
            log.exception("Failed to update job status for %s: %s", job_id, update_err)

