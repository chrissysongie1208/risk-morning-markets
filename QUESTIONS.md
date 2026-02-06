# Questions for Human

When stuck, write questions here with `Status: PENDING`. Human will answer and change to `Status: ANSWERED`.

---

## Format
```
### Q-XXX (TODO-YYY) - YYYY-MM-DD
**Status**: PENDING | ANSWERED
**Question**: ...
**Context**: ...
**Answer**: (Human fills this in)
```

---

## Questions

### Q-001 (TODO-048) - 2026-02-05
**Status**: ANSWERED
**Question**: Please verify the Buy/Sell button fix in production at https://risk-morning-markets.onrender.com

**Context**: TODO-047 implemented a client-side "aggress lock" mechanism to prevent WebSocket DOM updates from destroying the aggress form mid-submission. This was identified as the root cause of the ~80% button failure rate.

**Test scenarios to perform**:
1. **Single user rapid clicking**: Open market page, place a resting order with one browser tab, then rapidly click Buy/Sell buttons (~5+ times in quick succession) from another tab/user
2. **Two users simultaneously**: Have two browsers/tabs logged in as different users, both clicking Buy/Sell buttons at the same time
3. **Check console logs**: Open DevTools (F12) Console tab to see `[AGGRESS]` log messages showing lock acquire/release pattern

**Expected results**:
- Success rate >95% (almost all clicks result in trades or proper error toasts)
- Console shows: `[AGGRESS] Lock acquired` followed by `[AGGRESS] Lock released`
- If WebSocket update arrives during submission: `[AGGRESS] Deferring orderbook update`

**Answer**: i cant see it in Console tab, you will need to figure this one out yourself.

### Q-002 (Follow-up to Q-001) - 2026-02-06
**Status**: PENDING
**Question**: Improved console logging deployed - please verify Buy/Sell buttons work

**Context**: The previous logging was not visible enough. I've added clearer initialization logs that ALWAYS fire on page load.

**What you should see in Console (F12)**:
1. **On page load** (always):
   - `[MARKET] Initializing market page for market: <uuid>`
   - `[MARKET] Initialization complete. Buy/Sell handlers attached: N` (where N = number of orders)
   - `WebSocket connected` (if WebSocket working)

2. **On each Buy/Sell button click** (if buttons work):
   - `[AGGRESS] Button clicked for order: <uuid> Button text: Buy` (or Sell)
   - `[AGGRESS] Executing via fetch: {orderId: ..., qty: ..., fak: ...}`
   - `[AGGRESS] Success: Bought X lots @ Y` (or Error message)
   - `[AGGRESS] Lock released`

3. **After WebSocket updates orderbook**:
   - `[AGGRESS] Handler attached for order: <uuid>` (for each new Buy/Sell button)

**Debugging steps**:
1. Open https://risk-morning-markets.onrender.com
2. Login and go to a market with orders
3. Open DevTools (F12) → Console tab
4. Look for `[MARKET] Initializing...` message (confirms JS is loading)
5. Click a Buy or Sell button
6. Look for `[AGGRESS] Button clicked...` message (confirms handler is attached)

**If you don't see `[MARKET] Initializing...`**:
- Try hard refresh (Ctrl+Shift+R) to clear cached JavaScript
- Check for JavaScript errors in the Console (red text)

**If you see `[MARKET] Initializing...` but not `[AGGRESS] Button clicked...` when you click**:
- The handler isn't attached to that button
- Check if connection shows "Live" or "Polling"
- Try clicking again after a few seconds (WebSocket might be re-attaching handlers)

**Please report**:
1. What messages appear in Console on page load?
2. What happens when you click Buy/Sell? (success toast? nothing? error?)
3. What does the connection indicator show? (Live/Polling/Reconnecting?)
