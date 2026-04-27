-- YTS — initial schema for Supabase Postgres.
-- Apply this in Supabase dashboard → SQL Editor → New query.

CREATE TABLE IF NOT EXISTS channels (
    id         BIGSERIAL PRIMARY KEY,
    url        TEXT NOT NULL UNIQUE,
    name       TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id           BIGSERIAL PRIMARY KEY,
    channel_id   BIGINT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    youtube_id   TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    duration_sec INTEGER,
    upload_date  TEXT,
    scraped_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_id);
CREATE INDEX IF NOT EXISTS idx_videos_scraped ON videos(scraped_at);

CREATE TABLE IF NOT EXISTS chunks (
    id          BIGSERIAL PRIMARY KEY,
    video_id    BIGINT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    start_sec   DOUBLE PRECISION NOT NULL,
    end_sec     DOUBLE PRECISION NOT NULL,
    text        TEXT NOT NULL,
    UNIQUE(video_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_video ON chunks(video_id);

CREATE TABLE IF NOT EXISTS queries (
    id         BIGSERIAL PRIMARY KEY,
    intent     TEXT NOT NULL,
    model      TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS results (
    id           BIGSERIAL PRIMARY KEY,
    query_id     BIGINT NOT NULL REFERENCES queries(id) ON DELETE CASCADE,
    chunk_id     BIGINT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
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
    ref_id     BIGINT,
    completed  INTEGER NOT NULL DEFAULT 0,
    total      INTEGER NOT NULL DEFAULT 0,
    error_json TEXT,
    created_at TEXT NOT NULL
);
