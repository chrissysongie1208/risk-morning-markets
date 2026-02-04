"""Database setup and operations for the Morning Markets app.

Uses asyncpg via databases library for async PostgreSQL access.
The database URL is read from DATABASE_URL environment variable.
"""

import os
import uuid
from datetime import datetime
from typing import Optional

from databases import Database

from models import (
    User, Market, Order, Trade, Position, Participant,
    MarketStatus, OrderSide, OrderStatus
)

# Database URL from environment, defaulting to local PostgreSQL
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/morning_markets"
)

# databases library instance
database = Database(DATABASE_URL)

# Default position limit
DEFAULT_POSITION_LIMIT = 20


def generate_id() -> str:
    """Generate a UUID for database records."""
    return str(uuid.uuid4())


async def connect_db() -> None:
    """Connect to the database."""
    await database.connect()


async def disconnect_db() -> None:
    """Disconnect from the database."""
    await database.disconnect()


async def init_db() -> None:
    """Initialize the database schema."""
    # Note: The database connection must be established before calling this
    # We create tables if they don't exist

    # Users table
    await database.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            display_name TEXT UNIQUE NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Config table
    await database.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Participants table (pre-registered names by admin)
    await database.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            id TEXT PRIMARY KEY,
            display_name TEXT UNIQUE NOT NULL,
            created_by_admin INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            claimed_by_user_id TEXT REFERENCES users(id)
        )
    """)

    # Markets table
    await database.execute("""
        CREATE TABLE IF NOT EXISTS markets (
            id TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'OPEN',
            settlement_value REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            settled_at TEXT
        )
    """)

    # Orders table
    await database.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            market_id TEXT NOT NULL REFERENCES markets(id),
            user_id TEXT NOT NULL REFERENCES users(id),
            side TEXT NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            remaining_quantity INTEGER NOT NULL,
            status TEXT DEFAULT 'OPEN',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Trades table
    await database.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id TEXT PRIMARY KEY,
            market_id TEXT NOT NULL REFERENCES markets(id),
            buy_order_id TEXT NOT NULL REFERENCES orders(id),
            sell_order_id TEXT NOT NULL REFERENCES orders(id),
            buyer_id TEXT NOT NULL REFERENCES users(id),
            seller_id TEXT NOT NULL REFERENCES users(id),
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Positions table
    await database.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id TEXT PRIMARY KEY,
            market_id TEXT NOT NULL REFERENCES markets(id),
            user_id TEXT NOT NULL REFERENCES users(id),
            net_quantity INTEGER DEFAULT 0,
            total_cost REAL DEFAULT 0,
            UNIQUE(market_id, user_id)
        )
    """)

    # Create indexes for performance
    await database.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_market_status
        ON orders(market_id, status)
    """)
    await database.execute("""
        CREATE INDEX IF NOT EXISTS idx_trades_market
        ON trades(market_id)
    """)
    await database.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_market_user
        ON positions(market_id, user_id)
    """)

    # Initialize default config if not exists
    # PostgreSQL uses ON CONFLICT instead of INSERT OR IGNORE
    await database.execute("""
        INSERT INTO config (key, value) VALUES (:key, :value)
        ON CONFLICT (key) DO NOTHING
    """, {"key": "position_limit", "value": str(DEFAULT_POSITION_LIMIT)})


# ============ User Operations ============

async def create_user(display_name: str, is_admin: bool = False) -> User:
    """Create a new user. Raises ValueError if display_name already exists."""
    user_id = generate_id()
    now = datetime.utcnow().isoformat()

    try:
        await database.execute("""
            INSERT INTO users (id, display_name, is_admin, created_at)
            VALUES (:id, :display_name, :is_admin, :created_at)
        """, {
            "id": user_id,
            "display_name": display_name,
            "is_admin": int(is_admin),
            "created_at": now
        })
    except Exception as e:
        # asyncpg raises UniqueViolationError for duplicate key
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise ValueError(f"Display name '{display_name}' already exists")
        raise

    return User(
        id=user_id,
        display_name=display_name,
        is_admin=is_admin,
        created_at=datetime.fromisoformat(now)
    )


