-- Add user ownership and anonymous session tracking to channels and queries
ALTER TABLE channels ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE channels ADD COLUMN IF NOT EXISTS session_token TEXT;

ALTER TABLE queries ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE queries ADD COLUMN IF NOT EXISTS session_token TEXT;

-- Store AI search history for user library
CREATE TABLE IF NOT EXISTS ai_searches (
    id            BIGSERIAL PRIMARY KEY,
    video_id      BIGINT REFERENCES videos(id) ON DELETE CASCADE,
    question      TEXT NOT NULL,
    answer        TEXT,
    user_id       UUID,
    session_token TEXT,
    created_at    TEXT NOT NULL
);

-- Indexes for ownership lookups
CREATE INDEX IF NOT EXISTS idx_channels_user       ON channels(user_id);
CREATE INDEX IF NOT EXISTS idx_channels_session    ON channels(session_token);
CREATE INDEX IF NOT EXISTS idx_ai_searches_user    ON ai_searches(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_searches_session ON ai_searches(session_token);
CREATE INDEX IF NOT EXISTS idx_queries_user        ON queries(user_id);
CREATE INDEX IF NOT EXISTS idx_queries_session     ON queries(session_token);
