from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .database import init_db
from .routers import channel, scrape, query, video
from .routers.query import queries_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="YTS — YouTube Transcript Search", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:4321"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(channel.router)
app.include_router(scrape.router)
app.include_router(query.router)
app.include_router(queries_router)
app.include_router(video.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
