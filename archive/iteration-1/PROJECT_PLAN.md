# Morning Markets App - Project Plan (Revised)

## 1. Core Concept

A **prediction market** web app where:
- Admin creates markets with trivia-style questions (e.g., "Weight of largest recorded polar bear in kg?")
- Users join with a display name (Kahoot-style, no passwords)
- Users place bids and offers on the order book
- Orders that cross (bid >= best offer, or offer <= best bid) automatically match
- Admin settles the market by entering the actual answer
- Users see their results as both **binary** (win/loss) and **linear** (settlement - trade price) P&L

---

## 2. Confirmed Requirements

### Functional Requirements

| Requirement | Decision |
|-------------|----------|
| **User model** | Kahoot-style: enter display name, no passwords. Reject duplicate names. |
| **Admin** | Single admin (you) with a secret passphrase to access admin features |
| **Market lifecycle** | Admin creates markets, admin settles them with actual value |
| **Order matching** | Auto-match when orders cross. Price-time priority. |
| **Position limits** | Net position limit per user (default: 20 lots). Admin can change globally. |
| **Shorting** | Yes, users can go short (negative position) up to the limit |
| **Currency** | Virtual points (no starting balance needed - positions are the score) |
| **Settlement display** | Show both binary P&L (did you profit?) and linear P&L (how much?) |

### Non-Functional Requirements

| Requirement | Decision |
|-------------|----------|
| **Scale** | Up to 20 concurrent users |
| **Real-time** | 1-second polling (WebSocket overkill for 20 users) |
| **Persistence** | SQLite database, keeps historical records |
| **Mobile** | Desktop web only (no responsive design needed) |
| **Deployment** | Local: run on your machine, others connect via `http://your-ip:8000` |

### Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Backend** | Python + FastAPI | You're comfortable with Python, FastAPI is simple |
| **Frontend** | HTML + HTMX + minimal JS | Simpler than React for this scale, HTMX handles dynamic updates |
| **Database** | SQLite | Zero setup, sufficient for 20 users, persists to file |
| **Styling** | PicoCSS or simple custom CSS | Lightweight, looks decent out of the box |

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                               │
│  HTML + HTMX + minimal JavaScript                           │
│  - Join page (enter name)                                    │
│  - Market list                                               │
│  - Market trading view (order book + trade form)            │
│  - Leaderboard / results                                     │
│  - Admin panel (create market, settle, set limits)          │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP (REST + HTMX partials)
                      │ 1-second polling for order book
┌─────────────────────▼───────────────────────────────────────┐
│                    FastAPI Backend                           │
│  - User session management (cookie-based)                   │
│  - Market CRUD (admin only for create/settle)               │
│  - Order placement + matching engine                        │
│  - Position tracking                                         │
│  - Settlement + P&L calculation                             │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                    SQLite Database                           │
│  File: data/markets.db                                       │
│  Tables: users, markets, orders, trades, positions, config  │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Data Model

```sql
-- Users (Kahoot-style, no auth)
CREATE TABLE users (
    id TEXT PRIMARY KEY,           -- UUID
    display_name TEXT UNIQUE NOT NULL,
    is_admin INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Global config (position limits, etc.)
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Initial: INSERT INTO config VALUES ('position_limit', '20');

-- Markets
CREATE TABLE markets (
    id TEXT PRIMARY KEY,           -- UUID
    question TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'OPEN',    -- OPEN | CLOSED | SETTLED
    settlement_value REAL,         -- NULL until settled
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    settled_at TEXT
);

-- Orders
CREATE TABLE orders (
    id TEXT PRIMARY KEY,           -- UUID
    market_id TEXT NOT NULL REFERENCES markets(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    side TEXT NOT NULL,            -- BID | OFFER
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    remaining_quantity INTEGER NOT NULL,
    status TEXT DEFAULT 'OPEN',    -- OPEN | FILLED | CANCELLED
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Trades (executed matches)
CREATE TABLE trades (
    id TEXT PRIMARY KEY,           -- UUID
    market_id TEXT NOT NULL REFERENCES markets(id),
    buy_order_id TEXT NOT NULL REFERENCES orders(id),
    sell_order_id TEXT NOT NULL REFERENCES orders(id),
    buyer_id TEXT NOT NULL REFERENCES users(id),
    seller_id TEXT NOT NULL REFERENCES users(id),
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Positions (aggregate per user per market)
CREATE TABLE positions (
    id TEXT PRIMARY KEY,           -- UUID
    market_id TEXT NOT NULL REFERENCES markets(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    net_quantity INTEGER DEFAULT 0,  -- positive = long, negative = short
    total_cost REAL DEFAULT 0,       -- sum of (price * qty) for buys, negative for sells
    UNIQUE(market_id, user_id)
);
```

---

## 5. API Endpoints

