# VALE — the Video Analysis & Listening Engine

Side project that aims to provide users a tool that helps them scraping YouTube channel transcripts and run AI-powered semantic searches across them using Claude.

## Features

- **Channel management** — add and track YouTube channels
- **Transcript scraping** — download and index video transcripts via `yt-dlp`
- **AI semantic search** — query transcripts with natural language; Claude finds and ranks the most relevant chunks
- **Query history** — browse past searches and their results
- **User approval workflow** — invite-only access with a `pending → approved` flow

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | [Astro](https://astro.build) 6 (SSR) · TailwindCSS 4 · TypeScript · Node 22 |
| Backend | [FastAPI](https://fastapi.tiangolo.com) · Uvicorn · Python 3.11 |
| Database | [Supabase](https://supabase.com) PostgreSQL (connection pooler :6543) |
| Auth | Supabase Auth · JWT (JWKS ES256 / HS256 fallback) |
| AI | [Anthropic Claude API](https://anthropic.com) (`ai_search`, `evaluator`) |
| YouTube | `yt-dlp` · `youtube-transcript-api` |
| Deployment | Vercel (frontend) · Railway Docker (backend) |

## Architecture

```
Browser
  │
  │  HTTPS
  ▼
Vercel (Astro SSR)          ←── Supabase Auth (login / register)
  │  middleware.ts               JWT token issued to browser
  │  Bearer JWT
  │  fetch /api/*
  ▼
Railway (FastAPI)
  ├── auth.py          JWT verify via JWKS → Supabase
  ├── routers/         /api/channels  /api/videos  /api/scrape  /api/query
  └── services/
        ├── ai_search / evaluator  ──► Anthropic Claude API
        ├── scraper / vtt_parser   ──► YouTube (yt-dlp)
        └── database               ──► Supabase PostgreSQL
                                         channels · videos · chunks
                                         queries · results · jobs
                                         user_profiles · usage_logs
```

A full interactive diagram is available at [`infrastructure-diagram.html`](infrastructure-diagram.html) — open it in any browser.

## Project structure

```
.
├── backend/                 # FastAPI application
│   ├── app/
│   │   ├── main.py
│   │   ├── auth.py          # JWT verification (JWKS + HS256 fallback)
│   │   ├── database.py      # psycopg connection pool
│   │   ├── routers/         # channel, video, scrape, query
│   │   └── services/        # ai_search, scraper, evaluator, youtube, reporter
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                # Astro SSR application
│   ├── src/
│   │   ├── pages/           # index, login, register, library, channels, query…
│   │   ├── components/
│   │   ├── layouts/
│   │   └── middleware.ts    # auth guard
│   └── astro.config.mjs    # Vercel adapter, SSR output
├── supabase/
│   └── migrations/          # SQL migration files
└── infrastructure-diagram.html
```

## Local development

### Prerequisites

- Node.js 22+
- Python 3.11+
- A [Supabase](https://supabase.com) project with the migrations applied

### Setup

```bash
# 1. Install all dependencies
npm install              # root scripts (concurrently)
cd frontend && npm install

# 2. Create environment files
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# 3. Fill in the variables (see below), then start both services
npm run dev
```

This starts the backend on `localhost:8000` and the frontend on `localhost:4321`.

### Environment variables

**`backend/.env`**

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `DATABASE_URL` | Supabase PostgreSQL pooler URL |
| `SUPABASE_URL` | Supabase project URL (for JWKS endpoint) |
| `SUPABASE_JWT_SECRET` | JWT secret (HS256 fallback) |
| `FRONTEND_URL` | Frontend origin for CORS (e.g. `http://localhost:4321`) |
| `DAILY_AI_CALL_LIMIT` | Max Claude calls per user per day (`0` = unlimited) |
| `COOKIES_BROWSER` | Browser for yt-dlp cookie extraction (e.g. `chrome`) |

**`frontend/.env`**

| Variable | Description |
|---|---|
| `PUBLIC_SUPABASE_URL` | Supabase project URL |
| `PUBLIC_SUPABASE_ANON_KEY` | Supabase anonymous key |
| `PUBLIC_BACKEND_URL` | Backend URL for client-side fetches |
| `BACKEND_URL` | Backend URL for server-side fetches (Astro middleware) |

### Database migrations

Run the SQL files in `supabase/migrations/` in order from the Supabase dashboard or via the Supabase CLI:

```bash
supabase db push
```

## Deployment

### Backend → Railway

Push to the connected branch. Railway builds the `backend/Dockerfile` and starts:

```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Set all backend environment variables in the Railway service dashboard.

### Frontend → Vercel

Connect the repo to Vercel and set the root directory to `frontend/`. Set the frontend environment variables in the Vercel project settings.

The Astro config already includes the Vercel adapter (`@astrojs/vercel`).
