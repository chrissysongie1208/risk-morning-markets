"""Pytest fixtures for Morning Markets tests.

These fixtures provide clean database state and helper functions for testing.
Uses PostgreSQL via the databases library.
"""

import asyncio
import sys
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import database as db
from models import OrderSide, MarketStatus


# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """Set up a fresh test database for each test.

    Connects to PostgreSQL, initializes schema, and truncates all tables
    between tests to ensure clean state.
    """
    # Connect to the database
    await db.connect_db()

    # Initialize the schema (creates tables if they don't exist)
    await db.init_db()

    # Truncate all tables for clean state (order matters due to FK constraints)
    # Use TRUNCATE CASCADE to handle foreign key dependencies
    await db.database.execute("TRUNCATE TABLE trades CASCADE")
    await db.database.execute("TRUNCATE TABLE orders CASCADE")
    await db.database.execute("TRUNCATE TABLE positions CASCADE")
    await db.database.execute("TRUNCATE TABLE markets CASCADE")
    await db.database.execute("TRUNCATE TABLE participants CASCADE")
    await db.database.execute("TRUNCATE TABLE users CASCADE")
    # Re-initialize config with default position limit
    await db.database.execute("DELETE FROM config")
    await db.database.execute("""
        INSERT INTO config (key, value) VALUES ('position_limit', :value)
    """, {"value": str(db.DEFAULT_POSITION_LIMIT)})

    yield

    # Disconnect after test
    await db.disconnect_db()


@pytest_asyncio.fixture
async def market():
    """Create a test market."""
    return await db.create_market(
        question="Test market question?",
        description="Test description"
    )


@pytest_asyncio.fixture
async def user_alice():
    """Create test user Alice."""
    return await db.create_user("Alice")


@pytest_asyncio.fixture
async def user_bob():
    """Create test user Bob."""
    return await db.create_user("Bob")


@pytest_asyncio.fixture
async def user_charlie():
    """Create test user Charlie."""
    return await db.create_user("Charlie")


@pytest_asyncio.fixture
async def position_limit():
    """Get the current position limit."""
    return await db.get_position_limit()


async def create_resting_order(market_id: str, user_id: str, side: OrderSide, price: float, quantity: int):
    """Helper to create a resting order directly in the database.

    This bypasses the matching engine to set up test scenarios.
    """
    return await db.create_order(
        market_id=market_id,
        user_id=user_id,
        side=side,
        price=price,
        quantity=quantity
    )


async def set_user_position(market_id: str, user_id: str, net_quantity: int, total_cost: float = 0):
    """Helper to set up a user's position directly.

    Creates the position if it doesn't exist, or updates it if it does.
    """
    position = await db.get_position(market_id, user_id)
    # Update to target values
    await db.update_position(
        market_id=market_id,
        user_id=user_id,
        quantity_delta=net_quantity - position.net_quantity,
        cost_delta=total_cost - position.total_cost
    )
    return await db.get_position(market_id, user_id)


async def create_participant_and_get_id(display_name: str) -> str:
    """Helper to create a participant and return their ID for joining.

    This creates a pre-registered participant name that can be used in the /join flow.
    """
    participant = await db.create_participant(display_name)
    return participant.id
