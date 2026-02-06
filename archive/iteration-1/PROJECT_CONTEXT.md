# Project Context

## Goal

Build a **prediction market web app** for trivia-style questions where:
- Admin (chrson) creates markets with questions like "Weight of largest recorded polar bear in kg?"
- Participants join with a display name (Kahoot-style, no passwords)
- Users place bids and offers; crossing orders auto-match
- Admin settles markets with the actual answer
- Results show both binary P&L (lots won/lost) and linear P&L (dollar amount)

---

## Technical Context

### Tech Stack
| Component | Choice |
|-----------|--------|
| Backend | Python 3.10+ with FastAPI |
| Frontend | HTML + Jinja2 + HTMX (1-second polling for updates) |
| Database | PostgreSQL (via asyncpg) - works locally and on Render.com |
| Styling | PicoCSS or minimal custom CSS |
| Deployment | Render.com (free tier) |

### Key Libraries
```
fastapi
uvicorn
jinja2
python-multipart  # for form handling
asyncpg           # async PostgreSQL
databases         # async database abstraction (supports PostgreSQL)
pytest            # testing
pytest-asyncio    # async test support
httpx             # test client
```

### Database Connection
The app reads the database URL from the `DATABASE_URL` environment variable:
- **Local development**: `postgresql://localhost/morning_markets` (or use Docker)
- **Render.com**: Automatically set by Render when you add a PostgreSQL database

```python
import os
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/morning_markets")
```

### Database Schema
```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    display_name TEXT UNIQUE NOT NULL,
    is_admin INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE markets (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'OPEN',  -- OPEN | CLOSED | SETTLED
    settlement_value REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    settled_at TEXT
);

CREATE TABLE orders (
    id TEXT PRIMARY KEY,
    market_id TEXT NOT NULL REFERENCES markets(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    side TEXT NOT NULL,  -- BID | OFFER
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    remaining_quantity INTEGER NOT NULL,
    status TEXT DEFAULT 'OPEN',  -- OPEN | FILLED | CANCELLED
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE trades (
    id TEXT PRIMARY KEY,
    market_id TEXT NOT NULL REFERENCES markets(id),
    buy_order_id TEXT NOT NULL REFERENCES orders(id),
    sell_order_id TEXT NOT NULL REFERENCES orders(id),
    buyer_id TEXT NOT NULL REFERENCES users(id),
    seller_id TEXT NOT NULL REFERENCES users(id),
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE positions (
    id TEXT PRIMARY KEY,
    market_id TEXT NOT NULL REFERENCES markets(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    net_quantity INTEGER DEFAULT 0,
    total_cost REAL DEFAULT 0,
    UNIQUE(market_id, user_id)
);
```

---

## Constraints

### Authentication
- **Admin**: Username `chrson`, password `optiver`
- **Participants**: Enter display name only, no password. Reject duplicate names.
- Landing page offers choice: "Join as Admin" or "Join as Participant"

### Trading Rules
- **Order matching**: Auto-match when orders cross (bid >= best offer price)
- **Price priority**: Taker gets maker's price (price-time priority)
- **Position limit**: Net position limit per user, default 20 lots (admin can change globally)
- **Shorting**: Allowed (negative positions) up to the position limit

### Market Lifecycle
1. Admin creates market (OPEN status)
2. Users place bids/offers, orders match automatically when crossing
3. Admin closes market (CLOSED status) - no new orders accepted
4. Admin settles market with actual value (SETTLED status)
5. P&L calculated and displayed

### Display Requirements
- **Order book**: Show ALL orders (not aggregated by price level)
- **Trade history**: Show last 10 trades on market page
- **Results**: Show both binary P&L (lots won/lost per trade) and linear P&L (dollar amount)
- **Leaderboard**: Aggregate P&L across all settled markets

### Data Persistence
- All markets kept historically (no reset/delete)
- PostgreSQL database survives restarts and deployments

### Scale
- Up to 20 concurrent users
- 1-second polling for order book updates (no WebSocket needed)

