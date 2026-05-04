from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
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

_allowed_origins = [settings.frontend_url, "http://localhost:4321", "http://localhost:4322"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
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


@app.get("/api/auth/debug")
async def auth_debug(request: Request):
    """Diagnose JWT configuration without exposing secrets."""
    import jwt as pyjwt
    from jwt import PyJWKClient, PyJWKClientError
    auth_header = request.headers.get("Authorization", "")
    has_bearer = auth_header.startswith("Bearer ")
    token = auth_header[7:] if has_bearer else ""

    result: dict = {
        "has_bearer": has_bearer,
        "token_length": len(token),
        "supabase_url_configured": bool(settings.supabase_url),
        "jwt_secret_configured": bool(settings.supabase_jwt_secret),
        "jwt_secret_looks_like_jwt": settings.supabase_jwt_secret.startswith("eyJ"),
    }

    if token and settings.supabase_url:
        try:
            client = PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json")
            signing_key = client.get_signing_key_from_jwt(token)
            pyjwt.decode(token, signing_key.key, algorithms=["ES256", "RS256"], audience="authenticated")
            result["jwks_decode"] = "ok"
        except PyJWKClientError as e:
            result["jwks_decode"] = f"key_not_in_jwks: {e}"
        except pyjwt.ExpiredSignatureError:
            result["jwks_decode"] = "expired"
        except pyjwt.InvalidTokenError as e:
            result["jwks_decode"] = f"{type(e).__name__}"
        except Exception as e:
            result["jwks_decode"] = f"error: {e}"

    return result
