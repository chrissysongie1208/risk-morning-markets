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

---

## Admin Settle on Market Page (TODO-026) - 2026-02-04

### Convenience over navigation
Instead of forcing admins to go to Admin Panel → Settle to end a market, the settle form is now available directly on the market page. This reduces clicks and lets admins settle while viewing the live orderbook/positions.

### Implementation approach
The simplest solution was adding a conditional section in `market.html`:
- Check `{% if user.is_admin %}` to show the form only to admins
- Reuse the existing `/admin/markets/{market_id}/settle` POST endpoint
- Form includes confirmation dialog to prevent accidental settlements
- Styled with a border to visually distinguish it from trading controls

### Template-only change
No backend changes needed - the settle POST endpoint already handles OPEN markets (since TODO-024). This is a pure frontend UX improvement, which keeps the change minimal and low-risk.

---

## Auto-redirect with HX-Redirect (TODO-027) - 2026-02-04

### HTMX native redirect support
HTMX supports the `HX-Redirect` response header, which triggers a full-page redirect in the browser. This is the simplest way to redirect users when a polled endpoint detects a state change.

**Implementation:**
```python
if market.status == MarketStatus.SETTLED:
    return HTMLResponse(
        content="",
        headers={"HX-Redirect": f"/markets/{market_id}/results"}
    )
```

### Why HX-Redirect over alternatives
Three approaches were considered:
1. **HX-Redirect header** (chosen) - Cleanest, HTMX-native, no JS needed
2. **Custom HTMX event + JS handler** - More complex, requires client-side code
3. **Meta refresh in HTML** - Works but less elegant, flickers

The HX-Redirect approach:
- Requires no JavaScript
- Works with existing HTMX polling
- Is a single line of code in the endpoint
- Doesn't require template changes

### Polling continues after redirect
Note that once redirected to the results page, there's no HTMX polling anymore since results are static. The redirect is a one-way transition from the live market view to the final results.

---

## Testing Combined Partial Endpoints (TODO-028) - 2026-02-04

### What to test for combined HTMX endpoints
When testing a combined partial endpoint that uses `hx-swap-oob`, verify:

1. **All sections present**: Check that the response contains all expected div IDs (e.g., `position-content`, `orderbook`, `trades`)
2. **OOB attributes**: Verify `hx-swap-oob="innerHTML"` appears on the secondary sections
3. **Data flows through**: Test that actual data (orders, positions, trades) appears in the response when present
4. **Special behaviors**: Test edge cases like the HX-Redirect header when market status changes

### Testing backward compatibility for deprecated endpoints
When deprecating but keeping old endpoints:
1. Write explicit tests for each deprecated endpoint to ensure they still return valid responses
2. Tests serve as documentation that these endpoints exist and are intentionally maintained
3. If a deprecated endpoint is removed later, the failing test reminds you to handle the migration

### Test count increased from 67 to 74
Added 7 new tests covering combined partial endpoint and backward compatibility:
- 4 tests for combined `/partials/market/{id}` endpoint
- 3 tests for deprecated individual partial endpoints (orderbook, position, trades)

---

## Testing Admin UI Features (TODO-029) - 2026-02-04

### Testing template conditionals
When testing that a template shows or hides elements based on user role:
1. Check for specific text that only appears in that element (e.g., "Admin: Settle Market")
2. Check for action URLs that are unique to that form
3. Also verify that something else IS visible (sanity check the page loaded correctly)

Example assertions:
```python
# Admin should see the form
assert "Admin: Settle Market" in content
assert 'action="/admin/markets/' in content

# Non-admin should NOT see the form
assert "Admin: Settle Market" not in content
# But should see the market itself
assert "Test market question" in content
```

### Testing HX-Redirect headers
HTMX uses the `HX-Redirect` response header to trigger client-side redirects. Test this by:
1. Setting up the state that triggers the redirect (e.g., settled market)
2. Making a request to the HTMX endpoint
3. Checking that `"HX-Redirect" in response.headers`
4. Verifying the redirect URL is correct

Note: The response status code is still 200 (not 302/303) - the redirect is handled client-side by HTMX.

