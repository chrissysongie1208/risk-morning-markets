# Morning Markets - Project Context

## What This Is

An internal prediction market web app for morning market "games" where:
- Admin creates markets with trivia questions (e.g., "Weight of largest polar bear in kg?")
- Participants join with display names (Kahoot-style, no passwords)
- Users place bids/offers that auto-match when crossing
- Admin settles markets with the actual answer
- Results show linear P&L (dollar amount) and binary P&L (lots won/lost)

**Live**: https://risk-morning-markets.onrender.com
**Users**: <20 concurrent (internal team use)

---

## Tech Stack

| Component | Choice |
|-----------|--------|
| Backend | Python 3.10+ / FastAPI |
| Frontend | HTML + Jinja2 + HTMX (1s polling) |
| Database | Neon PostgreSQL (free, no expiry) |
| Hosting | Render.com (free tier) |
| Tests | pytest + httpx (53 tests) |

---

## Current Features

- [x] Kahoot-style participant joining (display name only)
- [x] Admin login (chrson/optiver)
- [x] Create/close/settle markets
- [x] Order book with bids/offers
- [x] Auto-matching engine (price-time priority)
- [x] Position limits (default 20, admin configurable)
- [x] Self-trade prevention
- [x] Linear P&L calculation
- [x] Binary P&L (per-trade lots won/lost)
- [x] Leaderboard (aggregate across markets)
- [x] Real-time updates (1s HTMX polling)

---

## Database Schema

```sql
users (id, display_name, is_admin, created_at)
markets (id, question, description, status, settlement_value, created_at, settled_at)
orders (id, market_id, user_id, side, price, quantity, remaining_quantity, status, created_at)
trades (id, market_id, buy_order_id, sell_order_id, buyer_id, seller_id, price, quantity, created_at)
positions (id, market_id, user_id, net_quantity, total_cost)
config (key, value)
```

---

## Key Constraints

- **Admin**: chrson/optiver
- **Position limit**: Default 20 lots (configurable)
- **Matching**: Price-time priority, taker gets maker's price
- **Shorting**: Allowed up to position limit

---

## Adding New Features

1. Add TODO to `TODO.md`
2. Implement in `src/`
3. Add tests in `tests/`
4. Run tests: `pytest tests/ -v`
5. Push: `git push` (auto-deploys)

When adding database changes:
- Update schema in `database.py` `init_db()`
- The app auto-creates tables on startup

---

## Known Issues & Improvement Ideas

Things noticed but not yet addressed. **If you notice something, add it here!**

### Performance
- [ ] N+1 queries in orderbook rendering (fetches user for each order separately)
- [ ] WebSocket broadcasts regenerate HTML for each connected client
- [ ] No database connection pooling optimization

### UX
- [ ] No mobile-responsive design
- [ ] No keyboard shortcuts for trading
- [ ] No dark mode

### Testing
- [ ] No browser automation tests (Playwright/Selenium) - only AsyncClient
- [ ] No load testing for concurrent users
- [ ] Race conditions between WebSocket and user clicks not tested

### Code Quality
- [ ] Some duplication between `market_detail()` and `partial_market_all()`
- [ ] Logging is basic - could use structured logging (JSON)
- [ ] No error monitoring integration (Sentry, etc.)

### Architecture
- [ ] Aggress creates intermediate order before matching (causes UI flicker)
- [ ] Session storage is in-memory (won't scale past single dyno)

**Pick any of these up, or add your own observations!**
