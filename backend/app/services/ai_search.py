import json
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ..config import settings

SYSTEM_PROMPT = """You analyze a YouTube video transcript and answer the user's question using ONLY information present in the transcript.

The transcript is provided as a list of numbered chunks: each line starts with [<index>] followed by a timestamp range and the chunk text.

Output ONLY valid JSON with this exact shape:
{
  "answer": "<a concise prose answer to the user's question, grounded in the transcript. If the transcript does not address the question, say so plainly.>",
  "significant_chunks": [
    { "index": <int>, "reason": "<one short sentence explaining why this chunk is significant for the answer>" }
  ]
}

Rules:
- Reference chunks only by their integer index from the transcript.
- Pick at most 8 significant chunks, ranked by importance to the answer.
- If no chunks are relevant, return an empty list for "significant_chunks".
- Do not invent information that is not in the transcript."""


def _fmt_time(s: float) -> str:
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _build_user_message(question: str, video_title: str, chunks: list[dict]) -> str:
    lines = [f"Video title: {video_title}", "", "Transcript chunks:"]
    for c in chunks:
        idx = c["index"]
        start = _fmt_time(c["start_sec"])
        end = _fmt_time(c["end_sec"])
        lines.append(f"[{idx}] ({start}–{end}) {c['text']}")
    lines.append("")
    lines.append(f"Question: {question}")
    return "\n".join(lines)


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
)
async def _call_claude(client: AsyncAnthropic, user_msg: str, model: str) -> str:
    response = await client.messages.create(
        model=model,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return response.content[0].text.strip()


async def ai_search(
    question: str,
    video_title: str,
    chunks: list[dict],
    model: str,
) -> dict:
    """Run a single Claude call to answer `question` from the transcript chunks.

    `chunks` is a list of dicts with keys: index, start_sec, end_sec, text.
    Returns: {"answer": str, "chunks": [{index, start_sec, end_sec, text, reason}]}
    """
    if not chunks:
        return {"answer": "This video has no transcript chunks to search.", "chunks": []}

    client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else AsyncAnthropic()
    user_msg = _build_user_message(question, video_title, chunks)
    raw = await _call_claude(client, user_msg, model)
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    parsed = json.loads(raw)

    answer = (parsed.get("answer") or "").strip()
    significant = parsed.get("significant_chunks") or []

    by_index = {c["index"]: c for c in chunks}
    out_chunks = []
    seen = set()
    for item in significant:
        try:
            idx = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        if idx in seen or idx not in by_index:
            continue
        seen.add(idx)
        c = by_index[idx]
        out_chunks.append({
            "index": idx,
            "start_sec": c["start_sec"],
            "end_sec": c["end_sec"],
            "text": c["text"],
            "reason": (item.get("reason") or "").strip(),
        })

    return {"answer": answer, "chunks": out_chunks}
