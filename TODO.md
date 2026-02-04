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

<!-- Add new TODOs here with sequential IDs -->

