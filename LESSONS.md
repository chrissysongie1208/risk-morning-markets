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
