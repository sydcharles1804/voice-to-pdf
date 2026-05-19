import os
from supabase import Client, create_client

_URL = os.getenv("SUPABASE_URL", "")
_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def get_client(user_jwt: str) -> Client:
    """User-scoped client — every query runs under the caller's identity.

    Passes the JWT to PostgREST so RLS policies are enforced automatically.
    Use this for all database reads and writes.
    """
    client = create_client(_URL, _ANON_KEY)
    client.postgrest.auth(user_jwt)
    return client


def get_admin_client() -> Client:
    """Service-role client — bypasses RLS entirely.

    Use ONLY for operations the user cannot perform via their own JWT, such as
    server-side Storage uploads where supabase-py's storage layer does not
    inherit the PostgREST auth token.  Never use this to return data to clients.
    """
    if not _SERVICE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not set")
    return create_client(_URL, _SERVICE_KEY)