### Test count increased from 74 to 80
Added 6 new tests covering admin settle form visibility and auto-redirect:
- `test_admin_sees_settle_form_on_market_page` - Admin on OPEN market sees settle form
- `test_non_admin_does_not_see_settle_form` - Participant doesn't see admin form
- `test_admin_settle_form_not_shown_on_settled_market` - Form hidden after settlement
- `test_settle_from_market_page_works` - Settle POST from market page succeeds
- `test_auto_redirect_on_settled_market` - HX-Redirect header on settled market
- `test_no_redirect_on_open_market` - No redirect header for open markets

---

## Session Exclusivity / Duplicate Login Prevention (TODO-030) - 2026-02-04

### Activity tracking approach
Session exclusivity is implemented by tracking `last_activity` timestamp on the users table:
1. **On login**: Set `last_activity` to current time
2. **On HTMX poll**: Update `last_activity` each time user polls the combined partial endpoint
3. **On login attempt**: Check if participant is claimed AND user is active (last_activity < 30s ago)

The 30-second timeout is configurable via `SESSION_ACTIVITY_TIMEOUT` in `auth.py`.

### Why track activity vs. using sessions
The in-memory session store (`_sessions` dict in auth.py) only tracks session tokens, not activity. Adding `last_activity` to the database:
- Persists across server restarts
- Works with multiple server instances (if scaling up later)
- Doesn't require managing session invalidation logic
- Is simpler than tracking "active sessions" separately

### Database migration pattern
For existing databases, PostgreSQL supports `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`:
```python
await database.execute("""
    ALTER TABLE users ADD COLUMN IF NOT EXISTS last_activity TEXT
""")
```
Wrapped in try/except for databases that don't support `IF NOT EXISTS`.

### Test behavior changes
The original `test_join_already_claimed_allows_rejoin` test assumed rejoining was always allowed. With session exclusivity, this behavior changed:
- **Old**: Second login attempt succeeds (same user rejoins)
- **New**: Second login attempt blocked if first user is active

Updated the test to reflect the new expected behavior: `test_join_already_claimed_blocks_if_active`.

### Test count increased from 80 to 85
Added 5 new tests covering session exclusivity:
- `test_active_session_blocks_new_login` - Active user blocks new login attempt
- `test_stale_session_allows_takeover` - Inactive (>30s) session allows takeover
- `test_activity_updates_on_partial_poll` - HTMX poll updates last_activity
- `test_first_login_sets_activity` - First login sets activity timestamp
- `test_unclaimed_participant_no_active_check` - Unclaimed participant has no session check

---

## Auto-Unclaim Stale Participants (TODO-031) - 2026-02-04

### Cleanup on index page load
The `cleanup_stale_participants()` function is called every time someone loads the join page (GET /). This ensures:
1. Participants whose users are inactive (>30s) are automatically released
2. The dropdown always shows accurate available participants
3. Between games, all participants auto-release with no admin intervention needed

### Implementation approach
The cleanup joins the `participants` table with `users` to check each claimed participant's user `last_activity`. Participants are unclaimed if:
- User's `last_activity` is NULL (no activity tracked)
- User's `last_activity` is older than the timeout (default 30s)

### Performance consideration
The cleanup runs on every index page load, which could be frequent. However:
- It only queries claimed participants (typically < 30 rows)
- The join is efficient with indexed tables
- The update only affects stale rows
- This avoids needing a separate background task/cron job

### Test count increased from 85 to 89
Added 4 new tests:
- `test_stale_participants_auto_unclaim_on_index` - Stale participants released on index load
- `test_active_participants_not_unclaimed_on_index` - Active participants stay claimed
- `test_cleanup_stale_participants_returns_count` - Function returns unclaim count
- `test_cleanup_stale_participants_with_no_activity` - NULL activity treated as stale

---

## UI Polish: Trade Feedback and Position Display (TODO-032) - 2026-02-04

### Trade fill detection via HTMX events
HTMX fires `htmx:afterSwap` events when content is replaced. By storing the previous position value in a `data-position` attribute and comparing after each swap, we can detect when a trade has filled:

```javascript
document.body.addEventListener('htmx:afterSwap', function(event) {
    if (event.detail.target.id !== 'position-content') return;
    const newPosition = parseInt(positionContent.dataset.position, 10);
    if (newPosition !== previousPosition) {
        // Trade happened!
        flashPosition(newPosition > previousPosition);  // green for buy, red for sell
    }
    previousPosition = newPosition;
});
```

Key insight: The `data-position` attribute is set in the Jinja template, so it survives the HTMX swap and is always current.

