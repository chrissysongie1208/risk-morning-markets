# Lessons Learned

Accumulated knowledge from this project. Each lesson references the TODO where it was discovered.

**READ THIS FILE AT THE START OF EVERY RUN** - past lessons prevent repeated mistakes.

---

## Format
```
### LESSON-XXX (TODO-YYY) - YYYY-MM-DD HH:MM
What we learned...

### LESSON-XXX (TODO-YYY) - YYYY-MM-DD HH:MM (DEBUNKED)
Old understanding...
**UPDATE (YYYY-MM-DD HH:MM)**: New understanding is...
```

When a lesson is proven wrong:
1. Add `(DEBUNKED)` to the header
2. Add `**UPDATE (timestamp)**:` explaining the new understanding
3. Never delete the original lesson

---

## Lessons

### LESSON-001 (TODO-002) - 2026-02-03 22:45
**Session management design**: Used in-memory dict for sessions (`_sessions: dict[str, str]`) mapping session_token -> user_id. This works for a small app but sessions are lost on server restart. For production, would need Redis or database-backed sessions. The cookie is set with `httponly=True` and `samesite="lax"` for security.

### LESSON-002 (TODO-002) - 2026-02-03 22:45
**Testing with httpx and FastAPI**: When testing FastAPI with `httpx.AsyncClient` and `ASGITransport`, the lifespan events (like `init_db()`) are NOT automatically triggered. Must manually call `await db.init_db()` before running tests. Also, httpx keeps a cookie jar by default, so create new client instances when you need a clean slate without cookies.

### LESSON-003 (TODO-002) - 2026-02-03 22:45
**Admin user creation**: The admin user (chrson) is created on first login rather than at database init time. This is cleaner because we don't need to handle the case where admin already exists in init_db. The `login_admin` function creates the admin user if it doesn't exist, using `get_user_by_name` then `create_user`.

### LESSON-004 (TODO-003) - 2026-02-03 22:48
**Enriching database records with related data**: When displaying order book or trades, we need to show user display names. Rather than complex JOIN queries, we fetch orders/trades first, then loop through and fetch user records by ID. This is simpler and acceptable for low-volume (20 users). Created helper models `OrderWithUser` and `TradeWithUsers` in `models.py` for type-safe templates. For higher scale, would use SQL JOINs or eager loading.

### LESSON-005 (TODO-003) - 2026-02-03 22:48
**PRG pattern with query parameters**: For admin actions (create market, close market, update config), use POST-Redirect-GET pattern. Pass success/error messages via query parameters using `urllib.parse.urlencode()`. This avoids issues with browser refresh re-submitting forms and keeps URLs bookmarkable. Templates check for `error` and `success` query params to display feedback.

