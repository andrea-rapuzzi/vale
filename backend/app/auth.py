import jwt
import logging
from functools import lru_cache
from datetime import datetime, timezone
from fastapi import HTTPException, Request
from jwt import PyJWKClient, PyJWKClientError
from .config import settings
from .database import get_conn

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _jwks_client(supabase_url: str) -> PyJWKClient:
    return PyJWKClient(
        f"{supabase_url}/auth/v1/.well-known/jwks.json",
        cache_jwk_set=True,
        lifespan=3600,
    )


def _decode_jwt(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing auth token")
    token = auth_header[7:]

    # Primary path: asymmetric verification via Supabase JWKS (ES256 / RS256)
    # Required when Supabase uses ECC P-256 or RSA signing keys.
    if settings.supabase_url:
        client = _jwks_client(settings.supabase_url)
        try:
            signing_key = client.get_signing_key_from_jwt(token)
            try:
                return jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["ES256", "RS256"],
                    audience="authenticated",
                )
            except jwt.ExpiredSignatureError:
                raise HTTPException(status_code=401, detail="Token expired")
            except jwt.InvalidTokenError as e:
                logger.warning("Asymmetric JWT decode failed (%s): %s", type(e).__name__, e)
                raise HTTPException(status_code=401, detail="Invalid token")
        except PyJWKClientError:
            # Token's kid not in JWKS — fall through to HS256 for legacy tokens
            pass
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("JWKS fetch error: %s", e)
            # Fall through to HS256 if JWKS endpoint is unreachable

    # Fallback: symmetric HS256 (legacy Supabase shared secret)
    if not settings.supabase_jwt_secret:
        raise HTTPException(status_code=500, detail="Auth not configured on server")
    try:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning("HS256 JWT decode failed (%s): %s", type(e).__name__, e)
        raise HTTPException(status_code=401, detail="Invalid token")


def require_approved_user(request: Request) -> dict:
    """FastAPI dependency: verifies Supabase JWT and checks that the user is approved."""
    payload = _decode_jwt(request)
    user_id: str = payload.get("sub", "")
    email: str = payload.get("email", "")

    with get_conn() as conn:
        row = conn.execute(
            "SELECT status FROM user_profiles WHERE id = %s", (user_id,)
        ).fetchone()

    if row is None:
        _now = datetime.now(timezone.utc).isoformat()
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO user_profiles (id, email, status, created_at)
                VALUES (%s, %s, 'pending', %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (user_id, email, _now),
            )
        raise HTTPException(status_code=403, detail="Account awaiting approval")

    if row["status"] != "approved":
        raise HTTPException(status_code=403, detail="Account awaiting approval")

    return {"user_id": user_id, "email": email}


def optional_user(request: Request) -> dict | None:
    """Returns approved user dict if a valid Bearer token is present, None otherwise."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    try:
        payload = _decode_jwt(request)
        user_id: str = payload.get("sub", "")
        email: str = payload.get("email", "")
        with get_conn() as conn:
            row = conn.execute(
                "SELECT status FROM user_profiles WHERE id = %s", (user_id,)
            ).fetchone()
        if row is None or row["status"] != "approved":
            return None
        return {"user_id": user_id, "email": email}
    except HTTPException:
        return None


def check_daily_ai_limit(user_id: str) -> None:
    """Raise 429 if the user has exceeded the daily AI call limit (0 = unlimited)."""
    if settings.daily_ai_call_limit == 0:
        return
    with get_conn() as conn:
        count = conn.execute(
            """
            SELECT COUNT(*) AS n FROM usage_logs
            WHERE user_id = %s
              AND action_type IN ('ai_search', 'query_eval')
              AND created_at >= (NOW() - INTERVAL '1 day')::text
            """,
            (user_id,),
        ).fetchone()["n"]
    if count >= settings.daily_ai_call_limit:
        raise HTTPException(status_code=429, detail="Daily AI call limit reached")


def log_usage(user_id: str, action_type: str, model: str, tokens_in: int, tokens_out: int) -> None:
    """Record a Claude API call in usage_logs."""
    _now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO usage_logs (user_id, action_type, model, tokens_in, tokens_out, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, action_type, model, tokens_in, tokens_out, _now),
        )
