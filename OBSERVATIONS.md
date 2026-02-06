# Observations

A scratchpad for thoughts during investigation. Not everything needs to be a TODO yet.

---

## Format

```
### [DATE] - [TOPIC]
**Observation**: What did you notice?
**Hypothesis**: What might be causing it?
**Evidence needed**: How would you confirm/reject?
**Possible TODO?**: Should this become a task?
```

---

## Observations

### 2026-02-06 - WebSocket Not Working in Production
**Observation**: Render logs show "No supported WebSocket library detected" and `/ws/market/...` returns 404. App falls back to "Polling" mode with 9+ second response times.
**Hypothesis**: `requirements.txt` had `uvicorn>=0.24.0` but needs `uvicorn[standard]>=0.24.0` for websockets support.
**Evidence needed**: After deploying fix, check if connection indicator shows "Live" instead of "Polling".
**Action taken**: Fixed requirements.txt, deployed. This may also fix Buy/Sell buttons if the slow polling was causing race conditions.

### 2026-02-06 - Buy/Sell Button Investigation
**Observation**: HTMX debug logs not appearing in browser console after deployment.
**Hypothesis**: Either (1) deployment not complete, (2) need hard refresh, or (3) JavaScript error preventing execution.
**Evidence needed**: Hard refresh (Ctrl+Shift+R), check for JS errors in console, verify `[HTMX DEBUG]` messages appear on any form submission.

### 2026-02-06 - Code Verification for TODO-049/050 Fixes
**Agent verification** (cannot access production due to proxy):
1. **requirements.txt**: Confirmed `uvicorn[standard]>=0.24.0` is present (TODO-049 fix)
2. **market.html**: Confirmed `attachAggressHandlers()` is called in `htmx:afterSwap` handler at line 516 (TODO-050 fix)
3. **All 129 tests pass** locally

**What human should verify in production**:
1. Connection indicator shows "Live" (not "Polling") - indicates WebSocket is working
2. Buy/Sell buttons work reliably (>95% success rate)
3. Check browser console for `[AGGRESS]` logs when clicking buttons
4. Check browser console for any JavaScript errors
5. If issues persist, check Render logs for WebSocket errors

**Git status**: All fixes committed and pushed (68dcc9a, 296e2e4)

### 2026-02-06 - N+1 Query Fix Verification (TODO-053)
**Observation**: Agent run verified the N+1 fix code is correctly deployed:
- `get_open_orders_with_users()` at `database.py:457` - single JOIN query for orderbook
- `get_recent_trades_with_users()` at `database.py:606` - single JOIN query for trades
- `main.py` uses these at lines 1154-1155, 1189, 1385-1386, 1420
- Latest commit `6efdc03` is `perf: Fix N+1 database queries`

**What human should verify in production**:
1. Check Render logs: `/partials/market/...` timing should be **<500ms** (was 9+ seconds)
2. Check Render logs: `/orders/.../aggress` timing should be **<500ms** (was 2.6-3.5 seconds)
3. GUI should feel responsive - updates within ~500ms, not 4-5 second delays
4. If still slow after N+1 fix, the issue is Neon database latency (investigate connection pooling or upgrade plan)

**Git status**: N+1 fix committed and pushed in `6efdc03`

### 2026-02-06 - Human Couldn't See Console Logs (Q-001 Follow-up)
**Observation**: Human answered Q-001 saying they "can't see it in Console tab"
**Investigation**:
- Verified code has correct console.log statements (grep found 8 `[AGGRESS]` logs)
- The issue is the logs only fire on specific code paths:
  - `[AGGRESS] Handler attached` - only if there are Buy/Sell buttons in orderbook
  - `[AGGRESS] Button clicked` - only when button is clicked
  - Human may have been looking at the wrong time or with no orders present

**Fix Applied**:
- Added `[MARKET] Initializing...` log that ALWAYS fires on page load
- Added `[MARKET] Initialization complete. Buy/Sell handlers attached: N`
- Added `[AGGRESS] Button clicked` log right when button click happens
- Created Q-002 with detailed debugging instructions

**Git commit**: `d4f3f31` - deployed, Render should auto-deploy in ~2-3 min

**What human should check after deploy**:
1. Hard refresh (Ctrl+Shift+R) to get new JS
2. Look for `[MARKET] Initializing...` on page load (proves JS loaded)
3. If they don't see it, there's a deployment or caching issue
4. If they DO see it, clicking buttons should show `[AGGRESS] Button clicked...`