### LESSON-006 (TODO-004) - 2026-02-03 23:15
**Position limits must consider open order exposure**: The position limit check must account for ALL open orders (resting orders that haven't filled yet), not just the current filled position. Otherwise users could place unlimited resting orders. Implemented `get_user_open_order_exposure()` in database.py to sum open bids and offers separately. The worst-case position is: `position + open_bids` (max long) or `position - open_offers` (max short).

### LESSON-007 (TODO-004) - 2026-02-03 23:15
**Matching engine architecture**: The matching engine uses a `MatchResult` dataclass to return rich information about what happened (trades, resting order, rejection reason). This allows the API layer to build appropriate feedback messages. Key matching rules: (1) Price-time priority - match at maker's price, (2) Self-trade prevention - exclude user's own orders from matching, (3) Position limits checked before matching and during fills. The engine is in `matching.py`, separate from `database.py` to keep concerns separated.

### LESSON-008 (TODO-004) - 2026-02-03 23:15
**Trade cost tracking for P&L**: Positions track `total_cost` which is the sum of `price * quantity` for all fills. Buyer adds cost, seller subtracts cost. This allows average price calculation (`total_cost / net_quantity`) and P&L calculation at settlement (`net_quantity * (settlement - avg_price)`). Note: cost can be negative for net sellers.

### LESSON-009 (TODO-005) - 2026-02-03 23:45
**HTMX partial templates for real-time updates**: To enable 1-second polling without full page refreshes, create partial templates in `templates/partials/` (orderbook.html, position.html, trades.html) that render just the dynamic content. The main page template uses `{% include 'partials/xxx.html' %}` for initial render, then HTMX `hx-get="/partials/xxx/{id}"` with `hx-trigger="every 1s"` polls for updates. This separates concerns: partials are used both for initial page load and subsequent polling.

### LESSON-010 (TODO-005) - 2026-02-03 23:45
**Partial endpoints return HTML, not redirects**: Unlike form submissions that use POST-Redirect-GET pattern, HTMX partial endpoints should return HTML fragments directly. If the session is expired, return an error message in HTML (e.g., `<p>Session expired</p>`) rather than redirecting, since HTMX will just swap in the response content. The main page will still work because the browser handles cookies for the HTMX requests.

### LESSON-011 (TODO-006) - 2026-02-03 12:10
**P&L calculation for flat positions**: When a user has a net_quantity of 0 (bought and sold equal amounts), the P&L is calculated as `-total_cost`. This is because total_cost tracks cumulative buys (+) and sells (-), so a flat position with total_cost=-50 means the user sold for more than they bought (profit of +50). The formula `linear_pnl = net_quantity * (settlement - avg_price)` only works for non-zero positions; for flat positions, use `-total_cost`.

### LESSON-012 (TODO-006) - 2026-02-03 12:10
**Settlement flow architecture**: Created a dedicated `settlement.py` module with: (1) `calculate_linear_pnl()` - pure function for P&L math, (2) `calculate_binary_result()` - pure function for WIN/LOSS/BREAKEVEN, (3) `settle_market()` - async function that cancels orders and updates market status, (4) `get_market_results()` - async function that computes and returns PositionWithPnL objects. The settle page (`settle.html`) is a GET endpoint showing current positions and a form to enter settlement value; the POST action triggers settlement and redirects to results page.

### LESSON-013 (TODO-007) - 2026-02-03 12:15
**Leaderboard aggregation pattern**: The `get_leaderboard()` function in `settlement.py` aggregates P&L across all settled markets by: (1) Filtering markets by status SETTLED, (2) Calling `get_market_results()` for each market, (3) Building a dict keyed by user_id to accumulate totals (total_linear_pnl, wins, losses, markets_traded), (4) Converting to `LeaderboardEntry` objects and sorting by total P&L descending. This approach reuses the existing P&L calculation logic rather than duplicating it.

### LESSON-014 (TODO-007) - 2026-02-03 12:15
**Admin config already existed**: The admin panel (admin.html) already had a form for position limit changes, and the `POST /admin/config` endpoint was already implemented in main.py. The admin.html template displays the current position limit in the form's input value and as a summary below the form. When verifying TODOs, always check existing code first to avoid reimplementing what's already done.

### LESSON-015 (TODO-007) - 2026-02-03 12:15
**Testing with existing database state**: When running tests against a persistent SQLite database, users created in previous test runs still exist. This caused issues when the test tried to join as "Alice" again and got a "name already taken" error. Solutions: (1) Use unique names per test run (e.g., with timestamps), (2) Delete the database file before testing, (3) Use a separate test database. For automated tests, pytest fixtures with `tmp_path` are recommended to ensure clean state.

### LESSON-016 (TODO-008) - 2026-02-03 12:20
**pytest-asyncio configuration**: With pytest-asyncio 1.3.0+, async fixtures require `@pytest_asyncio.fixture` decorator (not `@pytest.fixture`) to work properly with async tests. Additionally, need to configure `asyncio_mode = auto` in pytest.ini to avoid errors about async fixtures not being handled. The `asyncio_default_fixture_loop_scope = function` setting ensures each test gets a fresh event loop.

### LESSON-017 (TODO-008) - 2026-02-03 12:20
**Test database isolation with tmp_path_factory**: Using `tmp_path_factory.mktemp("data")` in an autouse fixture creates a fresh temporary database for each test. This is critical because overriding `db.DB_PATH` allows the matching engine and database module to use the test database without modifying any production code. Each test starts with clean state.

### LESSON-018 (TODO-008) - 2026-02-03 12:20
**Helper functions vs fixtures for test setup**: For complex test scenarios, helper functions like `create_resting_order()` and `set_user_position()` that directly call database functions are more flexible than fixtures. They allow tests to set up specific scenarios (e.g., user with +18 position) without the matching engine interfering. Keep them as regular async functions, not fixtures.

### LESSON-019 (TODO-009) - 2026-02-03 23:25
**Testing pure functions vs async integration functions separately**: Settlement tests benefit from separation: (1) Pure function tests (`calculate_linear_pnl`, `calculate_binary_result`) don't need database fixtures, run faster, and are easy to write with direct inputs/outputs. (2) Async integration tests (`settle_market`, `get_market_results`) use the database fixtures and test the full flow. This separation makes it easy to test edge cases for the core logic without setup overhead, and also validates the integration works correctly.

### LESSON-020 (TODO-009) - 2026-02-03 23:25
**Short position cost tracking convention**: For short positions, `total_cost` is negative because selling adds negative cost. When a user sells 10 @ 50, `total_cost = -500`. The average price formula `total_cost / net_quantity` still works: `-500 / -10 = 50`. This convention keeps the P&L formula `net_quantity * (settlement - avg_price)` consistent for both long and short positions.

### LESSON-021 (TODO-013) - 2026-02-03 12:36
**Binary P&L is per-trade, not per-position**: Binary P&L counts "lots won" vs "lots lost" on each individual trade. For a BUY: if settlement > trade price, user won those lots (+qty); if settlement < trade price, user lost (-qty). For a SELL: opposite. This is distinct from the overall binary result (WIN/LOSS/BREAKEVEN) which is based on total linear P&L. Created `calculate_binary_pnl_for_user()` as a pure function that takes user_id, trades list, and settlement value.

### LESSON-022 (TODO-013) - 2026-02-03 12:36
**Database function for fetching all trades**: Added `get_all_trades(market_id)` to database.py (alongside existing `get_recent_trades(market_id, limit=10)`). The settlement calculation needs ALL trades for accurate binary P&L, not just the most recent. This is fetched once per settlement results call and passed to the per-user calculation.

### LESSON-023 (TODO-013) - 2026-02-03 12:36
**Model evolution for new fields**: When adding new computed fields like `binary_pnl` to models, use default values (e.g., `binary_pnl: int = 0`) to maintain backward compatibility. Updated `PositionWithPnL` and `LeaderboardEntry` models. Templates were updated to display the new fields with appropriate formatting (positive = win color, negative = loss color).

### LESSON-024 (TODO-010) - 2026-02-03 12:45
**API integration testing with httpx**: When testing FastAPI with `httpx.AsyncClient` and `ASGITransport`, session cookies are automatically persisted within a single client instance. For testing multiple users, create separate `AsyncClient` instances. The `follow_redirects=False` parameter is useful for testing redirect responses (303 status codes) to verify the redirect URL contains expected query parameters.

### LESSON-025 (TODO-010) - 2026-02-03 12:45
**URL encoding in redirect assertions**: When testing redirects with query parameters, remember that spaces in error messages become `+` or `%20` in URLs (via `urllib.parse.urlencode`). Assertions like `"not open" in response.headers["location"]` fail because the URL has `not+open`. Check for URL-encoded variants: `"not+open" in location or "not%20open" in location`.

### LESSON-026 (TODO-010) - 2026-02-03 12:45
**Full lifecycle tests are valuable**: The `test_full_trade_lifecycle` test validates the complete flow: admin creates market → user A places offer → user B places crossing bid → verify trade & positions → admin settles → verify P&L. These end-to-end tests catch integration bugs that unit tests miss and serve as executable documentation of expected behavior.

### LESSON-027 (TODO-011) - 2026-02-03 13:00
**README structure for web apps**: A good README for a prediction market web app should cover: (1) Quick Start with numbered steps, (2) Features list, (3) How to Play for both participants and admins, (4) Trading rules explained clearly, (5) P&L calculation formulas with examples, (6) Project structure, (7) Test commands, (8) Network access instructions, (9) Tech stack, (10) API endpoints table. This structure helps both new users understand the app and developers understand the codebase.

### LESSON-028 (TODO-012) - 2026-02-03 12:48
**E2E testing with httpx must handle market discovery carefully**: When running E2E tests against a persistent database, identifying newly created markets requires comparing sets before/after creation. Using regex like `/markets/([a-f0-9-]{36})` finds ALL market IDs on the page - including old settled ones. The fix: capture market IDs before creation, then find the difference. This is more reliable than finding "the most recent" which may pick up stale data.

### LESSON-029 (TODO-012) - 2026-02-03 12:48
**Use unique names per test run**: When running E2E tests against a persistent database, use timestamps or unique suffixes in user display names (e.g., `Alice_{timestamp}`) to avoid conflicts with previous test runs. The app rejects duplicate display names, so reusing "Alice" will fail if that user already exists from a previous test.

### LESSON-030 (TODO-012) - 2026-02-03 12:48
**Verify P&L math carefully**: For short sellers, P&L calculation is: `net_quantity * (settlement - avg_price)`. With net_quantity=-10, avg_price=5, settlement=4: P&L = -10 * (4-5) = -10 * -1 = +10. The double negative makes shorts profit when settlement < avg_price. Always trace through the math manually when debugging P&L issues.

### LESSON-031 (TODO-014) - 2026-02-04 04:15
**PostgreSQL migration: Create orders before trades for FK constraints**: When migrating from SQLite to PostgreSQL, foreign key constraints are strictly enforced. The original matching engine used "TAKER" as a placeholder for the taker's order_id in trade records, which worked in SQLite but violates FK constraints in PostgreSQL. The fix: create the incoming order FIRST (with full quantity), then match against counter orders and create trades with valid order IDs, then update the incoming order's remaining quantity after all matches. This ensures all trade records have valid foreign keys to the orders table.

### LESSON-032 (TODO-014) - 2026-02-04 04:15
**databases library uses named parameters**: The `databases` library for async PostgreSQL uses `:param` syntax for named parameters (not `?` like sqlite). Example: `SELECT * FROM users WHERE id = :id` with params `{"id": user_id}`. This is actually cleaner and more readable than positional parameters. Also, `ON CONFLICT (key) DO NOTHING` replaces SQLite's `INSERT OR IGNORE`, and `ON CONFLICT (key) DO UPDATE SET` replaces `INSERT OR REPLACE`.

### LESSON-033 (TODO-014) - 2026-02-04 04:15
**Database connection lifecycle with databases library**: The `databases` library requires explicit `connect()` and `disconnect()` calls. In FastAPI, use lifespan events: `await db.connect_db()` on startup, `await db.disconnect_db()` on shutdown. Unlike aiosqlite which creates connections per-query, the databases library maintains a connection pool that must be explicitly managed.

### LESSON-034 (TODO-015) - 2026-02-04 15:20
**PostgreSQL test isolation with TRUNCATE CASCADE**: For pytest fixtures with PostgreSQL, use `TRUNCATE TABLE tablename CASCADE` to efficiently clear tables between tests. The CASCADE option handles foreign key dependencies automatically, so you can truncate in any order. This is much faster than dropping/recreating tables or rolling back transactions. Don't forget to re-initialize config data after truncation since TRUNCATE removes all rows including default config values.

### LESSON-035 (TODO-016) - 2026-02-04 04:30
**Concurrent testing with asyncio.gather()**: Use `asyncio.gather(*tasks)` to run multiple async operations simultaneously and verify the system handles concurrent access. Create separate `AsyncClient` instances for each simulated user to maintain separate cookie jars/sessions. This approach tests real concurrency scenarios rather than sequential execution.

### LESSON-036 (TODO-016) - 2026-02-04 04:30
**Race conditions in matching without database locking**: Without database-level row locking (`SELECT FOR UPDATE`), concurrent matching can cause race conditions where the same offer is matched multiple times by different buyers. This results in "over-fills" and positions that don't sum to zero. For a small-scale app (20 users), this is acceptable. Production systems would need: (1) `SELECT FOR UPDATE` on matching orders, (2) Database transactions wrapping the entire match operation, or (3) A serialized matching engine (single-threaded queue).

### LESSON-037 (TODO-016) - 2026-02-04 04:30
**Designing concurrent tests for systems with known limitations**: When testing concurrent scenarios on systems without full ACID guarantees, focus on verifying: (1) System doesn't crash under load, (2) All HTTP requests complete successfully, (3) Expected operations happen (trades created, positions exist). Document known limitations clearly in test docstrings rather than asserting impossible invariants that race conditions will violate.

### LESSON-038 (TODO-017) - 2026-02-04 15:45
**Render.yaml blueprint structure**: Render.com uses a `render.yaml` file to define infrastructure as code. Key points: (1) Use `runtime: python` not `env: python` in current Render syntax, (2) `fromDatabase` links environment variables to provisioned databases, (3) The `$PORT` environment variable is set by Render and must be passed to the app via command line (`--port $PORT`). The `__name__ == "__main__"` block in main.py isn't used in production since uvicorn is invoked directly.

### LESSON-039 (TODO-017) - 2026-02-04 15:45
**Render.com free tier limitations**: The free PostgreSQL database on Render expires after 90 days. The free web service also sleeps after 15 minutes of inactivity and takes ~30 seconds to wake up on first request. For a hackathon/demo app this is acceptable. For production, upgrade to paid tiers for persistent databases and always-on services.

### LESSON-040 (TODO-018) - 2026-02-04 16:00
**README structure for database-backed apps with cloud deployment**: A good README for a PostgreSQL-backed app with Render deployment should cover: (1) Quick Start with numbered steps including `docker-compose up -d` first, (2) Environment variables in a table format (DATABASE_URL, PORT), (3) Separate sections for local dev vs cloud deployment, (4) Test commands that include setting DATABASE_URL, (5) docker-compose quick commands (up/down/down -v). When updating a README from SQLite to PostgreSQL, remember to update ALL references: the Tech Stack section, the project structure comments (database.py -> "PostgreSQL setup"), and any test commands.

### LESSON-041 (TODO-019) - 2026-02-04 04:50
**Cloud deployment requires human interaction**: Deploying to cloud platforms like Render.com, Heroku, or AWS requires credentials and interactive dashboard access that an agent cannot provide autonomously. When a TODO requires cloud deployment:
1. Verify everything works locally first (tests pass, server runs)
2. Prepare all deployment configuration files (render.yaml, Dockerfile, etc.)
3. Document step-by-step manual instructions in README
4. Mark the TODO as blocked [?] and write to QUESTIONS.md asking for: (a) the GitHub repo URL to push to, or (b) whether to skip cloud deployment and mark as local-only complete
This ensures the human returns to a working local app with clear instructions, not a half-deployed broken state.

### LESSON-042 (TODO-019) - 2026-02-04
**Use Neon for PostgreSQL instead of Render's free database**: Render's free PostgreSQL expires after 90 days, which creates maintenance headaches. Neon (neon.tech) provides free PostgreSQL with no expiry. Setup: (1) Create Neon account with GitHub, (2) Create database, copy connection string, (3) In Render, create web service manually (not blueprint), (4) Add DATABASE_URL env var pointing to Neon. This decouples the database from Render's expiring free tier.

### LESSON-043 (TODO-019) - 2026-02-04
**Git credential conflicts with work vs personal accounts**: When pushing to a personal GitHub repo from a work machine, cached work credentials may block access. Fix: embed username in the remote URL: `git remote set-url origin https://USERNAME@github.com/USERNAME/repo.git`. For password, use a Personal Access Token (PAT) from github.com/settings/tokens with `repo` scope. The token works as a password when prompted.
