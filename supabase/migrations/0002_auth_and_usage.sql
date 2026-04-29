-- User profiles with approval status.
-- Run this in Supabase dashboard → SQL Editor → New query.
--
-- To approve a user: UPDATE user_profiles SET status = 'approved', approved_at = now()::text WHERE email = 'user@example.com';

CREATE TABLE IF NOT EXISTS user_profiles (
    id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'blocked')),
    created_at  TEXT NOT NULL,
    approved_at TEXT
);

-- Claude API usage log per user
CREATE TABLE IF NOT EXISTS usage_logs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,  -- ai_search | query_eval | channel_fetch | scrape
    model       TEXT,
    tokens_in   INTEGER,
    tokens_out  INTEGER,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_user_date ON usage_logs(user_id, created_at DESC);
