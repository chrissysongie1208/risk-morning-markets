# Lessons Learned

Key learnings from building this app. Read before starting work.

> **Note**: This file is cumulative across iterations. See `archive/iteration-N/` for historical TODO.md, PROJECT_CONTEXT.md, and QUESTIONS.md from each iteration.

---

## Iteration 1 (Feb 3-4): Initial Build

Built the complete prediction market app from scratch:
- SQLite → PostgreSQL migration
- Matching engine with price-time priority
- P&L calculation (linear + binary)
- HTMX real-time updates
- Deployed to Render + Neon

**43 detailed lessons documented** - see `archive/iteration-1/LESSONS.md` for the full sequential record.

Key highlights:
- LESSON-031: Create orders before trades for FK constraints in PostgreSQL
- LESSON-036: Race conditions without database locking (acceptable for 20 users)
- LESSON-041: Cloud deployment requires human interaction - mark blocked
- LESSON-043: Git credential conflicts - embed username in remote URL

---

## Iteration 2 (Feb 4+): Feature Updates

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

---

## Removing Features Cleanly (TODO-023) - 2026-02-04

### Binary result (WIN/LOSS/BREAKEVEN) removed
The `BinaryResult` enum and `calculate_binary_result()` function were removed because:
1. Linear P&L already shows who made/lost money
2. Binary P&L (lots won/lost) provides more nuance than simple WIN/LOSS
3. The WIN/LOSS label was redundant - if linear_pnl > 0, you won

### Cleanup checklist for feature removal
When removing a feature, update all these places:
1. **Templates** (`results.html`, `leaderboard.html`) - remove columns
2. **Models** (`models.py`) - remove fields from response models
3. **Business logic** (`settlement.py`) - remove function and usages
4. **Imports** - remove unused imports (BinaryResult)
5. **Tests** - remove tests for removed function, update assertions that used the field

### Test count dropped from 69 to 66
Removed 3 tests for `calculate_binary_result()`. All remaining 66 tests pass.

---

## Combining Close and Settle (TODO-024) - 2026-02-04

### Simplifying the admin workflow
The old flow required two steps: Close Market → Settle Market. This was unnecessary complexity since:
1. The `settle_market()` function already cancels all open orders before settling
2. Admins don't need a "CLOSED" intermediate state - they just want to end the market with a settlement value

### Implementation approach
Rather than creating a new combined endpoint, the existing infrastructure already supported this:
- `settlement.settle_market()` calls `db.cancel_all_market_orders()` before settling
- The settle POST endpoint only rejected SETTLED markets (not OPEN ones)
- Only the UI prevented settling OPEN markets

**Changes made:**
1. **admin.html**: Replaced "Close" button with "Settle" link for OPEN markets
2. **settle.html**: Added note explaining that settling auto-closes the market
3. **main.py**: Updated settle GET endpoint to redirect SETTLED markets to results, allowing OPEN/CLOSED
4. **Kept `/admin/markets/{id}/close` endpoint** for backward compatibility (existing tests use it)

### Test count increased to 67
Added `test_settle_open_market_cancels_orders` to verify OPEN markets can be settled directly and open orders are cancelled.

---

## HTMX OOB Swaps for Combined Updates (TODO-025) - 2026-02-04

### Reducing HTTP requests with hx-swap-oob
HTMX's Out-of-Band (OOB) swap feature allows a single response to update multiple DOM elements. Instead of 3 separate polling endpoints (position, orderbook, trades), we now use one combined endpoint that returns all sections.

**How it works:**
1. The position div is the "primary target" with `hx-get="/partials/market/{id}"` and `hx-trigger="every 1s"`
2. The response includes orderbook and trades divs with `hx-swap-oob="innerHTML"` attribute
3. HTMX recognizes these OOB elements and swaps them into their target locations by ID

**Template structure:**
```html
{# Primary content - goes to hx-target #}
<div id="position-content">...</div>

{# OOB swaps - automatically placed by ID #}
<div id="orderbook" hx-swap-oob="innerHTML">...</div>
<div id="trades" hx-swap-oob="innerHTML">...</div>
```

### Key insight: nesting wrapper div
The primary target div needs a wrapper to work correctly:
- `market.html` has `<div id="position" hx-target="#position-content">` containing `<div id="position-content">`
- The response replaces the inner `position-content` div
- This prevents the polling attributes from being overwritten

### Backward compatibility
Old endpoints (`/partials/orderbook`, `/partials/position`, `/partials/trades`) are kept but marked deprecated. This allows gradual migration if any external tools depend on them.
