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

---

## Inline Forms, Loading States, Connection Indicator (TODO-036) - 2026-02-04

### HTMX inline form submission with custom headers
Instead of returning `RedirectResponse` for form POSTs, HTMX requests can receive custom response headers that the client-side JavaScript interprets:
- `HX-Toast-Success`: Display a green success toast notification
- `HX-Toast-Error`: Display a red error toast notification

Detection of HTMX requests:
```python
def is_htmx_request(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"
```

The backend returns `HTMLResponse` with custom headers instead of redirects:
```python
if is_htmx_request(request):
    return HTMLResponse(content="", headers={"HX-Toast-Success": msg})
return RedirectResponse(...)  # Fallback for non-HTMX
```

This dual-path approach maintains backward compatibility - forms still work without JavaScript.

### Loading states with CSS and HTMX
HTMX adds the `htmx-request` class to elements during requests. Combine this with CSS to show/hide spinners:
```css
.btn-spinner { display: none; }
.htmx-request .btn-spinner { display: inline-block; }
.htmx-request .btn-text { display: none; }
```

Button disabling is handled in JavaScript:
```javascript
document.body.addEventListener('htmx:beforeRequest', function(event) {
    const button = event.detail.elt.querySelector('button[type="submit"]');
    if (button) button.disabled = true;
});
document.body.addEventListener('htmx:afterRequest', function(event) {
    const button = event.detail.elt.querySelector('button[type="submit"]');
    if (button) button.disabled = false;
});
```

### Toast notifications with auto-removal
Toast notifications use CSS animations for slide-in and fade-out:
```css
.toast {
    animation: toast-in 0.3s ease-out, toast-out 0.3s ease-in 2.7s forwards;
}
```

The second animation (toast-out) starts at 2.7s, leaving 0.3s for the fade-out before the 3-second JavaScript removal.

### WebSocket connection indicator
The connection indicator shows current status with color-coded dots:
- **Green (connected)**: WebSocket live and working
- **Green (polling)**: Fallback HTMX polling active
- **Yellow (reconnecting)**: WebSocket reconnecting with backoff
- **Red (disconnected)**: No connection

The indicator updates in `connectWebSocket()` callbacks:
```javascript
ws.onopen = function() { updateConnectionStatus('connected'); };
ws.onclose = function() { updateConnectionStatus('reconnecting'); };
```

### Form state preservation on error
On success, clear the form inputs to prepare for the next order:
```javascript
if (successMsg && event.detail.elt.id === 'order-form') {
    document.getElementById('price-input').value = '';
    document.getElementById('quantity-input').value = '';
}
```

On error, keep values so users can fix and retry without re-entering everything.

### No test changes needed
This TODO only changes:
1. Frontend templates (CSS, JS, HTML)
2. Backend response format for HTMX requests

The endpoints still return the same redirects for non-HTMX requests, so all 89 existing tests pass unchanged.

---

## One-Click Trading / Aggress Endpoint (TODO-037) - 2026-02-04

### Aggressing vs. placing crossing orders
"Aggressing" is a trading term meaning to immediately trade against a resting order. When you aggress:
- An **offer**: You place a BID at that price (buying/hitting the offer)
- A **bid**: You place an OFFER at that price (selling/lifting the bid)

The aggress endpoint is a convenience wrapper around the existing `place_order()` function - it creates the appropriate crossing order automatically.

### Capping quantity at available
When the user requests more quantity than the target order has available, the backend caps the quantity at `target_order.remaining_quantity`. This prevents creating a resting order (the user only wanted to trade against that specific order).

```python
available_qty = target_order.remaining_quantity
actual_qty = min(quantity, available_qty)
```

The success message reflects any difference: "Bought 3 of 5 requested @ 50.00"

### Click size with localStorage persistence
The click size input uses localStorage to persist across page refreshes:
```javascript
// On load: restore from localStorage
const savedSize = localStorage.getItem('clickSize');
if (savedSize) clickSizeInput.value = savedSize;

// On change: save to localStorage
clickSizeInput.addEventListener('change', function() {
    localStorage.setItem('clickSize', this.value);
});
```