### Deployment (Render.com)
The app must be deployable to Render.com free tier:
- **Web Service**: Python, uses `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **PostgreSQL**: Free tier database (auto-provisioned)
- **Environment**: `DATABASE_URL` set automatically by Render
- **Build command**: `pip install -r requirements.txt`
- **Start command**: `cd src && uvicorn main:app --host 0.0.0.0 --port $PORT`

Required files for Render:
- `requirements.txt` - all dependencies
- `render.yaml` - Render blueprint (optional but recommended)

---

## Success Criteria

### Functional Requirements
- [ ] Users can join with unique display name
- [ ] Admin can log in with chrson/optiver
- [ ] Admin can create markets with question + optional description
- [ ] Users can place bids and offers
- [ ] Crossing orders auto-match at maker's price
- [ ] Position limit enforced (rejects orders that would exceed limit)
- [ ] Users can cancel their own open orders
- [ ] Admin can close markets (stops new orders)
- [ ] Admin can settle markets with actual value
- [ ] Settlement page shows binary + linear P&L per user
- [ ] Leaderboard shows aggregate P&L across all settled markets
- [ ] Order book displays all orders, updates every 1 second
- [ ] Trade history shows last 10 trades

### Non-Functional Requirements
- [ ] App runs locally with PostgreSQL (via Docker or local install)
- [ ] App deploys to Render.com and is accessible via public URL
- [ ] PostgreSQL database persists between restarts and deployments
- [ ] Handles 20 concurrent users without issues
- [ ] Multiple users can join and trade simultaneously in the same market

### Test Requirements
- [ ] Unit tests for matching engine (see below)
- [ ] Unit tests for settlement logic (see below)
- [ ] Integration tests for API endpoints (see below)
- [ ] Concurrent user tests (multiple users trading simultaneously)
- [ ] All tests pass with `pytest tests/`

---

## Test Specifications

### Unit Tests: Matching Engine (`tests/test_matching.py`)

```python
def test_exact_match():
    """
    Given: Offer at 100 for 5 lots exists
    When: Bid at 100 for 5 lots placed
    Then: Full match, trade at 100, both orders filled
    """

def test_partial_fill():
    """
    Given: Offer at 100 for 3 lots exists
    When: Bid at 100 for 10 lots placed
    Then: Partial match (3 lots at 100), bid has 7 lots resting
    """

def test_no_match_bid_below_offer():
    """
    Given: Offer at 100 for 5 lots exists
    When: Bid at 90 for 5 lots placed
    Then: No match, both orders rest in book
    """

def test_price_improvement():
    """
    Given: Offer at 100 for 5 lots exists
    When: Bid at 110 for 5 lots placed
    Then: Match at 100 (maker's price), not 110
    """

def test_multiple_fills():
    """
    Given: Offers at 100 (3 lots), 101 (3 lots), 102 (3 lots)
    When: Bid at 102 for 8 lots placed
    Then: Fills 3@100, 3@101, 2@102. Remaining 1 lot at 102 rests.
    """

def test_time_priority():
    """
    Given: Two offers at 100, first for 3 lots, second for 3 lots
    When: Bid at 100 for 4 lots placed
    Then: First offer fully filled, second partially (1 lot)
    """

def test_position_limit_rejects_order():
    """
    Given: User has +18 position, limit is 20
    When: User places bid for 5 lots
    Then: Order rejected (would result in +23 position)
    """

def test_position_limit_allows_reducing_order():
    """
    Given: User has +18 position, limit is 20
    When: User places offer for 5 lots
    Then: Order accepted (would result in +13 position)
    """

def test_position_limit_after_partial_fill():
    """
    Given: User has +15 position, limit is 20, offer exists for 10 lots
    When: User places bid for 10 lots
    Then: Fills 5 lots (to +20), remaining 5 rejected or not posted
    """

def test_self_trade_prevention():
    """
    Given: User A has offer at 100
    When: User A places bid at 100
    Then: No self-match occurs, bid rests in book
    """
