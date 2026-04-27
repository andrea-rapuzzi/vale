-- YTS — switch results scoring from 1-10 scale to binary relevance + topic.
-- Apply this in Supabase dashboard → SQL Editor → New query (after 0001).

-- Drop the old 1..10 CHECK so the evaluator can store 0 (not relevant) / 10 (relevant).
ALTER TABLE results DROP CONSTRAINT IF EXISTS results_score_check;
ALTER TABLE results ADD CONSTRAINT results_score_check CHECK (score BETWEEN 0 AND 10);

-- Topic label produced by the LLM classifier (nullable for legacy rows).
ALTER TABLE results ADD COLUMN IF NOT EXISTS topic TEXT;
