# TODO List

## Status Key
- `[ ]` - Pending (first one is always next task)
- `[x]` - Complete and verified
- `[?]` - Blocked (see QUESTIONS.md)

---

## Completed (Phase 1 & 2)

<details>
<summary>Click to expand completed TODOs</summary>

- [x] TODO-001: Project foundation (database, models)
- [x] TODO-002: User join + session system
- [x] TODO-003: Market CRUD + admin panel
- [x] TODO-004: Matching engine + order placement
- [x] TODO-005: Position tracking + HTMX polling
- [x] TODO-006: Settlement + results
- [x] TODO-007: Leaderboard + admin config
- [x] TODO-008: Unit tests for matching engine (11 tests)
- [x] TODO-009: Unit tests for settlement (24 tests)
- [x] TODO-010: Integration tests for API (12 tests)
- [x] TODO-011: README + documentation
- [x] TODO-012: Final E2E verification
- [x] TODO-013: Fix binary P&L (per-trade calculation)
- [x] TODO-014: Migrate to PostgreSQL
- [x] TODO-015: Update tests for PostgreSQL
- [x] TODO-016: Concurrent user tests (6 tests)
- [x] TODO-017: Render.com deployment config
- [x] TODO-018: README deployment instructions
- [x] TODO-019: Deploy to production (https://risk-morning-markets.onrender.com)

</details>

---

## Phase 3: New Features

- [x] TODO-020: Anti-spoofing - Prevent users from placing bids when they have an offer at equal or higher price (and vice versa). When placing a BID at price P, reject if user has any OFFER at price <= P. When placing an OFFER at price P, reject if user has any BID at price >= P. Add validation in `matching.py` before order creation. Add test cases. Display clear error message to user.

- [x] TODO-021: Pre-registered usernames - Admin can create participant usernames in advance. Add `participants` table (id, display_name, created_by_admin, created_at). Admin panel gets new section to add/remove participant names. Join page changes from free-text input to dropdown of available names. When user selects a name, they "claim" it for that session (still no password). Historical data (positions, trades) stays linked to the participant record across sessions.

- [x] TODO-022: Add tests for anti-spoofing and pre-registered usernames - Unit tests for spoofing prevention logic, integration tests for admin creating participants, tests for dropdown join flow.

- [x] TODO-023: Remove WIN/LOSS result label - Remove the "Result" column (WIN/LOSS/BREAKEVEN) from results.html and leaderboard.html. Linear P&L and Binary P&L are sufficient. Also remove `calculate_binary_result()` from settlement.py and `binary_result` field from models if no longer needed.

- [x] TODO-024: Combine close and settle into single action - Remove separate "Close Market" button/endpoint. Admin just enters settlement value and clicks "Settle" which automatically closes AND settles in one step. Update admin.html, main.py routes, and settlement.py. Remove `/admin/markets/{id}/close` endpoint or have settle call it internally. Market goes directly from OPEN to SETTLED.

---

## Phase 3: Performance & UX Improvements

- [x] TODO-025: Combine HTMX partials into single endpoint - Create `/partials/market/{id}` that returns position, orderbook, and trades in one response. Update market.html to poll this single endpoint instead of 3 separate endpoints. Use HTMX `hx-swap-oob` or wrap sections in target divs. This reduces HTTP requests from 3/sec to 1/sec per user, reducing load on Render/Neon free tiers. Keep old endpoints for backward compatibility but mark deprecated.

- [x] TODO-026: Add settle button to market page for admin - When admin views a market page and market is OPEN, show a "Settle Market" form directly on the page (not just in Admin panel). Form has settlement value input and submit button. Non-admin users don't see this form. This lets admin settle without navigating away from the market view.

- [x] TODO-027: Auto-redirect to results when market settles - When market is SETTLED and user is on the market page, automatically redirect to results page. Implement via: (a) HTMX partial returns a redirect header/meta refresh when market.status == SETTLED, or (b) Add market status to partial response and use HTMX `hx-trigger` with custom event, or (c) Simple JS check on partial response. Choose simplest approach that works.

- [x] TODO-028: Add tests for combined partial endpoint - Test that single endpoint returns all 3 sections. Test that old endpoints still work (backward compat). Test performance improvement is measurable.

- [x] TODO-029: Add tests for admin settle on market page and auto-redirect - Test admin sees settle form, non-admin doesn't. Test settle from market page works. Test auto-redirect fires when market settles.

- [x] TODO-030: Prevent duplicate participant login (session exclusivity) - If a participant is claimed AND has an active session, reject new login attempts with "Participant already in use". Track `last_activity` timestamp per user, updated on each HTMX poll or page load. Define "active" as last_activity within 30 seconds (configurable). When user tries to join a claimed participant, check if claimed user's last_activity is recent. If yes, reject. If stale (>30s), allow takeover (auto-releases old session). Add test cases for: active user blocks new login, stale session allows takeover.

- [x] TODO-031: Auto-unclaim stale participants - On join page load (GET /), run cleanup that sets `claimed_by_user_id = NULL` for any participant whose user has been inactive >30 seconds. This makes "claimed" mean "actively in use" rather than "logged in at some point". Simplifies dropdown logic (stays `WHERE claimed_by_user_id IS NULL`). Between games, all participants auto-release after 30s of inactivity - no manual admin cleanup needed. Add `cleanup_stale_participants()` in database.py, call it in the index route before fetching available participants. Add test: participant auto-unclaims after user goes stale.

- [x] TODO-032: UI polish - trade feedback and position display. Three enhancements: (1) **Trade fill sound + flash**: Play subtle sound and flash the position box green/red when user's order fills. Detect fills by comparing position before/after in HTMX response, or include `recent_fill` flag from server. Use HTML5 Audio with a small sound file or Web Audio API. Handle browser autoplay restrictions (may need user interaction first). (2) **Bigger position display**: Make the "Your Position" section more prominent - larger font, clearer layout showing "You: +5 lots @ $47.20" as the hero element. (3) **Highlight your orders**: In the orderbook, add distinct background color to orders where `order.user_id == user.id` so users can quickly spot their own orders. Add CSS classes and update orderbook partial template.

- [x] TODO-033: Faster polling + longer session timeout - Two config changes: (1) Change HTMX polling from 1000ms to 500ms in market.html (`hx-trigger="every 500ms"`). Makes the UI feel more real-time. (2) Change `SESSION_ACTIVITY_TIMEOUT` in auth.py from 30 to 120 seconds. Gives users more buffer for browser refreshes or brief interruptions during a game.

- [x] TODO-034: WebSocket backend - Add real-time push updates via WebSocket. Create `ConnectionManager` class to track connected clients per market. Add `/ws/market/{market_id}` WebSocket endpoint in main.py. Implement `broadcast()` method to push HTML updates to all connected clients. Call broadcast when: order placed, order cancelled, trade happens, market settled. Add ping/pong keepalive (30s interval) to detect stale connections. Handle client disconnection gracefully. This replaces polling with instant updates.

- [x] TODO-035: WebSocket frontend - Replace HTMX polling with WebSocket client. Add JavaScript to market.html that: (1) Connects to `wss://[host]/ws/market/{id}` on page load. (2) Updates DOM when message received (position, orderbook, trades sections). (3) Handles reconnection with exponential backoff (1s, 2s, 4s... max 60s) on disconnect. (4) Integrates with trade sound/flash from TODO-032. (5) Falls back to polling if WebSocket fails. Remove or disable HTMX `hx-trigger` polling since WebSocket handles updates.

- [x] TODO-036: Inline forms + loading states + connection indicator. Three UX improvements: (1) **Inline form submissions**: Place order and cancel order via HTMX `hx-post` without page redirect. Show success/error as toast notification. Form stays filled on error so user doesn't lose input. Server returns appropriate headers/response for HTMX to handle. (2) **Loading states**: Add spinner to Submit/Cancel buttons while processing. Disable button to prevent double-click. Show visual feedback immediately on click so user knows action registered (especially important with 200-300ms network latency). (3) **WebSocket connection indicator**: Small status dot (green = connected, yellow = reconnecting, red = disconnected). Show near top of market page. Update on WebSocket open/close/error events. Helps user know if they're seeing live data or stale.

- [x] TODO-037: One-click trading against resting orders. Add "Trade" button on other users' orders (in place of Cancel button which shows on your own orders). Clicking Trade immediately aggresses that order - hitting offers (buy) or lifting bids (sell). Add "Click size" input field on market page (always visible, above orderbook) that sets how many lots per click. Store in localStorage so it persists. Use inline HTMX submission (no page redirect). Handle edge cases: (a) order gone before click → toast "Order no longer available", (b) partial fill → fill what's available and show "Bought 3 of 5 requested @ 47", (c) order is yours → show Cancel not Trade. Backend: new endpoint `POST /orders/{id}/aggress` that takes quantity param and creates a crossing order.

- [x] TODO-038: Price ladder orderbook layout. Replace side-by-side bid/offer columns with a vertical price ladder where both sides share the same price axis. Price increases going UP. Layout: `[Trade] Bids Qty | User | PRICE | User | Offers Qty [Trade]`. Best bid appears BELOW best offer with a visible spread gap between them - no visual "crossing". Bids on left side of price column, offers on right side. All prices sorted ascending (lowest at bottom, highest at top). Trade/Cancel buttons integrate with the new layout. This matches professional trading ladder UIs (CME, crypto exchanges). Example: offers at 50, 49 appear above the spread gap; bids at 47, 46 appear below. The gap between 47 and 49 is the spread.

---

## Bugfixes

- [x] TODO-039: BUG - Anti-spoofing rejection shows no error message. Repro: User has resting BID at 150, then places OFFER at 150. Expected: toast error "Cannot place offer at or below your bid price" (or similar). Actual: Nothing happens, no error shown, order silently rejected. Debug steps: (1) Check `matching.py` `check_spoofing()` returns correct rejection. (2) Check `main.py` `place_order()` returns `HX-Toast-Error` header on rejection. (3) Check `market.html` JS listener for `htmx:afterRequest` reads header and calls `showToast()`. (4) Write test that verifies anti-spoofing rejection returns proper error response with header. Fix the broken link in the chain.

- [x] TODO-040: BUG - Trade buttons (Buy/Sell) on orderbook don't execute trades. Repro: User A has resting OFFER at 50. User B clicks "Trade" button on that offer. Expected: Trade executes, positions update. Actual: Nothing happens. Debug steps: (1) Check `POST /orders/{id}/aggress` endpoint exists and is correct. (2) Check the Trade button form has correct `hx-post` URL and params. (3) Check the aggress endpoint calls `matching.place_order()` with correct side/price. (4) Check WebSocket broadcast happens after trade. (5) Write test for aggress endpoint that verifies trade execution. Fix the broken link in the chain.

---

## New Features

- [x] TODO-041: Fill-and-Kill option for Trade button. Add user preference (checkbox or toggle near Click Size) for "Fill and Kill" mode. When enabled: clicking Trade fills as much as possible from the target order, but does NOT create a resting order for unfilled quantity. When disabled (default): current behavior where remainder becomes a resting quote. Store preference in localStorage alongside click_size. Backend: add `fill_and_kill` param to `/orders/{id}/aggress` endpoint. If true and order can't fully fill, fill what's available and return without creating resting order. Update toast message: "Bought 3 lots @ 50 (2 unfilled, killed)".

- [x] TODO-042: Add request timing/latency logging. Help diagnose 4-5 second latency issues. (1) Backend: Add logging to key endpoints showing processing time (order placement, aggress, WebSocket broadcast). Use Python `time.perf_counter()` to measure. Log if any operation takes >500ms. (2) Frontend: Add optional debug mode that shows round-trip time for actions in console. (3) WebSocket: Log time between broadcast call and message send. This helps identify if latency is network, database, or code.

---

## Test Coverage Improvements

- [x] TODO-043: Comprehensive test audit and improvements. Current tests miss bugs that users find in UI. Add/improve tests for: (1) **Error message delivery**: Test that ALL rejection scenarios (spoofing, position limit, market closed, etc.) return proper `HX-Toast-Error` headers. (2) **Full flow integration tests**: Test complete flows like "place order → verify in orderbook → trade against it → verify positions updated → verify trade in recent trades". (3) **Edge cases**: Partial fills, order gone before aggress, self-trade attempts, concurrent trades on same order. (4) **WebSocket delivery**: Test that broadcasts actually send correct HTML to connected clients. (5) **Aggress endpoint**: Test all scenarios - full fill, partial fill, order not found, own order, fill-and-kill mode. Each test should verify the COMPLETE expected outcome, not just "no error thrown".

---

## CRITICAL - Production Issues

- [x] TODO-044: **CRITICAL** - Buy/Sell button reliability audit. Improved WebSocket broadcast to use parallel processing with asyncio.gather(). Added granular timing logs to aggress endpoint (auth, lookup, match, cancel, broadcast). Added 5 new reliability tests. See LESSONS.md for detailed analysis. **REQUIRES HUMAN VERIFICATION** - Please test in production with multiple rapid trades and report if issues persist.

---

## New Features

- [x] TODO-045: Aggregate orders at same price level in orderbook display. Currently if a user places 2 separate BUY orders at the same price (e.g., 5 lots @ 50, then 3 lots @ 50), they show as 2 separate rows. Instead, aggregate them into a single row showing combined quantity (8 lots @ 50). Only aggregate orders from the SAME user on the SAME side at the SAME price. Different users' orders at the same price should still show separately (important for queue priority visibility). Update orderbook partial template and the database query that fetches orders. Add tests: (1) Same user, same side, same price → aggregated. (2) Same user, same side, different price → separate rows. (3) Different users, same price → separate rows.

- [x] TODO-046: Queue priority display in orderbook - ensure time priority is visually clear. Orders should be displayed showing queue priority (first-in-first-out within same price level). For BIDS: the first person to bid at price X should appear at the TOP of that price level's orders. For OFFERS: the first person to offer at price X should appear at the BOTTOM of that price level's orders. This reflects actual fill priority - the matching engine uses price-time priority, so the display should match. Verify the SQL query uses `ORDER BY created_at ASC` within each price level. Update orderbook template if needed. Add test that verifies display order matches fill priority.

<!-- Add new TODOs here with sequential IDs -->