```

### Unit Tests: Settlement (`tests/test_settlement.py`)

```python
def test_linear_pnl_long_profit():
    """
    Given: User long 10 lots @ avg price 50
    When: Market settles at 60
    Then: Linear P&L = 10 * (60 - 50) = +100
    """

def test_linear_pnl_long_loss():
    """
    Given: User long 10 lots @ avg price 50
    When: Market settles at 40
    Then: Linear P&L = 10 * (40 - 50) = -100
    """

def test_linear_pnl_short_profit():
    """
    Given: User short 10 lots @ avg price 50
    When: Market settles at 40
    Then: Linear P&L = -10 * (40 - 50) = +100
    """

def test_linear_pnl_short_loss():
    """
    Given: User short 10 lots @ avg price 50
    When: Market settles at 60
    Then: Linear P&L = -10 * (60 - 50) = -100
    """

def test_binary_pnl_single_winning_trade():
    """
    Given: User bought 5 lots @ 100
    When: Market settles at 110
    Then: Binary P&L = +5 (bought below settlement = won those lots)
    """

def test_binary_pnl_single_losing_trade():
    """
    Given: User bought 5 lots @ 100
    When: Market settles at 90
    Then: Binary P&L = -5 (bought above settlement = lost those lots)
    """

def test_binary_pnl_multiple_trades():
    """
    Given: User sold 10 lots @ 100, bought 5 lots @ 115
    When: Market settles at 110
    Then: Binary P&L = -10 (sold below settlement) + -5 (bought above settlement) = -15
    """

def test_settlement_cancels_open_orders():
    """
    Given: Market has open orders
    When: Market is settled
    Then: All open orders cancelled
    """

def test_zero_position_no_pnl():
    """
    Given: User has 0 net position (bought and sold equal amounts)
    When: Market settles
    Then: P&L calculated on closed trades, not just final position
    Note: This tests that total_cost tracking is correct
    """

def test_average_price_multiple_trades():
    """
    Given: User buys 5 @ 100, then buys 5 @ 110
    Then: Average price = (5*100 + 5*110) / 10 = 105
    When: Settles at 120
    Then: P&L = 10 * (120 - 105) = +150
    """
```

### Integration Tests: API (`tests/test_api.py`)

```python
def test_join_unique_name():
    """POST /join with unique name -> success, get session"""

def test_join_duplicate_name_rejected():
    """POST /join with existing name -> 400 error"""

def test_admin_login_correct_credentials():
    """POST /admin/login with chrson/optiver -> success"""

def test_admin_login_wrong_credentials():
    """POST /admin/login with wrong password -> 401"""

def test_create_market_as_admin():
    """POST /admin/markets as admin -> market created"""

def test_create_market_as_participant_rejected():
    """POST /admin/markets as non-admin -> 403"""

def test_place_order():
    """POST /markets/{id}/orders -> order created"""

def test_place_order_on_closed_market_rejected():
    """POST /markets/{id}/orders on CLOSED market -> 400"""

def test_cancel_own_order():
    """DELETE /orders/{id} on own order -> success"""

def test_cancel_other_user_order_rejected():
    """DELETE /orders/{id} on other's order -> 403"""

def test_settle_market_as_admin():
    """POST /admin/markets/{id}/settle -> market settled"""

def test_full_trade_lifecycle():
    """
    1. Admin creates market
    2. User A places offer at 100 for 5
    3. User B places bid at 100 for 5
    4. Verify trade created, positions updated
    5. Admin settles at 110
    6. Verify P&L: A = -50 (sold at 100, settled 110), B = +50
    """
```

### Concurrent User Tests (`tests/test_concurrent.py`)

```python
def test_multiple_users_join_simultaneously():
    """
    Given: Empty system
    When: 10 users join at the same time (async/parallel requests)
    Then: All 10 users successfully created with unique IDs
    """

def test_multiple_users_place_orders_simultaneously():
    """
    Given: Market exists, 5 users joined
    When: All 5 users place orders at the same time
    Then: All orders created correctly, no race conditions
    """

