from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .database import init_db, shutdown_pool
from .routers import channel, scrape, query, video
from .routers.query import queries_router
from .routers.channel import channels_router
from .routers.video import videos_router
from .auth import require_approved_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    shutdown_pool()


app = FastAPI(title="YTS — YouTube Transcript Search", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:4321", "http://localhost:4322"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(channel.router)
app.include_router(channels_router)
app.include_router(scrape.router)
app.include_router(query.router)
app.include_router(queries_router)
app.include_router(video.router)
app.include_router(videos_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/auth/me")
async def auth_me(user: dict = Depends(require_approved_user)):
    return {"user_id": user["user_id"], "email": user["email"]}