### HTMX form quantity injection
The hidden quantity field in aggress forms is populated just before submission using HTMX's `htmx:beforeRequest` event:
```javascript
document.body.addEventListener('htmx:beforeRequest', function(event) {
    if (event.detail.elt.classList.contains('aggress-form')) {
        const qtyInput = event.detail.elt.querySelector('.aggress-qty');
        qtyInput.value = getClickSize();
    }
});
```

### Button labels reflect action direction
Trade buttons show "Buy" (green/primary) for hitting offers and "Sell" (contrast) for lifting bids. This makes the UI intuitive - clicking "Buy" on an offer row buys that offer.

### Test count increased from 89 to 95
Added 6 new tests:
- `test_aggress_offer_creates_buy` - Hitting an offer creates a buy
- `test_aggress_bid_creates_sell` - Lifting a bid creates a sell
- `test_aggress_own_order_rejected` - Can't trade against your own order
- `test_aggress_nonexistent_order` - Graceful handling of missing orders
- `test_aggress_filled_order` - Graceful handling of already-filled orders
- `test_aggress_partial_fill` - Quantity capped at available amount

---

## Price Ladder Orderbook Layout (TODO-038) - 2026-02-04

### Vertical price ladder vs side-by-side columns
The traditional side-by-side orderbook (bids on left, offers on right) was replaced with a professional trading ladder layout:
- **Price column in center**: All prices sorted vertically
- **Bids on left**: User info and quantity shown on left side of price
- **Offers on right**: User info and quantity shown on right side of price
- **Spread row**: Visible gap between best bid and best offer with spread value

This layout matches professional trading UIs (CME, crypto exchanges) where traders can quickly see the entire price depth and spread at a glance.

### Order display logic
- **Offers**: Displayed at top, sorted by price descending (highest at top). Template uses `offers|reverse` since offers come sorted ASC (best offer first)
- **Bids**: Displayed below spread, sorted by price descending (best bid at top). Already sorted DESC from database
- **Result**: Highest prices at top, lowest at bottom, with spread gap in between

### Template changes for layout
The orderbook section changed from a 2-column CSS grid to a single table with 5 columns:
1. `ladder-action` (left): Cancel/Sell buttons for bids
2. `ladder-bid-info`: User and quantity for bids
3. `ladder-price`: The price level (center)
4. `ladder-offer-info`: User and quantity for offers
5. `ladder-action` (right): Cancel/Buy buttons for offers