### Web Audio API for sounds (no files needed)
Instead of requiring an audio file, use the Web Audio API to generate simple beeps:
- Create an OscillatorNode with a sine wave
- Use 880Hz (high pitch) for buys, 440Hz (low pitch) for sells
- Short duration (150ms) with exponential decay for a pleasant "ping" sound
- No external dependencies or files to serve

Browser autoplay restriction: Audio context must be initialized after user interaction. Use `document.addEventListener('click', initAudio, { once: true })` to enable sound on first click.

### CSS animations for position flash
Use CSS `@keyframes` animations for the visual flash effect:
```css
@keyframes flash-green {
    0% { background-color: rgba(34, 197, 94, 0.4); }
    100% { background-color: transparent; }
}
.flash-buy { animation: flash-green 0.8s ease-out; }
```

To restart animation on repeated fills, force a DOM reflow:
```javascript
positionBox.classList.remove('flash-buy', 'flash-sell');
void positionBox.offsetWidth;  // Force reflow
positionBox.classList.add(isBuy ? 'flash-buy' : 'flash-sell');
```

### Hero position display
Made the position section a "hero" element with:
- Larger font (2.5rem for quantity, 1.25rem for average price)
- Card-style background using Pico CSS variables
- Color coding: green for LONG, red for SHORT, gray for FLAT
- Clear format: "+5 lots" with sign for direction

### Highlighting own orders
Added `.own-order` CSS class to orderbook rows where `order.user_id == user.id`:
- Subtle purple background (`rgba(99, 102, 241, 0.15)`)
- Bold text for own orders
- "(you)" label next to username for extra clarity

### Template consistency
When updating a partial template, update ALL versions:
- `market_all.html` (combined endpoint - primary)
- `position.html` (deprecated standalone)
- `orderbook.html` (deprecated standalone)

Even deprecated templates should stay consistent for backward compatibility.

### No test changes needed
This was a pure frontend/CSS change - no backend logic affected, so all 89 existing tests continue to pass.

---

## Configurable Timeout and Polling (TODO-033) - 2026-02-04

### Changing config values requires updating related tests
When changing a configurable value like `SESSION_ACTIVITY_TIMEOUT` from 30 to 120 seconds, tests that depend on that value may fail. Tests that used hardcoded "stale" times (e.g., 60 seconds ago) need to be updated to use the actual timeout constant:

```python
# Before - hardcoded 60 seconds
stale_time = (datetime.utcnow() - timedelta(seconds=60)).isoformat()

# After - dynamically based on config
from auth import SESSION_ACTIVITY_TIMEOUT
stale_time = (datetime.utcnow() - timedelta(seconds=SESSION_ACTIVITY_TIMEOUT + 30)).isoformat()
```

This makes tests resilient to future timeout changes.

### HTMX polling interval affects UI responsiveness
Changing polling from 1000ms to 500ms doubles the HTTP request rate but makes the UI feel more responsive:
- Orderbook updates appear faster
- Trade fills show within 0.5s instead of 1s
- Position changes are more immediate

For a small-scale app (< 30 users), the increased request rate is acceptable. For larger scale, WebSockets (TODO-034) would be better.

### Session timeout tradeoffs
The 30-second timeout was too aggressive for real users:
- Browser refreshes could log them out
- Brief network issues would cause "already in use" errors
- Users stepping away briefly would lose their session

120 seconds provides a better balance:
- Still cleans up stale sessions between games (2 min)
- Tolerates typical user interruptions
- Doesn't block other users unnecessarily long

---

## WebSocket Backend Implementation (TODO-034) - 2026-02-04

### ConnectionManager architecture
The `ConnectionManager` class in `websocket.py` tracks connected WebSocket clients per market:
- `_connections`: dict mapping `market_id` -> set of `(websocket, user_id)` tuples
- `_last_pong`: dict mapping `websocket` -> last pong timestamp for keepalive

Key methods:
- `connect()`: Accept connection, add to market set, start keepalive task
- `disconnect()`: Remove connection from tracking, clean up empty sets
- `broadcast()`: Send message to all clients for a market
- `send_personal_update()`: Send personalized update to specific user

### Personalized updates for position data
Unlike a chat app where everyone sees the same message, position data is user-specific. Each connected client receives their own view with:
- Their position highlighted
- Their orders marked with "(you)"
- Position direction based on their trades

