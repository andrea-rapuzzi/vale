import sqlite3
from pathlib import Path
from contextlib import contextmanager
from .config import settings

DDL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS channels (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url        TEXT NOT NULL UNIQUE,
    name       TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id   INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    youtube_id   TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    duration_sec INTEGER,
    upload_date  TEXT,
    scraped_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_id);
CREATE INDEX IF NOT EXISTS idx_videos_scraped  ON videos(scraped_at);

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id    INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    start_sec   REAL NOT NULL,
    end_sec     REAL NOT NULL,
    text        TEXT NOT NULL,
    UNIQUE(video_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_video ON chunks(video_id);

CREATE TABLE IF NOT EXISTS queries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    intent     TEXT NOT NULL,
    model      TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS results (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id     INTEGER NOT NULL REFERENCES queries(id) ON DELETE CASCADE,
    chunk_id     INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    score        INTEGER NOT NULL CHECK(score BETWEEN 1 AND 10),
    reasoning    TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    UNIQUE(query_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_results_query       ON results(query_id);
CREATE INDEX IF NOT EXISTS idx_results_query_score ON results(query_id, score DESC);

CREATE TABLE IF NOT EXISTS jobs (
    id         TEXT PRIMARY KEY,
    type       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'queued',
    ref_id     INTEGER,
    completed  INTEGER NOT NULL DEFAULT 0,
    total      INTEGER NOT NULL DEFAULT 0,
    error_json TEXT,
    created_at TEXT NOT NULL
);
"""


def _db_path() -> Path:
    p = settings.db_path_resolved
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def init_db() -> None:
    conn = sqlite3.connect(str(_db_path()))
    conn.executescript(DDL)
    conn.commit()
    conn.close()


@contextmanager
def get_conn():
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
