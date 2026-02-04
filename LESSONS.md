# Lessons Learned

Key learnings from building this app. Read before starting work.

---

## Database & PostgreSQL

### PostgreSQL with databases library
The `databases` library uses `:param` syntax for named parameters (not `?` like SQLite).
```python
await db.execute("SELECT * FROM users WHERE id = :id", {"id": user_id})
```
Use `ON CONFLICT (key) DO NOTHING` instead of SQLite's `INSERT OR IGNORE`.

### Foreign key constraints are strict
PostgreSQL enforces FK constraints strictly. When creating trades, the order must exist first. The matching engine creates the incoming order before matching, then updates remaining_quantity after.

### Database lifecycle
```python
# In FastAPI lifespan
await db.connect_db()   # startup
await db.disconnect_db() # shutdown
```

---

## Matching Engine

### Position limits include open orders
Position limit check must account for ALL open orders (resting orders), not just filled position. Otherwise users could place unlimited resting orders.

### Trade cost tracking
Positions track `total_cost = sum(price * quantity)`. Buyer adds cost, seller subtracts. Average price = `total_cost / net_quantity`. Works for both long and short positions.

### Self-trade prevention
When matching, exclude the user's own orders from the counter-orders list.

### Anti-spoofing (TODO-020) - 2026-02-04
Anti-spoofing prevents users from placing orders that would cross their own resting orders:
- BID at price P: reject if user has any OFFER at price <= P
- OFFER at price P: reject if user has any BID at price >= P

Implementation adds `check_spoofing()` in `matching.py` that queries user's own orders and checks for crossing prices. This runs BEFORE order creation (not during matching) so no partial order is created if rejected.

Key insight: This supersedes the old self-trade prevention behavior where crossing orders were allowed but just didn't match. Now crossing orders are outright rejected, which is cleaner and prevents market manipulation.

---

## P&L Calculation

### Linear P&L
```python
linear_pnl = net_quantity * (settlement_value - avg_price)
```
For flat positions (net_quantity = 0), use `-total_cost`.

### Binary P&L (per-trade)
For each trade:
- BUY: `+quantity` if settlement > price, else `-quantity`
- SELL: `+quantity` if settlement < price, else `-quantity`

Sum across all user's trades.

---

## Testing

### Test isolation with PostgreSQL
Use `TRUNCATE TABLE tablename CASCADE` to clear tables between tests. Re-initialize config after truncation.

### Concurrent testing
Use `asyncio.gather(*tasks)` with separate `AsyncClient` instances per simulated user.

### URL encoding in redirects
Spaces become `+` or `%20` in redirect URLs. Check for both when asserting.

---

## HTMX & Frontend

### Partial templates
Create partials in `templates/partials/` for HTMX polling. Use `hx-get` with `hx-trigger="every 1s"`.

### Partial endpoints return HTML, not redirects
Unlike form POSTs, HTMX partial endpoints should return HTML fragments directly.

---

## Deployment

### Auto-deploy on push
`git push origin main` triggers Render auto-deploy (~2-3 min).

### Neon PostgreSQL
Free tier, no 90-day expiry like Render's database. Connection string in Render env vars.

### Cold starts
After 15 min idle, first request takes ~30 seconds. Hit the URL before game starts to warm it up.

---

## Pre-registered Participants (TODO-021) - 2026-02-04

### Design decision: Participants table separate from Users
The `participants` table holds pre-registered names created by admin. When a user joins by selecting a participant name:
1. A `User` record is created (if needed) for that display_name
2. The participant's `claimed_by_user_id` links to that user
3. Historical data (positions, trades) stays linked to the user record

This allows:
- Same user to rejoin if they refresh/close browser (participant stays claimed)
- Admin to release a participant to make it available again
- Users to retain their trading history across sessions

### Join flow changed: dropdown instead of free-text
The `/join` endpoint now takes `participant_id` (UUID) instead of `display_name` (text). This prevents:
- Users creating arbitrary names
- Name collision issues
- Typos in display names

### Test updates required
When changing the join API, ALL tests that use `/join` must be updated. This includes:
- test_api.py (direct join tests)
- test_concurrent.py (concurrent user simulations)
- Any fixture that creates a "participant_client"

Create a helper function `create_participant_and_get_id(name)` to streamline test setup.

---

## Test Coverage for New Features (TODO-022) - 2026-02-04

### Anti-spoofing tests already existed
The anti-spoofing tests were added as part of TODO-020 in `test_matching.py`. They cover:
- Bid crossing own offer at same/lower price
- Offer crossing own bid at same/higher price
- Valid non-crossing orders are accepted
- Spoofing check only affects user's own orders

### Pre-registered participants integration tests
Added 9 new tests to `test_api.py` covering the participant admin flow:
- Join with invalid/non-existent participant ID returns error
- Join with whitespace-only ID returns error (after strip)
- Admin can create participants
- Admin cannot create duplicate participants
- Admin can delete unclaimed participants
- Admin cannot delete claimed participants
- Admin can release claimed participants
- Only unclaimed participants appear in available list
- Non-admin cannot create participants (403)

### Test count increased from 60 to 69
Total test breakdown: 21 API tests, 6 concurrent tests, 18 matching tests, 24 settlement tests.