async def get_user_by_id(user_id: str) -> Optional[User]:
    """Get a user by ID."""
    row = await database.fetch_one(
        "SELECT * FROM users WHERE id = :id", {"id": user_id}
    )
    if row:
        return User(
            id=row["id"],
            display_name=row["display_name"],
            is_admin=bool(row["is_admin"]),
            created_at=datetime.fromisoformat(row["created_at"])
        )
    return None


async def get_user_by_name(display_name: str) -> Optional[User]:
    """Get a user by display name."""
    row = await database.fetch_one(
        "SELECT * FROM users WHERE display_name = :name", {"name": display_name}
    )
    if row:
        return User(
            id=row["id"],
            display_name=row["display_name"],
            is_admin=bool(row["is_admin"]),
            created_at=datetime.fromisoformat(row["created_at"])
        )
    return None


# ============ Market Operations ============

async def create_market(question: str, description: Optional[str] = None) -> Market:
    """Create a new market."""
    market_id = generate_id()
    now = datetime.utcnow().isoformat()

    await database.execute("""
        INSERT INTO markets (id, question, description, status, created_at)
        VALUES (:id, :question, :description, 'OPEN', :created_at)
    """, {
        "id": market_id,
        "question": question,
        "description": description,
        "created_at": now
    })

    return Market(
        id=market_id,
        question=question,
        description=description,
        status=MarketStatus.OPEN,
        settlement_value=None,
        created_at=datetime.fromisoformat(now),
        settled_at=None
    )


async def get_market(market_id: str) -> Optional[Market]:
    """Get a market by ID."""
    row = await database.fetch_one(
        "SELECT * FROM markets WHERE id = :id", {"id": market_id}
    )
    if row:
        return Market(
            id=row["id"],
            question=row["question"],
            description=row["description"],
            status=MarketStatus(row["status"]),
            settlement_value=row["settlement_value"],
            created_at=datetime.fromisoformat(row["created_at"]),
            settled_at=datetime.fromisoformat(row["settled_at"]) if row["settled_at"] else None
        )
    return None


async def get_all_markets() -> list[Market]:
    """Get all markets, ordered by creation time (newest first)."""
    rows = await database.fetch_all(
        "SELECT * FROM markets ORDER BY created_at DESC"
    )
    return [
        Market(
            id=row["id"],
            question=row["question"],
            description=row["description"],
            status=MarketStatus(row["status"]),
            settlement_value=row["settlement_value"],
            created_at=datetime.fromisoformat(row["created_at"]),
            settled_at=datetime.fromisoformat(row["settled_at"]) if row["settled_at"] else None
        )
        for row in rows
    ]


async def update_market_status(market_id: str, status: MarketStatus) -> None:
    """Update market status."""
    await database.execute(
        "UPDATE markets SET status = :status WHERE id = :id",
        {"status": status.value, "id": market_id}
    )


async def settle_market(market_id: str, settlement_value: float) -> None:
    """Settle a market with the given value."""
    now = datetime.utcnow().isoformat()
    await database.execute("""
        UPDATE markets
        SET status = 'SETTLED', settlement_value = :value, settled_at = :settled_at
        WHERE id = :id
    """, {"value": settlement_value, "settled_at": now, "id": market_id})


# ============ Order Operations ============

async def create_order(
    market_id: str, user_id: str, side: OrderSide,
    price: float, quantity: int
) -> Order:
    """Create a new order."""
    order_id = generate_id()
    now = datetime.utcnow().isoformat()

    await database.execute("""
        INSERT INTO orders (id, market_id, user_id, side, price, quantity,
                          remaining_quantity, status, created_at)
        VALUES (:id, :market_id, :user_id, :side, :price, :quantity,
                :remaining_quantity, 'OPEN', :created_at)
    """, {
        "id": order_id,
        "market_id": market_id,
        "user_id": user_id,
        "side": side.value,
        "price": price,
        "quantity": quantity,
        "remaining_quantity": quantity,
        "created_at": now
    })

    return Order(
        id=order_id,
        market_id=market_id,
        user_id=user_id,
        side=side,
        price=price,
        quantity=quantity,
        remaining_quantity=quantity,
        status=OrderStatus.OPEN,
        created_at=datetime.fromisoformat(now)
    )