def test_concurrent_matching():
    """
    Given: Market with offer at 100 for 10 lots
    When: 3 users simultaneously place bids at 100 for 5 lots each
    Then: First 2 bids fill (10 lots total), third bid rests or partially fills
          No double-fills, no lost orders
    """

def test_concurrent_order_and_cancel():
    """
    Given: User A has open order
    When: User A cancels order while User B places crossing order (simultaneously)
    Then: Either cancel succeeds (no trade) OR trade happens (cancel fails)
          No inconsistent state
    """

def test_five_users_trading_session():
    """
    Full simulation of 5 users trading in a market:
    1. Admin creates market "Test Market"
    2. Users Alice, Bob, Carol, Dave, Eve join
    3. Alice places OFFER at 100 for 10 lots
    4. Bob places BID at 95 for 5 lots (no match, rests)
    5. Carol places BID at 100 for 3 lots (matches with Alice)
    6. Dave places BID at 100 for 4 lots (matches with Alice)
    7. Eve places OFFER at 98 for 5 lots (matches with Bob's bid at 95? No - offer > bid)
    8. Eve places OFFER at 94 for 3 lots (matches with Bob's bid at 95, fills 3)
    9. Admin settles at 102
    10. Verify all positions and P&L are correct:
        - Alice: sold 7 @ 100, position -7, linear P&L = -7*(102-100) = -14
        - Bob: bought 3 @ 94 (from Eve), position +3, linear P&L = +3*(102-94) = +24
        - Carol: bought 3 @ 100, position +3, linear P&L = +3*(102-100) = +6
        - Dave: bought 4 @ 100, position +4, linear P&L = +4*(102-100) = +8
        - Eve: sold 3 @ 94, position -3, linear P&L = -3*(102-94) = -24
    """

def test_rapid_order_placement():
    """
    Given: Market exists
    When: Single user places 20 orders in rapid succession
    Then: All orders processed correctly, position limits enforced throughout
    """
```

---

## File Structure

```
morning-_markets_app/
├── src/
│   ├── main.py               # FastAPI app, routes
│   ├── database.py           # SQLite setup, queries
│   ├── models.py             # Pydantic models
│   ├── matching.py           # Matching engine
│   ├── settlement.py         # Settlement + P&L logic
│   ├── auth.py               # Session management, admin auth
│   └── templates/
│       ├── base.html         # Base layout
│       ├── index.html        # Landing/join page
│       ├── markets.html      # Market list
│       ├── market.html       # Trading view
│       ├── results.html      # Settlement results
│       ├── leaderboard.html  # Aggregate scores
│       ├── admin.html        # Admin panel
│       └── partials/
│           ├── orderbook.html
│           ├── position.html
│           └── trades.html
├── static/
│   └── style.css
├── data/                     # Created at runtime
│   └── markets.db
├── tests/
│   ├── conftest.py           # Pytest fixtures
│   ├── test_matching.py
│   ├── test_settlement.py
│   ├── test_api.py
│   └── test_concurrent.py    # Multi-user concurrent tests
├── requirements.txt
├── render.yaml               # Render.com deployment config
├── Dockerfile                # For local PostgreSQL testing (optional)
├── docker-compose.yml        # Local dev with PostgreSQL
└── README.md                 # Setup + run instructions
```

---

## Running the App

### Local Development (with Docker)

```bash
# Start PostgreSQL in Docker
docker-compose up -d

# Install dependencies
pip install -r requirements.txt

# Run the server
cd src && DATABASE_URL=postgresql://postgres:postgres@localhost:5432/morning_markets uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Access locally
open http://localhost:8000
```

### Deploy to Render.com

1. Push code to GitHub
2. Go to https://render.com and create account
3. Click "New" → "Blueprint" → Connect your repo
4. Render will read `render.yaml` and create:
   - Web service (the app)
   - PostgreSQL database
5. Once deployed, you get a public URL like `https://morning-markets.onrender.com`

## Running Tests

```bash
# Start test database
docker-compose up -d

# Run all tests
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/morning_markets pytest tests/ -v
```
