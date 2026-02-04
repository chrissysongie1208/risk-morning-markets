"""Authentication and session management for the Morning Markets app.

Uses cookie-based sessions for user tracking.
Admin authentication uses hardcoded credentials (chrson/optiver).
"""

import secrets
from typing import Optional
from fastapi import Cookie, HTTPException, status

from models import User
import database as db

# Admin credentials
ADMIN_USERNAME = "chrson"
ADMIN_PASSWORD = "optiver"

# In-memory session store (user_id -> session_token)
# For a production app, this would be in Redis or similar
_sessions: dict[str, str] = {}  # session_token -> user_id


def generate_session_token() -> str:
    """Generate a secure random session token."""
    return secrets.token_urlsafe(32)


def create_session(user_id: str) -> str:
    """Create a new session for a user and return the session token."""
    token = generate_session_token()
    _sessions[token] = user_id
    return token


def get_user_id_from_session(session_token: Optional[str]) -> Optional[str]:
    """Get user_id from a session token."""
    if not session_token:
        return None
    return _sessions.get(session_token)


def delete_session(session_token: str) -> None:
    """Delete a session."""
    _sessions.pop(session_token, None)


async def get_current_user(session: Optional[str] = Cookie(None)) -> Optional[User]:
    """Get the current user from the session cookie.

    Returns None if not logged in (doesn't raise an error).
    """
    user_id = get_user_id_from_session(session)
    if not user_id:
        return None
    return await db.get_user_by_id(user_id)


async def require_user(session: Optional[str] = Cookie(None)) -> User:
    """Require a logged-in user. Raises 401 if not authenticated."""
    user = await get_current_user(session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return user


async def require_admin(session: Optional[str] = Cookie(None)) -> User:
    """Require an admin user. Raises 401/403 if not authenticated/authorized."""
    user = await require_user(session)
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


def verify_admin_credentials(username: str, password: str) -> bool:
    """Verify admin credentials."""
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD


async def login_participant(display_name: str) -> tuple[User, str]:
    """Create a participant user and return (user, session_token).

    Raises ValueError if display_name already exists.
    """
    # Check if this name is already taken
    existing = await db.get_user_by_name(display_name)
    if existing:
        raise ValueError(f"Display name '{display_name}' is already taken")

    # Create new user
    user = await db.create_user(display_name, is_admin=False)
    token = create_session(user.id)
    return user, token


async def login_admin(username: str, password: str) -> tuple[User, str]:
    """Login as admin and return (user, session_token).

    Raises ValueError if credentials are invalid.
    Creates admin user if doesn't exist.
    """
    if not verify_admin_credentials(username, password):
        raise ValueError("Invalid admin credentials")

    # Get or create admin user
    admin_user = await db.get_user_by_name(ADMIN_USERNAME)
    if not admin_user:
        admin_user = await db.create_user(ADMIN_USERNAME, is_admin=True)

    token = create_session(admin_user.id)
    return admin_user, token