async def get_order(order_id: str) -> Optional[Order]:
    """Get an order by ID."""
    row = await database.fetch_one(
        "SELECT * FROM orders WHERE id = :id", {"id": order_id}
    )
    if row:
        return Order(
            id=row["id"],
            market_id=row["market_id"],
            user_id=row["user_id"],
            side=OrderSide(row["side"]),
            price=row["price"],
            quantity=row["quantity"],
            remaining_quantity=row["remaining_quantity"],
            status=OrderStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"])
        )
    return None


async def get_open_orders(
    market_id: str,
    side: Optional[OrderSide] = None,
    exclude_user_id: Optional[str] = None
) -> list[Order]:
    """Get open orders for a market, optionally filtered by side and excluding a user."""
    query = "SELECT * FROM orders WHERE market_id = :market_id AND status = 'OPEN'"
    params: dict = {"market_id": market_id}

    if side:
        query += " AND side = :side"
        params["side"] = side.value

    if exclude_user_id:
        query += " AND user_id != :exclude_user_id"
        params["exclude_user_id"] = exclude_user_id

    # Order by price (best first) and time (oldest first for same price)
    if side == OrderSide.BID:
        query += " ORDER BY price DESC, created_at ASC"
    else:
        query += " ORDER BY price ASC, created_at ASC"

    rows = await database.fetch_all(query, params)

    return [
        Order(
            id=row["id"],
            market_id=row["market_id"],
            user_id=row["user_id"],
            side=OrderSide(row["side"]),
            price=row["price"],
            quantity=row["quantity"],
            remaining_quantity=row["remaining_quantity"],
            status=OrderStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"])
        )
        for row in rows
    ]


async def update_order_quantity(order_id: str, remaining_quantity: int) -> None:
    """Update an order's remaining quantity and status."""
    status = OrderStatus.OPEN if remaining_quantity > 0 else OrderStatus.FILLED
    await database.execute("""
        UPDATE orders SET remaining_quantity = :remaining, status = :status WHERE id = :id
    """, {"remaining": remaining_quantity, "status": status.value, "id": order_id})


async def cancel_order(order_id: str) -> None:
    """Cancel an order."""
    await database.execute(
        "UPDATE orders SET status = 'CANCELLED' WHERE id = :id",
        {"id": order_id}
    )


async def get_user_open_order_exposure(market_id: str, user_id: str) -> tuple[int, int]:
    """
    Get a user's open order exposure in a market.

    Returns:
        Tuple of (total_bid_quantity, total_offer_quantity) from open orders.
        This represents the maximum position change if all orders fill.
    """
    # Sum remaining quantity for open bids
    row = await database.fetch_one("""
        SELECT COALESCE(SUM(remaining_quantity), 0) as total
        FROM orders
        WHERE market_id = :market_id AND user_id = :user_id
              AND side = 'BID' AND status = 'OPEN'
    """, {"market_id": market_id, "user_id": user_id})
    bid_exposure = int(row["total"]) if row else 0

    # Sum remaining quantity for open offers
    row = await database.fetch_one("""
        SELECT COALESCE(SUM(remaining_quantity), 0) as total
        FROM orders
        WHERE market_id = :market_id AND user_id = :user_id
              AND side = 'OFFER' AND status = 'OPEN'
    """, {"market_id": market_id, "user_id": user_id})
    offer_exposure = int(row["total"]) if row else 0

    return (bid_exposure, offer_exposure)


async def cancel_all_market_orders(market_id: str) -> None:
    """Cancel all open orders for a market."""
    await database.execute("""
        UPDATE orders SET status = 'CANCELLED'
        WHERE market_id = :market_id AND status = 'OPEN'
    """, {"market_id": market_id})


# ============ Trade Operations ============

async def create_trade(
    market_id: str, buy_order_id: str, sell_order_id: str,
    buyer_id: str, seller_id: str, price: float, quantity: int
) -> Trade:
    """Create a new trade record."""
    trade_id = generate_id()
    now = datetime.utcnow().isoformat()

    await database.execute("""
        INSERT INTO trades (id, market_id, buy_order_id, sell_order_id,
                          buyer_id, seller_id, price, quantity, created_at)
        VALUES (:id, :market_id, :buy_order_id, :sell_order_id,
                :buyer_id, :seller_id, :price, :quantity, :created_at)
    """, {
        "id": trade_id,
        "market_id": market_id,
        "buy_order_id": buy_order_id,
        "sell_order_id": sell_order_id,
        "buyer_id": buyer_id,
        "seller_id": seller_id,
        "price": price,
        "quantity": quantity,
        "created_at": now
    })

    return Trade(
        id=trade_id,
        market_id=market_id,
        buy_order_id=buy_order_id,
        sell_order_id=sell_order_id,
        buyer_id=buyer_id,
        seller_id=seller_id,
        price=price,
        quantity=quantity,
        created_at=datetime.fromisoformat(now)
    )


