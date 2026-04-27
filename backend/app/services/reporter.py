from ..database import get_conn


def generate_report(query_id: int) -> str:
    with get_conn() as conn:
        query_row = conn.execute(
            "SELECT intent, model, created_at FROM queries WHERE id = %s", (query_id,)
        ).fetchone()
        if query_row is None:
            return "# Query not found\n"

        results = conn.execute(
            """
            SELECT r.topic, r.reasoning, c.text, c.start_sec, c.end_sec,
                   v.youtube_id, v.title AS video_title
            FROM results r
            JOIN chunks c ON c.id = r.chunk_id
            JOIN videos v ON v.id = c.video_id
            WHERE r.query_id = %s AND r.score > 0
            ORDER BY r.topic NULLS LAST, v.title ASC, c.start_sec ASC
            """,
            (query_id,),
        ).fetchall()

    lines = [
        f"# Search Results",
        f"",
        f"**Intent:** {query_row['intent']}",
        f"**Model:** {query_row['model']}",
        f"**Date:** {query_row['created_at'][:10]}",
        f"**Relevant chunks:** {len(results)}",
        f"",
        "---",
        "",
    ]

    if not results:
        lines.append("_No relevant chunks found for this query._")
        return "\n".join(lines)

    current_topic = object()
    for row in results:
        topic = row["topic"] or "Other"
        if topic != current_topic:
            lines += [f"## {topic}", ""]
            current_topic = topic
        start = int(row["start_sec"])
        url = f"https://www.youtube.com/watch?v={row['youtube_id']}&t={start}"
        lines += [
            f"### {row['video_title']}",
            f"",
            f"**Timestamp:** [{_fmt_time(row['start_sec'])} → {_fmt_time(row['end_sec'])}]({url})",
            f"",
            f"**Why:** {row['reasoning']}",
            f"",
            f"> {row['text'][:400]}{'...' if len(row['text']) > 400 else ''}",
            f"",
            "---",
            "",
        ]

    return "\n".join(lines)


def _fmt_time(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"
