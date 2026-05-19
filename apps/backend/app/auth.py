import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import create_client

_bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """FastAPI dependency — verifies the Supabase JWT and returns {user, token}.

    Raises 401 if the token is missing, malformed, or expired.
    Inject this into any route that requires an authenticated user.
    """
    token = credentials.credentials
    try:
        # get_user() validates the JWT against Supabase Auth (server-side check,
        # not just a local decode) and returns the canonical user object.
        client = create_client(
            os.getenv("SUPABASE_URL", ""),
            os.getenv("SUPABASE_ANON_KEY", ""),
        )
        response = client.auth.get_user(token)
        if not response.user:
            raise ValueError("no user in response")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"user": response.user, "token": token}