async def get_recent_trades(market_id: str, limit: int = 10) -> list[Trade]:
    """Get recent trades for a market."""
    rows = await database.fetch_all("""
        SELECT * FROM trades
        WHERE market_id = :market_id
        ORDER BY created_at DESC
        LIMIT :limit
    """, {"market_id": market_id, "limit": limit})

    return [
        Trade(
            id=row["id"],
            market_id=row["market_id"],
            buy_order_id=row["buy_order_id"],
            sell_order_id=row["sell_order_id"],
            buyer_id=row["buyer_id"],
            seller_id=row["seller_id"],
            price=row["price"],
            quantity=row["quantity"],
            created_at=datetime.fromisoformat(row["created_at"])
        )
        for row in rows
    ]


async def get_all_trades(market_id: str) -> list[Trade]:
    """Get all trades for a market (for settlement calculations)."""
    rows = await database.fetch_all("""
        SELECT * FROM trades
        WHERE market_id = :market_id
        ORDER BY created_at ASC
    """, {"market_id": market_id})

    return [
        Trade(
            id=row["id"],
            market_id=row["market_id"],
            buy_order_id=row["buy_order_id"],
            sell_order_id=row["sell_order_id"],
            buyer_id=row["buyer_id"],
            seller_id=row["seller_id"],
            price=row["price"],
            quantity=row["quantity"],
            created_at=datetime.fromisoformat(row["created_at"])
        )
        for row in rows
    ]


# ============ Position Operations ============

async def get_position(market_id: str, user_id: str) -> Position:
    """Get a user's position in a market, creating if not exists."""
    row = await database.fetch_one("""
        SELECT * FROM positions WHERE market_id = :market_id AND user_id = :user_id
    """, {"market_id": market_id, "user_id": user_id})

    if row:
        return Position(
            id=row["id"],
            market_id=row["market_id"],
            user_id=row["user_id"],
            net_quantity=row["net_quantity"],
            total_cost=row["total_cost"]
        )

    # Create new position
    position_id = generate_id()
    await database.execute("""
        INSERT INTO positions (id, market_id, user_id, net_quantity, total_cost)
        VALUES (:id, :market_id, :user_id, 0, 0)
    """, {"id": position_id, "market_id": market_id, "user_id": user_id})

    return Position(
        id=position_id,
        market_id=market_id,
        user_id=user_id,
        net_quantity=0,
        total_cost=0.0
    )


async def update_position(
    market_id: str, user_id: str,
    quantity_delta: int, cost_delta: float
) -> Position:
    """Update a user's position after a trade."""
    # Get or create position
    position = await get_position(market_id, user_id)

    new_quantity = position.net_quantity + quantity_delta
    new_cost = position.total_cost + cost_delta

    await database.execute("""
        UPDATE positions
        SET net_quantity = :quantity, total_cost = :cost
        WHERE market_id = :market_id AND user_id = :user_id
    """, {
        "quantity": new_quantity,
        "cost": new_cost,
        "market_id": market_id,
        "user_id": user_id
    })

    return Position(
        id=position.id,
        market_id=market_id,
        user_id=user_id,
        net_quantity=new_quantity,
        total_cost=new_cost
    )


async def get_all_positions(market_id: str) -> list[Position]:
    """Get all positions for a market."""
    rows = await database.fetch_all(
        "SELECT * FROM positions WHERE market_id = :market_id",
        {"market_id": market_id}
    )

    return [
        Position(
            id=row["id"],
            market_id=row["market_id"],
            user_id=row["user_id"],
            net_quantity=row["net_quantity"],
            total_cost=row["total_cost"]
        )
        for row in rows
    ]


# ============ Config Operations ============

async def get_position_limit() -> int:
    """Get the current position limit."""
    row = await database.fetch_one(
        "SELECT value FROM config WHERE key = 'position_limit'"
    )
    return int(row["value"]) if row else DEFAULT_POSITION_LIMIT