Implementation uses `generate_market_html_for_user()` which renders the template for each user individually during broadcast.

### Broadcast trigger points
Broadcasts are called from three endpoints in `main.py`:
1. **Order placed** - after successful `matching.place_order()`
2. **Order cancelled** - after successful `matching.cancel_order()`
3. **Market settled** - after `settlement.settle_market()`

### WebSocket authentication via cookies
WebSockets don't have a straightforward Request object, but can access cookies:
```python
session_cookie = websocket.cookies.get("session")
user = await auth.get_current_user(session_cookie) if session_cookie else None
if not user:
    await websocket.close(code=4001, reason="Unauthorized")
```

Custom close codes (4001 for unauthorized, 4004 for not found) follow WebSocket protocol conventions.

### Ping/pong keepalive
The keepalive loop runs every 30 seconds:
1. Send `{"type": "ping"}` to all clients
2. Check if last pong was received within 60 seconds
3. Close stale connections that haven't responded

Clients should respond with `{"type": "pong"}` or `pong`. The `record_pong()` method updates the timestamp.

### Template rendering without Request
For WebSocket broadcasts, we don't have a full Request object. Jinja2 templates can be rendered with `request=None` if they don't use `url_for()` or other request-dependent functions. The `market_all.html` partial works fine without a request since it only uses passed variables.

### Test impact
No new tests were added for WebSocket functionality since:
1. WebSocket testing requires async test clients with WebSocket support
2. The existing 89 tests verify the core business logic still works
3. Frontend integration (TODO-035) will be the true test of the WebSocket system

The backend is ready - frontend integration in TODO-035 will complete the real-time experience.

---

## WebSocket Frontend Implementation (TODO-035) - 2026-02-04

### WebSocket client with HTMX polling fallback
The frontend WebSocket client in `market.html` attempts to connect to WebSocket first, but gracefully falls back to HTMX polling if:
- WebSocket connection fails (network error, browser doesn't support)
- Connection drops and is in reconnection phase

This hybrid approach ensures the app works in all environments while providing real-time updates when possible.

### Disabling HTMX polling dynamically
When WebSocket connects, we disable HTMX polling by removing attributes from the DOM:
```javascript
function disablePolling() {
    const positionDiv = document.getElementById('position');
    if (positionDiv) {
        positionDiv.removeAttribute('hx-trigger');
        positionDiv.removeAttribute('hx-get');
        if (typeof htmx !== 'undefined') {
            htmx.process(positionDiv); // Re-process to stop polling
        }
    }
}
```

To re-enable polling (fallback mode), we set the attributes back and call `htmx.process()` again.

### Exponential backoff for reconnection
WebSocket reconnection uses exponential backoff to avoid hammering the server:
- Initial delay: 1 second
- Doubles each attempt: 1s, 2s, 4s, 8s, 16s, 32s, 60s (capped)

The backoff counter resets when connection succeeds, so a brief network blip only costs 1 second of reconnection delay.

### DOMParser for WebSocket HTML updates
WebSocket sends pre-rendered HTML (same as HTMX partials). The client parses it with `DOMParser`:
```javascript
const parser = new DOMParser();
const doc = parser.parseFromString(html, 'text/html');

const newOrderbook = doc.getElementById('orderbook');
if (newOrderbook) {
    document.getElementById('orderbook').innerHTML = newOrderbook.innerHTML;
}
```

This approach reuses the existing server-side rendering - no need for separate JSON API or client-side templating.

### JSON messages for control events
The server sends JSON messages for non-HTML control events like redirects:
```json
{"type": "redirect", "url": "/markets/{id}/results"}
```

The client checks if the message starts with `{` and tries to parse as JSON before treating it as HTML. This allows mixing control messages with HTML updates over the same connection.

### Integration with existing trade feedback
The trade fill detection (sound + flash) from TODO-032 works with both WebSocket and HTMX:
- `checkPositionChange()` is called after every DOM update
- It compares `data-position` attribute before/after
- The same `playBeep()` and `flashPosition()` functions handle the feedback

This means trade feedback works in both WebSocket mode and fallback polling mode.

### No test changes needed
This was a frontend-only change - the backend WebSocket API was already built in TODO-034. All 89 existing tests pass since they test the HTTP/REST API and business logic, not the WebSocket functionality.
