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
**Status**: PENDING
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

**Answer**: (Please report: success rate, any failures observed, console log patterns)