async def set_position_limit(limit: int) -> None:
    """Set the position limit."""
    # PostgreSQL uses ON CONFLICT for upsert
    await database.execute("""
        INSERT INTO config (key, value) VALUES ('position_limit', :value)
        ON CONFLICT (key) DO UPDATE SET value = :value
    """, {"value": str(limit)})


# ============ Participant Operations ============

async def create_participant(display_name: str) -> Participant:
    """Create a pre-registered participant name (admin only).

    Raises ValueError if display_name already exists.
    """
    participant_id = generate_id()
    now = datetime.utcnow().isoformat()

    try:
        await database.execute("""
            INSERT INTO participants (id, display_name, created_by_admin, created_at)
            VALUES (:id, :display_name, 1, :created_at)
        """, {
            "id": participant_id,
            "display_name": display_name,
            "created_at": now
        })
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise ValueError(f"Participant name '{display_name}' already exists")
        raise

    return Participant(
        id=participant_id,
        display_name=display_name,
        created_by_admin=True,
        created_at=datetime.fromisoformat(now),
        claimed_by_user_id=None
    )


async def get_participant_by_id(participant_id: str) -> Optional[Participant]:
    """Get a participant by ID."""
    row = await database.fetch_one(
        "SELECT * FROM participants WHERE id = :id", {"id": participant_id}
    )
    if row:
        return Participant(
            id=row["id"],
            display_name=row["display_name"],
            created_by_admin=bool(row["created_by_admin"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            claimed_by_user_id=row["claimed_by_user_id"]
        )
    return None


async def get_participant_by_name(display_name: str) -> Optional[Participant]:
    """Get a participant by display name."""
    row = await database.fetch_one(
        "SELECT * FROM participants WHERE display_name = :name", {"name": display_name}
    )
    if row:
        return Participant(
            id=row["id"],
            display_name=row["display_name"],
            created_by_admin=bool(row["created_by_admin"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            claimed_by_user_id=row["claimed_by_user_id"]
        )
    return None


async def get_available_participants() -> list[Participant]:
    """Get all participants that haven't been claimed yet."""
    rows = await database.fetch_all("""
        SELECT * FROM participants
        WHERE claimed_by_user_id IS NULL
        ORDER BY display_name ASC
    """)
    return [
        Participant(
            id=row["id"],
            display_name=row["display_name"],
            created_by_admin=bool(row["created_by_admin"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            claimed_by_user_id=row["claimed_by_user_id"]
        )
        for row in rows
    ]


async def get_all_participants() -> list[Participant]:
    """Get all participants (for admin panel)."""
    rows = await database.fetch_all("""
        SELECT * FROM participants
        ORDER BY display_name ASC
    """)
    return [
        Participant(
            id=row["id"],
            display_name=row["display_name"],
            created_by_admin=bool(row["created_by_admin"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            claimed_by_user_id=row["claimed_by_user_id"]
        )
        for row in rows
    ]


async def claim_participant(participant_id: str, user_id: str) -> None:
    """Claim a participant name for a user."""
    await database.execute("""
        UPDATE participants
        SET claimed_by_user_id = :user_id
        WHERE id = :participant_id AND claimed_by_user_id IS NULL
    """, {"user_id": user_id, "participant_id": participant_id})


async def unclaim_participant(participant_id: str) -> None:
    """Unclaim a participant name (release it back to available)."""
    await database.execute("""
        UPDATE participants
        SET claimed_by_user_id = NULL
        WHERE id = :participant_id
    """, {"participant_id": participant_id})


async def delete_participant(participant_id: str) -> bool:
    """Delete a participant. Returns True if deleted, False if not found or claimed."""
    # Only delete if not claimed
    result = await database.execute("""
        DELETE FROM participants
        WHERE id = :id AND claimed_by_user_id IS NULL
    """, {"id": participant_id})
    return result > 0 if result else False


# Synchronous init for testing/CLI
def init_db_sync() -> None:
    """Synchronous wrapper for init_db."""
    import asyncio
    asyncio.run(async_init_db_sync())


async def async_init_db_sync() -> None:
    """Async helper for sync init."""
    await connect_db()
    await init_db()
    await disconnect_db()


if __name__ == "__main__":
    init_db_sync()
    print(f"Database initialized at {DATABASE_URL}")
