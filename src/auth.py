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


# Session exclusivity timeout in seconds
SESSION_ACTIVITY_TIMEOUT = 30


async def login_participant(participant_id: str) -> tuple[User, str]:
    """Claim a pre-registered participant and return (user, session_token).

    The participant must exist and not be claimed by another user.
    Creates a new user record linked to the participant.

    Session exclusivity: If the participant is claimed AND the user has been
    active within SESSION_ACTIVITY_TIMEOUT seconds, reject the login attempt.
    If the session is stale (no activity for > timeout), allow takeover.

    Raises ValueError if participant doesn't exist, is already claimed with
    an active session, or other errors.
    """
    # Get the participant
    participant = await db.get_participant_by_id(participant_id)
    if not participant:
        raise ValueError("Participant not found")

    if participant.claimed_by_user_id:
        # Participant is claimed - check if user has an active session
        existing_user = await db.get_user_by_id(participant.claimed_by_user_id)
        if existing_user:
            # Check if the existing user has an active session
            if await db.is_user_active(existing_user.id, SESSION_ACTIVITY_TIMEOUT):
                # Active session exists - reject login
                raise ValueError("Participant already in use")

            # Session is stale - allow takeover by creating new session
            # Update activity timestamp to mark the takeover
            await db.update_user_activity(existing_user.id)
            token = create_session(existing_user.id)
            return existing_user, token
        # User was deleted but participant still claimed - should not happen
        raise ValueError("Participant session is invalid")

    # Check if a user with this display name already exists
    existing_user = await db.get_user_by_name(participant.display_name)
    if existing_user:
        # User exists - link participant to them and create session
        await db.claim_participant(participant_id, existing_user.id)
        await db.update_user_activity(existing_user.id)
        token = create_session(existing_user.id)
        return existing_user, token

    # Create new user with participant's display name
    user = await db.create_user(participant.display_name, is_admin=False)

    # Link participant to user
    await db.claim_participant(participant_id, user.id)

    # Update activity timestamp for new user
    await db.update_user_activity(user.id)

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
