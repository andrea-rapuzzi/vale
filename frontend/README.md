# YTS Frontend

Astro 6 SSR application for YouTube Transcript Search, deployed on Vercel.

## Stack

- **Astro 6** — server-side rendering with Vercel adapter
- **TailwindCSS 4** — utility-first styling
- **TypeScript** — strict mode
- **@supabase/ssr** — auth session management

## Development

```bash
npm install
cp .env.example .env   # fill in the variables
npm run dev            # starts at localhost:4321
```

## Environment variables

| Variable | Description |
|---|---|
| `PUBLIC_SUPABASE_URL` | Supabase project URL |
| `PUBLIC_SUPABASE_ANON_KEY` | Supabase anonymous key |
| `PUBLIC_BACKEND_URL` | Backend URL for client-side fetches |
| `BACKEND_URL` | Backend URL for server-side fetches (middleware) |

## Commands

| Command | Action |
|---|---|
| `npm run dev` | Start dev server at `localhost:4321` |
| `npm run build` | Build for production |
| `npm run preview` | Preview production build locally |

## Deployment

Connect to Vercel with root directory set to `frontend/`. The `@astrojs/vercel` adapter is already configured in `astro.config.mjs`.

See the [root README](../README.md) for full project documentation.