### CSS styling for visual clarity
Key styling decisions:
- **Background highlighting**: Bid rows have green tint on left, offer rows have red tint on right
- **Spread row**: Dashed borders above and below, with spread value shown
- **Color-coded buttons**: Buy buttons are green (#22c55e), Sell buttons are red (#ef4444)
- **Own order highlighting**: Purple tint (consistent with previous own-order styling)

### Test updates for new layout
When changing a template's structure, tests that assert on specific text content need updating:
```python
# Old assertions (side-by-side layout)
assert "Bids (Buy Orders)" in content
assert "Offers (Sell Orders)" in content

# New assertions (price ladder layout)
assert 'class="price-ladder"' in content
assert "ladder-bid-info" in content
assert "ladder-offer-info" in content
```

Check for structural elements rather than display text when verifying layout changes.

### Maintaining both templates
Both `market_all.html` (combined partial) and `orderbook.html` (deprecated standalone) were updated to use the price ladder layout. Even deprecated templates should stay consistent for backward compatibility.

### No test count change
This was primarily a UI/template change with test assertion updates. Total tests remain at 95.

---

## Anti-Spoofing Toast Error Bug Fix (TODO-039) - 2026-02-05

### Root cause: Event listeners attached before DOM ready
The bug was that HTMX event listeners for toast notifications were being attached to `document.body` in a script in the `<head>`, before the body element existed. This caused the event listeners to silently fail because `document.body` was `null` at the time.

```javascript
// BUG: This runs in <head> before document.body exists
document.body.addEventListener('htmx:afterRequest', function(event) {
    // Never fires because listener wasn't attached
});
```

### The fix: Defer event handler setup to DOMContentLoaded
Wrap event handler setup in a function and call it after DOM is ready:

```javascript
function setupHTMXEventHandlers() {
    document.body.addEventListener('htmx:afterRequest', function(event) {
        // Now this works correctly
    });
}

// Call after DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupHTMXEventHandlers);
} else {
    setupHTMXEventHandlers();
}
```

### Testing strategy for frontend bugs
When debugging a bug where the backend works but the frontend doesn't show the result:
1. **Write backend tests first** - Verify the API returns correct headers/response
2. **Check event timing** - Scripts in `<head>` run before `<body>` exists
3. **Check if listeners are attached** - Events can't fire if listeners aren't registered
4. **Add console logging temporarily** - Help trace the execution flow

### Test count increased from 95 to 97
Added 2 new tests:
- `test_anti_spoofing_rejection_returns_error_toast` - HTMX request returns HX-Toast-Error header
- `test_anti_spoofing_rejection_non_htmx_returns_redirect` - Regular form submission redirects with error

---

## Trade Button Bug Fix - WebSocket DOM Updates (TODO-040) - 2026-02-05

### Root cause: HTMX elements not re-processed after WebSocket DOM update
When WebSocket updates the orderbook via `innerHTML`, the new HTMX elements (forms with `hx-post`) were not being processed by HTMX. The HTMX library needs to scan new elements to attach event handlers and configure behaviors.

```javascript
// BUG: New elements have hx-post but HTMX doesn't know about them
orderbookTarget.innerHTML = newOrderbook.innerHTML;
// Form submissions do nothing because HTMX hasn't processed them
```

### The fix: Call htmx.process() after innerHTML update
After updating DOM with new content, call `htmx.process()` on the container element:

```javascript
orderbookTarget.innerHTML = newOrderbook.innerHTML;
// Re-process HTMX attributes on newly added elements (forms, buttons)
if (typeof htmx !== 'undefined') {
    htmx.process(orderbookTarget);
}
```

### Key insight: HTMX only processes elements once
HTMX processes elements on initial page load or when explicitly told to via `htmx.process()`. When you manually update DOM (via WebSocket, JavaScript, etc.), you must:
1. Update the innerHTML or appendChild
2. Call `htmx.process(containerElement)` to initialize HTMX behaviors

This is different from HTMX's own swapping mechanism (`hx-swap-oob`) which automatically processes new content.

### Testing strategy for HTMX bugs
When HTMX forms/buttons don't work after dynamic DOM updates:
1. **Check if htmx.process() is called** - Required after manual DOM manipulation
2. **Verify backend works** - Write tests with `HX-Request: true` header to confirm response format
3. **Check browser console** - No errors usually means HTMX just doesn't know about the elements

### Test count increased from 97 to 98
Added 1 new test:
- `test_aggress_htmx_returns_toast_success` - Verifies aggress endpoint returns HX-Toast-Success header for HTMX requests

---

## Fill-and-Kill Order Type (TODO-041) - 2026-02-05

### What is Fill-and-Kill?
Fill-and-Kill (F&K) is an order execution mode where any unfilled portion of an order is automatically cancelled (killed) rather than becoming a resting order in the book. This is useful for traders who only want to trade against specific visible liquidity without inadvertently creating new orders.

### Implementation approach
The F&K feature was added to the aggress endpoint (one-click trading):
1. **Backend**: Added `fill_and_kill: bool = Form(False)` parameter to `/orders/{id}/aggress`
2. **Frontend**: Added checkbox toggle with localStorage persistence
3. **Forms**: Added hidden `fill_and_kill` field to aggress forms, populated via JS before submission

### Handling unfilled remainder
When `fill_and_kill=true` and the order has a resting portion after matching:
```python
if fill_and_kill and result.order and result.order.remaining_quantity > 0:
    unfilled_qty = result.order.remaining_quantity
    await matching.cancel_order(result.order.id, user.id)
```

The message is updated to show what was killed:
- `"Bought 3 of 5 requested @ 50.00 (2 killed)"` for partial fills with remainder cancelled

### Aggress endpoint quantity capping
The aggress endpoint caps requested quantity at the target order's available quantity BEFORE calling `place_order`:
```python
available_qty = target_order.remaining_quantity
actual_qty = min(quantity, available_qty)
```

This means F&K primarily affects cases where:
1. The matching engine partially fills due to position limits during matching
2. The user requests more than available (capped, so no resting order anyway)

### localStorage persistence for user preferences
Both click size and fill-and-kill preference are persisted in localStorage:
```javascript
// Save on change
toggle.addEventListener('change', function() {
    localStorage.setItem('fillAndKill', this.checked ? 'true' : 'false');
});

// Load on page init
const savedValue = localStorage.getItem('fillAndKill');
if (savedValue === 'true') {
    toggle.checked = true;
}
```

### Test count increased from 98 to 102
Added 4 new tests:
- `test_fill_and_kill_cancels_unfilled_remainder` - F&K with full fill works
- `test_fill_and_kill_message_shows_requested_vs_filled` - Message shows requested vs filled amounts
- `test_fill_and_kill_false_creates_resting_order` - F&K off doesn't say "killed"
- `test_fill_and_kill_default_is_false` - Default behavior is unchanged

---

## Request Timing / Latency Logging (TODO-042) - 2026-02-05

### Multi-layer timing approach
To diagnose latency issues effectively, instrument timing at multiple layers:

1. **HTTP middleware**: Catches all request timing, adds `X-Process-Time-Ms` header
2. **Endpoint-specific timing**: Breaks down into matching engine vs broadcast time
3. **WebSocket layer**: Tracks time to send messages to each client
4. **Frontend debug mode**: Measures round-trip time visible to the user

This layered approach helps identify WHERE latency occurs (network, database, code, etc.).

### FastAPI middleware for request timing
Use `@app.middleware("http")` to wrap all requests with timing:

```python
@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time-Ms"] = f"{process_time * 1000:.2f}"
    return response
```

### Logging slow operations vs all operations
Use different log levels for different purposes:
- `logger.warning()` for slow operations (>500ms threshold) - always visible
- `logger.info()` for operation breakdowns (match time, broadcast time)
- `logger.debug()` for routine request timing - only visible when debug enabled

This keeps logs clean while still capturing important slow operation warnings.

### Frontend debug mode with localStorage
Make debug timing opt-in to avoid console spam:

```javascript
let debugTimingEnabled = localStorage.getItem('debugTiming') === 'true';

window.enableDebugTiming = function(enabled) {
    debugTimingEnabled = enabled;
    localStorage.setItem('debugTiming', enabled ? 'true' : 'false');
};

function logTiming(operation, startTime, details) {
    if (!debugTimingEnabled) return;
    const elapsed = performance.now() - startTime;
    console.log('[TIMING] ' + operation + ': ' + elapsed.toFixed(1) + 'ms', details);
}
```

Users can enable with `window.enableDebugTiming(true)` in browser console.

### Correlating frontend and backend timing
The `X-Process-Time-Ms` header in the response tells the frontend how long the server took. Combined with frontend round-trip measurement, you can calculate:
- **Server time**: from header
- **Network time**: round-trip minus server time

This helps distinguish between slow server and slow network issues.

### No test count change
This was an observability/logging feature with no new tests needed. All 102 existing tests pass unchanged.

---

## Comprehensive Test Coverage Improvements (TODO-043) - 2026-02-05

### Testing error message delivery (HX-Toast headers)
Tests should verify that ALL rejection scenarios return proper `HX-Toast-Error` headers for HTMX requests. Create explicit tests for each scenario:
- Position limit exceeded
- Market closed/not open
- Invalid order side/price/quantity
- Cancel non-existent order
- Cancel other user's order
- Aggress with zero quantity
- Session expired

Each test should:
1. Set up the rejection condition
2. Make request with `headers={"HX-Request": "true"}`
3. Assert `response.status_code == 200` (not 4xx)
4. Assert `"HX-Toast-Error" in response.headers`
5. Assert the error message contains relevant keywords

### Full flow integration tests
Test complete user flows, not just individual endpoints:
1. **Place order → verify in orderbook**: Assert order appears with correct price/quantity
2. **Aggress → verify trade**: Assert trade shows correct buyer/seller IDs
3. **Trade → verify positions**: Assert positions updated correctly (buyer +qty, seller -qty)
4. **Settlement → verify P&L**: Assert P&L calculations are correct and zero-sum

Key insight: Get user IDs from database objects (orders, trades) rather than looking up by name, which can fail when multiple tests create users with similar names.

### Concurrent access tests document known limitations
For concurrent tests where race conditions are expected (e.g., two users aggressing same order simultaneously):
1. **Document the limitation** in the test docstring
2. **Test for safety**, not perfect behavior (system doesn't crash, no HTTP errors)
3. **Assert what IS guaranteed** (at least some trades happen, requests complete)
4. **Log outcomes** for visibility into race condition behavior
5. **Don't assert impossible guarantees** (e.g., total filled <= available without DB locking)

### Test isolation issues
When tests look up users/orders by name, they can fail if multiple tests run in sequence and create entities with overlapping names. Solutions:
1. Use IDs directly from created objects: `order.user_id` instead of `get_user_by_name("Seller")`
2. Use unique names per test: `f"UniqueTestName_{test_function_name}"`
3. Trust database cleanup between tests (TRUNCATE CASCADE)

### Test count increased from 102 to 118
Added 16 new tests covering:
- 9 error message delivery tests (position limit, market closed, invalid inputs, cancel scenarios, aggress scenarios, session expired)
- 2 full flow integration tests (order→trade→verify, multiple trades→settlement→P&L)
- 5 edge case tests (concurrent aggress, aggress on closed market, cancel already cancelled, session expired for different endpoints)

---

## Buy/Sell Button Reliability Audit (TODO-044) - 2026-02-05

### Root causes of potential latency issues identified:

1. **Sequential WebSocket broadcasts**: Previously, when broadcasting updates to all connected clients, the server was sending HTML to each client one at a time. For N clients, this was O(N) sequential network operations.

2. **HTML generation per user**: Each connected WebSocket client receives personalized HTML (their own position highlighted, their own orders marked). This requires a full render per user, including database queries for orderbook, trades, and positions.

3. **Missing detailed timing logs**: While basic timing middleware existed, the aggress endpoint didn't log granular breakdown of where time was spent (auth, order lookup, matching, broadcast).

### Improvements implemented:

1. **Parallel broadcast processing**: Changed `broadcast_market_update()` to use `asyncio.gather()` for sending updates to all clients in parallel instead of sequentially. This reduces broadcast time from O(N) to O(1) (wall clock time).

2. **Granular timing in aggress endpoint**: Added timing logs for each step:
   - `auth_time`: Time to validate session cookie
   - `order_lookup_time`: Time to fetch target order from database
   - `match_time`: Time for matching engine to process order
   - `cancel_time`: Time for F&K cancellation (if applicable)
   - `broadcast_time`: Time to send WebSocket updates

3. **Better error logging in WebSocket manager**: Added detailed warning logs when:
   - Connection state is not CONNECTED
   - Send operations fail
   - Broadcasts have failures

### Key insight: Parallel async operations

When broadcasting to multiple WebSocket clients, using `asyncio.gather()` allows all send operations to happen concurrently:

```python
# Before (sequential)
for websocket, user_id in connections:
    await ws_manager.send_personal_update(market_id, user_id, html)

# After (parallel)
tasks = [send_to_client(ws, uid) for ws, uid in connections]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

This is crucial for real-time trading apps where multiple users need updates simultaneously.

### Diagnosing latency with logs

The timing logs now show a complete breakdown:
```
aggress_order: auth=1.2ms, lookup=3.5ms, match=15.8ms, cancel=0.0ms, broadcast=45.2ms, total=65.7ms, trades=1, user=Alice
```

If any operation exceeds 500ms, a separate WARNING is logged:
```
SLOW aggress_order: 850.3ms (auth=1.1, lookup=503.2, match=12.4, broadcast=333.6)
```

This helps identify whether slowness is in the database (lookup), matching engine, or network (broadcast).

### Test count increased from 118 to 123
Added 5 new reliability tests:
- `test_aggress_rapid_trades_succeed` - 5 rapid successive trades all succeed
- `test_aggress_response_contains_toast_header` - Every response has HX-Toast header
- `test_aggress_returns_timing_header` - X-Process-Time-Ms header present and reasonable
- `test_aggress_completes_trade_end_to_end` - Full flow verification (aggress→trade→positions)
- `test_aggress_with_fill_and_kill_shows_killed` - F&K message format correct

---

## Order Aggregation in Orderbook Display (TODO-045) - 2026-02-05

### Template-side aggregation, not database-side
Order aggregation was implemented in the Jinja2 template rather than in the database query. This approach has several benefits:
1. **Individual orders remain accessible**: The Trade/Cancel buttons need to reference specific order IDs. Aggregating at the database level would lose this information.
2. **Preserves queue priority**: The first order in a price level is still tracked (`first_order`) so the button targets the order with highest time priority.
3. **Simpler implementation**: No SQL GROUP BY complexity or additional models needed.

### Jinja2 dictionary aggregation pattern
To aggregate orders by (user_id, price) in Jinja2:

```jinja2
{% set aggregated = {} %}
{% for order in orders %}
    {% set key = (order.user_id, order.price) %}
    {% if key not in aggregated %}
        {% set _ = aggregated.update({key: {'first_order': order, 'total_qty': order.remaining_quantity}}) %}
    {% else %}
        {% set _ = aggregated[key].update({'total_qty': aggregated[key]['total_qty'] + order.remaining_quantity}) %}
    {% endif %}
{% endfor %}
{% set rows = aggregated.values()|list|sort(attribute='first_order.price', reverse=true) %}
```

Key points:
- Use `{% set _ = dict.update(...) %}` to mutate dictionaries in Jinja2 (the `_` captures the None return value)
- Convert to list and sort for display order
- Access nested attributes with `attribute='first_order.price'` in sort filter

### Test pitfall: Admin login replaces participant session
When a test needs both admin actions (create market) and participant actions (place orders), be careful about session management:

**Wrong**: Join as participant, then login as admin, then place orders → orders are placed as admin user, not participant!

**Right**: Use separate client contexts for admin setup vs participant trading:
```python
# Admin creates market in its own context
async with AsyncClient(...) as admin:
    await admin.post("/admin/login", ...)
    await admin.post("/admin/markets", ...)

# Participants trade in separate contexts (no admin login)
async with AsyncClient(...) as trader1:
    await trader1.post("/join", ...)
    await trader1.post("/orders", ...)
```

### Test count increased from 123 to 126
Added 3 new tests:
- `test_orderbook_aggregates_same_user_same_price` - Same user + same price = aggregated qty
- `test_orderbook_same_user_different_prices_separate_rows` - Different prices stay separate
- `test_orderbook_different_users_same_price_separate_rows` - Different users stay separate

---

## Queue Priority Display in Orderbook (TODO-046) - 2026-02-05

### Visual display should match fill priority
The matching engine uses price-time priority: within the same price level, the first order placed gets filled first. The orderbook display should reflect this so traders know their queue position.

For a price ladder layout:
- **BIDS**: First-to-bid appears at TOP of that price level (closer to spread = first to be filled)
- **OFFERS**: First-to-offer appears at BOTTOM of that price level (closer to spread = first to be filled)

This is because the spread gap separates bids and offers, and being "closer to spread" visually indicates higher fill priority.

### Jinja2 stable sort for multi-key ordering
Jinja2's `sort` filter is stable, meaning equal elements maintain their relative order. To achieve multi-key sorting (like SQL's `ORDER BY price DESC, created_at ASC`), apply sorts in reverse priority order:

```jinja2
{# For bids: sort by created_at ASC first, then by price DESC #}
{# The second sort (price) is stable, preserving created_at order within same price #}
{% set bid_rows = data|sort(attribute='created_at')|sort(attribute='price', reverse=true) %}

{# For offers: sort by created_at DESC first, then by price DESC #}
{% set offer_rows = data|sort(attribute='created_at', reverse=true)|sort(attribute='price', reverse=true) %}
```

Key insight: The **last** sort applied is the primary sort key. Earlier sorts establish the tie-breaking order for equal primary keys.

### Database query already provides correct order
The `get_open_orders()` function in `database.py` already sorts by `created_at ASC` within each price level:
```python
# ORDER BY price DESC, created_at ASC  (for bids)
# ORDER BY price ASC, created_at ASC   (for offers)
```

The issue was in the template aggregation logic, which was only sorting by price after aggregation, losing the time priority information within price levels.

### Test count increased from 126 to 129
Added 3 new tests:
- `test_queue_priority_bids_first_bidder_at_top` - First bidder at same price appears first in HTML
- `test_queue_priority_offers_first_offerer_at_bottom` - First offerer at same price appears last in HTML (bottom of price level)
- `test_queue_priority_matches_fill_order` - Verifies that the first bidder actually gets filled first (matching engine confirmation)
