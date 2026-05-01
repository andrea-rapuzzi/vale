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


@app.get("/api/auth/debug")
async def auth_debug(request: Request):
    """Diagnose JWT configuration without exposing secrets."""
    from .config import settings
    import jwt as pyjwt
    auth_header = request.headers.get("Authorization", "")
    has_bearer = auth_header.startswith("Bearer ")
    token = auth_header[7:] if has_bearer else ""
    secret_len = len(settings.supabase_jwt_secret)
    secret_looks_like_jwt = settings.supabase_jwt_secret.startswith("eyJ")

    result: dict = {
        "has_bearer": has_bearer,
        "token_length": len(token),
        "secret_configured": secret_len > 0,
        "secret_length": secret_len,
        "secret_looks_like_jwt_key_error": secret_looks_like_jwt,
    }

    if token and secret_len > 0:
        try:
            pyjwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
            result["decode_result"] = "ok"
        except pyjwt.ExpiredSignatureError:
            result["decode_result"] = "expired"
        except pyjwt.InvalidAudienceError:
            result["decode_result"] = "wrong_audience"
        except pyjwt.InvalidSignatureError:
            result["decode_result"] = "wrong_secret"
        except pyjwt.DecodeError as e:
            result["decode_result"] = f"malformed_token: {e}"
        except pyjwt.InvalidTokenError as e:
            result["decode_result"] = f"invalid: {type(e).__name__}"

    return result
