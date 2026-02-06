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