```
User Management
GET    /                           # Landing page - enter name to join
POST   /join                       # Set display name, get session cookie
GET    /me                         # Current user info

Markets (User)
GET    /markets                    # List all markets
GET    /markets/{id}               # Market detail + order book + trade form
POST   /markets/{id}/orders        # Place a bid or offer
DELETE /orders/{id}                # Cancel own order

Admin (requires admin passphrase)
GET    /admin                      # Admin panel
POST   /admin/login                # Verify admin passphrase
POST   /admin/markets              # Create new market
POST   /admin/markets/{id}/close   # Close market (no new orders)
POST   /admin/markets/{id}/settle  # Settle with value
POST   /admin/config               # Update position limit

Results
GET    /markets/{id}/results       # Show settlement results (binary + linear P&L)
GET    /leaderboard                # Aggregate scores across all settled markets

HTMX Partials (for dynamic updates)
GET    /partials/orderbook/{id}    # Just the order book HTML
GET    /partials/position/{id}     # Just user's position for this market
GET    /partials/trades/{id}       # Just recent trades for this market
```

---

## 5.5 HTMX Polling Pattern

For real-time updates without WebSockets, use HTMX polling. Example in `market.html`:

```html
<!-- Order book updates every 1 second -->
<div id="orderbook"
     hx-get="/partials/orderbook/{{ market.id }}"
     hx-trigger="every 1s"
     hx-swap="innerHTML">
    {% include 'partials/orderbook.html' %}
</div>

<!-- User's position updates every 1 second -->
<div id="position"
     hx-get="/partials/position/{{ market.id }}"
     hx-trigger="every 1s"
     hx-swap="innerHTML">
    {% include 'partials/position.html' %}
</div>

<!-- Recent trades updates every 1 second -->
<div id="trades"
     hx-get="/partials/trades/{{ market.id }}"
     hx-trigger="every 1s"
     hx-swap="innerHTML">
    {% include 'partials/trades.html' %}
</div>
```

Include HTMX in `base.html`:
```html
<script src="https://unpkg.com/htmx.org@1.9.10"></script>
```

---

## 6. Matching Engine Logic

When a new order arrives:

```python
def place_order(market_id, user_id, side, price, quantity):
    # 1. Validate position limit
    current_position = get_position(market_id, user_id)
    projected_position = current_position + (quantity if side == 'BID' else -quantity)
    if abs(projected_position) > get_position_limit():
        raise PositionLimitExceeded()

    # 2. Check for crossing orders
    if side == 'BID':
        # Find offers at or below my bid price (I'm willing to pay up to `price`)
        matching_offers = get_orders(market_id, 'OFFER', price_lte=price, order_by='price ASC, created_at ASC')
    else:
        # Find bids at or above my offer price (someone willing to pay at least `price`)
        matching_bids = get_orders(market_id, 'BID', price_gte=price, order_by='price DESC, created_at ASC')

    # 3. Match against crossing orders
    remaining = quantity
    for counter_order in matching_orders:
        if remaining == 0:
            break

        fill_qty = min(remaining, counter_order.remaining_quantity)
        fill_price = counter_order.price  # Price-time priority: taker gets maker's price

        create_trade(...)
        update_positions(...)
        update_order_quantities(...)

        remaining -= fill_qty

    # 4. If any quantity left, post as resting order
    if remaining > 0:
        create_order(market_id, user_id, side, price, remaining)
```

---

## 7. Settlement Logic

```python
def settle_market(market_id, settlement_value):
    market = get_market(market_id)
    market.status = 'SETTLED'
    market.settlement_value = settlement_value
    market.settled_at = now()

    # Cancel all remaining open orders
    cancel_all_orders(market_id)

    # Calculate P&L for each position
    for position in get_positions(market_id):
        if position.net_quantity == 0:
            continue

        # Linear P&L: how much did they make/lose?
        avg_price = position.total_cost / position.net_quantity if position.net_quantity != 0 else 0
        linear_pnl = position.net_quantity * (settlement_value - avg_price)

        # Binary P&L: did they profit? (1 = win, 0 = loss, 0.5 = breakeven)
        if linear_pnl > 0:
            binary_result = 'WIN'
        elif linear_pnl < 0:
            binary_result = 'LOSS'
        else:
            binary_result = 'BREAKEVEN'

        # Store results (or calculate on-the-fly when displaying)
```

---

## 8. Testing Strategy

### Unit Tests (`tests/test_matching.py`)

```python
# Matching engine tests
def test_exact_match():
    """Bid at 100 for 5 meets offer at 100 for 5 -> full fill"""

def test_partial_fill_price_match():
    """Offer at 100 for 10 meets bid at 100 for 3 -> partial fill, 7 resting"""

def test_partial_fill_price_cross():
   """Offer at 100 for 10 meets bid at 105 for 3 -> partial fill at 105 (resting quote price), 7 resting"""

def test_no_match():
    """Bid at 90 with offers at 100+ -> no fill, order rests"""

def test_price_improvement():
    """Bid at 110 meets offer at 100 -> fills at 100 (maker's price)"""

def test_multiple_fills():
    """Large bid sweeps multiple offers"""

def test_position_limit_enforced():
    """Order rejected if it would exceed position limit"""

def test_position_limit_with_existing_position():
    """Limit checked against net position after potential fill"""
```

