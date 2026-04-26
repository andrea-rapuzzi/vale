from ..database import get_conn


def generate_report(query_id: int, min_score: int = 1) -> str:
    with get_conn() as conn:
        query_row = conn.execute(
            "SELECT intent, model, created_at FROM queries WHERE id = %s", (query_id,)
        ).fetchone()
        if query_row is None:
            return "# Query not found\n"

        results = conn.execute(
            """
            SELECT r.score, r.reasoning, c.text, c.start_sec, c.end_sec,
                   v.youtube_id, v.title AS video_title
            FROM results r
            JOIN chunks c ON c.id = r.chunk_id
            JOIN videos v ON v.id = c.video_id
            WHERE r.query_id = %s AND r.score >= %s
            ORDER BY r.score DESC, c.start_sec ASC
            """,
            (query_id, min_score),
        ).fetchall()

    lines = [
        f"# Search Results",
        f"",
        f"**Intent:** {query_row['intent']}",
        f"**Model:** {query_row['model']}",
        f"**Date:** {query_row['created_at'][:10]}",
        f"**Matches:** {len(results)} (score ≥ {min_score})",
        f"",
        "---",
        "",
    ]

    if not results:
        lines.append("_No results found for this query._")
        return "\n".join(lines)

    for row in results:
        start = int(row["start_sec"])
        url = f"https://www.youtube.com/watch?v={row['youtube_id']}&t={start}"
        lines += [
            f"## Score {row['score']}/10 — {row['video_title']}",
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
