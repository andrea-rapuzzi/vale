# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**VALE** (previously named YTS) is a YouTube transcript search tool. Users add YouTube channels, scrape video transcripts, and run AI-powered semantic searches across the transcript corpus. Two Claude-based flows exist:

1. **Query search** (`/query`): evaluates every transcript chunk against a search intent, classifying each as relevant or not (binary 10/0 score).
2. **AI search** (`/video/[id]`): answers a specific question about a single video's transcript, returning an answer and the most relevant chunks.

## Architecture

The project is a monorepo with three distinct layers:

- `backend/` — FastAPI (Python 3.11) REST API, deployed to Railway via Docker
- `frontend/` — Astro 6 SSR app with Tailwind CSS v4, deployed to Vercel
- `supabase/migrations/` — SQL migrations applied manually via Supabase dashboard

**Database**: Supabase Postgres, accessed directly with `psycopg` + connection pool (`psycopg_pool`). The pool is configured with `prepare_threshold=None` because Supabase uses PgBouncer in transaction mode (port 6543). All queries return `dict_row`.

**Auth**: Supabase Auth issues JWTs. The backend verifies them via JWKS (ES256/RS256) with HS256 fallback. Every protected route uses the `require_approved_user` FastAPI dependency, which also checks `user_profiles.status = 'approved'` — new users land in `pending` state and must be manually approved (`UPDATE user_profiles SET status = 'approved'...`).

**Background jobs**: long-running tasks (scraping transcripts, running queries) are enqueued as FastAPI `BackgroundTasks` and tracked in the `jobs` table. The frontend polls `/api/query/status/{job_id}` or `/api/channel/scrape/status/{job_id}` until done. Jobs stuck in `running` for >10 minutes are auto-failed by `get_job()`.

## Data flow

```
Channel URL → yt-dlp (fetch video list) → videos table
                                            ↓
                           fetch_transcript (youtube-transcript-api → yt-dlp VTT fallback)
                                            ↓
                           chunk_cues (45s windows, 10s overlap) → chunks table
                                            ↓
                           run_query_job → Claude evaluates each chunk → results table
                           run_ai_search  → Claude answers from all chunks of one video
```

Transcript fetching tries `youtube-transcript-api` first, falls back to `yt-dlp --write-auto-sub`. Cookie export from a local browser (`COOKIES_BROWSER=chrome`) and an HTTP proxy (`YT_PROXY`) help bypass YouTube rate-limits.

## Dev Commands

**Run everything (from repo root):**
```bash
npm run dev
# Starts backend on :8000 and frontend on :4321 concurrently
```

**Backend only:**
```bash
cd backend && uvicorn app.main:app --reload --port 8000
```

**Frontend only:**
```bash
cd frontend && npm run dev -- --port 4321
```

**Build frontend:**
```bash
cd frontend && npm run build
```

**Install frontend deps:**
```bash
npm run install:frontend   # or: cd frontend && npm install
```

**Backend uses a `.venv` at repo root:**
```bash
source .venv/bin/activate
pip install -r backend/requirements.txt
```

## Environment Variables

**`backend/.env`** (see `backend/.env.example`):
| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API access |
| `DATABASE_URL` | Postgres connection string (use Supabase pooler port 6543) |
| `SUPABASE_URL` | `https://xxx.supabase.co` — enables JWKS JWT verification |
| `SUPABASE_JWT_SECRET` | Fallback HS256 secret if SUPABASE_URL not set |
| `FRONTEND_URL` | Added to CORS allowed origins |
| `DAILY_AI_CALL_LIMIT` | Per-user AI call cap per day (0 = unlimited) |
| `COOKIES_BROWSER` | Browser for cookie export (chrome, firefox, etc.) |
| `YT_PROXY` | HTTP proxy for YouTube requests |

**`frontend/.env`** (see `frontend/.env.example`):
| Variable | Purpose |
|---|---|
| `BACKEND_URL` | Server-side fetch target (middleware approval check) |
| `PUBLIC_BACKEND_URL` | Client-side API calls from browser |
| `PUBLIC_SUPABASE_URL` | Supabase project URL |
| `PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key |

## Key Backend Modules

- `app/auth.py` — JWT decode (JWKS primary, HS256 fallback), `require_approved_user` dependency, `check_daily_ai_limit`, `log_usage`
- `app/database.py` — connection pool init/shutdown, DDL auto-applied on startup, `get_conn()` context manager
- `app/jobs.py` — `create_job`, `update_job`, `get_job` (with stale-running detection)
- `app/config.py` — all settings via pydantic-settings, reads from `.env`
- `app/services/youtube.py` — `fetch_channel_videos` (yt-dlp), `fetch_transcript` (transcript-api → yt-dlp fallback)
- `app/services/vtt_parser.py` — VTT parsing, deduplication, chunking (45s/10s overlap)
- `app/services/evaluator.py` — parallel Claude evaluation of chunks (semaphore of 5), binary relevant/not scoring
- `app/services/ai_search.py` — single Claude call to answer a question from a video's chunks
- `app/services/reporter.py` — Markdown report generation from query results

## Frontend Structure

All pages are Astro SSR (no static generation). Auth token is injected by `Base.astro` as `window.__authToken` and refreshed via `window.__getAuthToken()` (calls Supabase client-side). API calls from client-side scripts use `window.__getAuthToken()` for the Bearer token.

`src/middleware.ts` — runs on every request, redirects unauthenticated users to `/login`, checks backend approval status, exposes `Astro.locals.accessToken` and `Astro.locals.userEmail`.

## Database Migrations

Migrations are applied manually via Supabase dashboard SQL editor (not via CLI). Files in `supabase/migrations/` are numbered and ordered; apply them in sequence. The backend also runs DDL on startup (`init_db()`) for the core tables — this is idempotent via `CREATE TABLE IF NOT EXISTS`.

To approve a new user:
```sql
UPDATE user_profiles SET status = 'approved', approved_at = now()::text WHERE email = 'user@example.com';
```

## Deployment

- **Backend**: Railway, using `backend/Dockerfile`. Port is `$PORT` (injected by Railway).
- **Frontend**: Vercel, using `@astrojs/vercel` adapter. Node 22.x required.