### Unit Tests (`tests/test_settlement.py`)

```python
def test_linear_pnl_long_profit():
    """Long 10 @ avg 50, settles at 60 -> P&L = +100"""

def test_linear_pnl_long_loss():
    """Long 10 @ avg 50, settles at 40 -> P&L = -100"""

def test_linear_pnl_short_profit():
    """Short 10 @ avg 50, settles at 40 -> P&L = +100"""

def test_linear_pnl_short_loss():
    """Short 10 @ avg 50, settles at 60 -> P&L = -100"""

def test_binary_classification():
    """Verify WIN/LOSS/BREAKEVEN classification"""

def test_settlement_cancels_open_orders():
    """All open orders cancelled on settlement"""
```

### Integration Tests (`tests/test_api.py`)

```python
def test_join_flow():
    """User can join with unique name, rejected with duplicate"""

def test_full_trade_lifecycle():
    """Create market -> place orders -> match -> settle -> verify results"""

def test_admin_authentication():
    """Admin endpoints require correct passphrase"""

def test_order_cancellation():
    """User can cancel own orders, not others'"""
```

### Manual Testing Checklist

- [ ] Join as user, see markets list
- [ ] Place bid, see it in order book
- [ ] Place crossing offer from another user, verify match
- [ ] Verify position updates after trade
- [ ] Admin: create market, close it, settle it
- [ ] Verify settlement results show binary + linear P&L
- [ ] Test position limit enforcement
- [ ] Test duplicate name rejection

---

## 9. File Structure

```
morning-_markets_app/
├── CLAUDE.md                 # Agent instructions
├── PROMPT.md                 # Loop prompt
├── PROJECT_CONTEXT.md        # Requirements (generate from this plan)
├── TODO.md                   # Task tracking
├── QUESTIONS.md              # Blocking questions
├── LESSONS.md                # Accumulated knowledge
├── src/
│   ├── main.py               # FastAPI app entry point
│   ├── database.py           # SQLite setup + queries
│   ├── models.py             # Pydantic models
│   ├── matching.py           # Matching engine
│   ├── settlement.py         # Settlement logic
│   ├── auth.py               # Session + admin auth
│   └── templates/            # Jinja2 HTML templates
│       ├── base.html
│       ├── index.html        # Join page
│       ├── markets.html      # Market list
│       ├── market.html       # Trading view
│       ├── results.html      # Settlement results
│       ├── leaderboard.html
│       ├── admin.html        # Admin panel
│       └── partials/         # HTMX partial templates
│           ├── orderbook.html
│           └── position.html
├── static/
│   └── style.css             # Minimal custom styles
├── data/
│   └── markets.db            # SQLite database (gitignored)
├── tests/
│   ├── test_matching.py
│   ├── test_settlement.py
│   └── test_api.py
├── requirements.txt
├── run.sh                    # Single agent run
└── loop.sh                   # Continuous agent loop
```

---

## 10. Phased Implementation

### Phase 1: Foundation
- [ ] Set up FastAPI project structure
- [ ] Create SQLite database schema
- [ ] Implement user join flow (name entry, session cookie)
- [ ] Basic market CRUD (admin create, list all)

### Phase 2: Trading Core
- [ ] Order placement (bid/offer)
- [ ] Matching engine (cross detection, fill execution)
- [ ] Position tracking
- [ ] Order cancellation
- [ ] Position limit enforcement

### Phase 3: Settlement
- [ ] Admin settle endpoint
- [ ] Linear P&L calculation
- [ ] Binary P&L classification
- [ ] Results display page

### Phase 4: UI Polish
- [ ] Order book display with 1-second polling (HTMX)
- [ ] User's position display
- [ ] Leaderboard across all markets
- [ ] Admin panel (create, close, settle markets, set limits)

### Phase 5: Testing & Documentation
- [ ] Unit tests for matching engine
- [ ] Unit tests for settlement
- [ ] Integration tests for API
- [ ] README with setup instructions

---

## 11. Deployment (Local Network)

"Deployment target" means where the app runs. For your use case:

1. **Run on your machine**: `python src/main.py` starts server on port 8000
2. **Find your IP**: Run `hostname -I` (Linux) or `ipconfig` (Windows)
3. **Share with others**: They open `http://YOUR_IP:8000` in their browser
4. **Same network required**: Everyone must be on the same WiFi/LAN

No cloud deployment needed. The SQLite database persists to `data/markets.db`.

---

## 12. Open Items / Clarifications Needed

1. **Admin passphrase**: What should it be? (Or generate random on first run?) Users when opening should get an option to enter as admin or participant. the admin should have a username (chrson) and password (optiver).
2. **Starting a new game**: Should there be a "reset all" button, or just create new markets? Each market should be a different 'instance' and should be historically kept.
3. **Order book depth**: Show all orders, or just top N price levels? All orders.
4. **Trade history**: Show recent trades on market page? Yes, recent 10 trades.

---

**Next step**: Review this plan. Once approved, I'll generate the final `PROJECT_CONTEXT.md` with success criteria.
