"""Integration tests for the Morning Markets API.

Tests cover:
- Join flow (unique names, duplicate rejection)
- Admin authentication (correct credentials, wrong credentials)
- Market CRUD (create as admin, reject non-admin)
- Order placement
- Order cancellation
- Full trade lifecycle
"""

import pytest
import pytest_asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from httpx import AsyncClient, ASGITransport
from main import app
import database as db
import auth
from conftest import create_participant_and_get_id


@pytest_asyncio.fixture
async def client():
    """Create an async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_client():
    """Create an async HTTP client logged in as admin."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Login as admin
        response = await ac.post(
            "/admin/login",
            data={"username": "chrson", "password": "optiver"},
            follow_redirects=False
        )
        # Cookie should be set from the redirect response
        yield ac


@pytest_asyncio.fixture
async def participant_client():
    """Create an async HTTP client logged in as a participant."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create a pre-registered participant and join
        participant_id = await create_participant_and_get_id("TestParticipant")
        response = await ac.post(
            "/join",
            data={"participant_id": participant_id},
            follow_redirects=False
        )
        yield ac


# ============ Join Flow Tests ============

@pytest.mark.asyncio
async def test_join_unique_name(client):
    """POST /join with pre-registered participant -> success, get session"""
    # Create a pre-registered participant
    participant_id = await create_participant_and_get_id("UniqueUser1")

    response = await client.post(
        "/join",
        data={"participant_id": participant_id},
        follow_redirects=False
    )

    # Should redirect to /markets
    assert response.status_code == 303
    assert response.headers["location"] == "/markets"

    # Should have session cookie set
    assert "session" in response.cookies


@pytest.mark.asyncio
async def test_join_already_claimed_allows_rejoin(client):
    """POST /join with already claimed participant -> allows rejoin (same user)"""
    # Create a pre-registered participant
    participant_id = await create_participant_and_get_id("ClaimedUser")

    # First user joins successfully
    response1 = await client.post(
        "/join",
        data={"participant_id": participant_id},
        follow_redirects=False
    )
    assert response1.status_code == 303
    assert response1.headers["location"] == "/markets"

    # Same participant joins again - should work (returns same user session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client2:
        response2 = await client2.post(
            "/join",
            data={"participant_id": participant_id},
            follow_redirects=False
        )

        # Should still redirect to /markets (same user rejoins)
        assert response2.status_code == 303
        assert response2.headers["location"] == "/markets"


# ============ Pre-registered Participants Tests ============

@pytest.mark.asyncio
async def test_join_invalid_participant_id(client):
    """POST /join with non-existent participant ID -> redirect with error"""
    response = await client.post(
        "/join",
        data={"participant_id": "non-existent-uuid-12345"},
        follow_redirects=False
    )

    # Should redirect to / with error
    assert response.status_code == 303
    assert "error=" in response.headers["location"]


@pytest.mark.asyncio
async def test_join_empty_participant_id(client):
    """POST /join with empty participant_id -> rejected"""
    response = await client.post(
        "/join",
        data={"participant_id": "   "},  # Whitespace-only
        follow_redirects=False
    )

    # With whitespace the form validates, but our handler strips and rejects
    assert response.status_code == 303
    assert "error=" in response.headers["location"]


@pytest.mark.asyncio
async def test_admin_create_participant(admin_client):
    """POST /admin/participants as admin -> participant created"""
    response = await admin_client.post(
        "/admin/participants",
        data={"display_name": "NewParticipant"},
        follow_redirects=False
    )

    # Should redirect to /admin with success message
    assert response.status_code == 303
    assert "/admin" in response.headers["location"]
    assert "success=" in response.headers["location"]

    # Verify participant was created
    participant = await db.get_participant_by_name("NewParticipant")
    assert participant is not None
    assert participant.claimed_by_user_id is None


@pytest.mark.asyncio
async def test_admin_create_duplicate_participant(admin_client):
    """POST /admin/participants with duplicate name -> redirect with error"""
    # Create first participant
    await admin_client.post(
        "/admin/participants",
        data={"display_name": "DuplicateName"},
        follow_redirects=True
    )

    # Try to create duplicate
    response = await admin_client.post(
        "/admin/participants",
        data={"display_name": "DuplicateName"},
        follow_redirects=False
    )

    # Should redirect with error
    assert response.status_code == 303
    assert "error=" in response.headers["location"]


@pytest.mark.asyncio
async def test_admin_delete_unclaimed_participant(admin_client):
    """POST /admin/participants/{id}/delete on unclaimed -> success"""
    # Create participant
    participant_id = await create_participant_and_get_id("ToDelete")

    # Delete it
    response = await admin_client.post(
        f"/admin/participants/{participant_id}/delete",
        follow_redirects=False
    )

    # Should redirect with success
    assert response.status_code == 303
    assert "success=" in response.headers["location"]
    assert "deleted" in response.headers["location"].lower()

    # Verify participant was deleted
    participant = await db.get_participant_by_id(participant_id)
    assert participant is None


@pytest.mark.asyncio
async def test_admin_cannot_delete_claimed_participant(admin_client):
    """POST /admin/participants/{id}/delete on claimed -> error"""
    # Create and claim participant
    participant_id = await create_participant_and_get_id("ClaimedToDelete")

    # Have someone claim it via join
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as joiner:
        await joiner.post(
            "/join",
            data={"participant_id": participant_id},
            follow_redirects=False
        )

    # Try to delete claimed participant
    response = await admin_client.post(
        f"/admin/participants/{participant_id}/delete",
        follow_redirects=False
    )

    # Should redirect with error
    assert response.status_code == 303
    assert "error=" in response.headers["location"]


@pytest.mark.asyncio
async def test_admin_release_claimed_participant(admin_client):
    """POST /admin/participants/{id}/release on claimed -> success"""
    # Create and claim participant
    participant_id = await create_participant_and_get_id("ClaimedToRelease")

    # Have someone claim it
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as joiner:
        await joiner.post(
            "/join",
            data={"participant_id": participant_id},
            follow_redirects=False
        )

    # Verify it's claimed
    participant = await db.get_participant_by_id(participant_id)
    assert participant.claimed_by_user_id is not None

    # Release it
    response = await admin_client.post(
        f"/admin/participants/{participant_id}/release",
        follow_redirects=False
    )

    # Should redirect with success
    assert response.status_code == 303
    assert "success=" in response.headers["location"]
    assert "released" in response.headers["location"].lower()

    # Verify participant is unclaimed
    participant = await db.get_participant_by_id(participant_id)
    assert participant.claimed_by_user_id is None


@pytest.mark.asyncio
async def test_only_unclaimed_participants_in_dropdown():
    """GET / should show only unclaimed participants in dropdown"""
    transport = ASGITransport(app=app)

    # Create two participants
    participant1_id = await create_participant_and_get_id("AvailableParticipant")
    participant2_id = await create_participant_and_get_id("ClaimedParticipant")

    # Claim one participant
    async with AsyncClient(transport=transport, base_url="http://test") as claimer:
        await claimer.post(
            "/join",
            data={"participant_id": participant2_id},
            follow_redirects=False
        )

    # Now check available participants
    available = await db.get_available_participants()
    available_names = [p.display_name for p in available]

    assert "AvailableParticipant" in available_names
    assert "ClaimedParticipant" not in available_names


@pytest.mark.asyncio
async def test_participant_create_as_non_admin_rejected(participant_client):
    """POST /admin/participants as non-admin -> 403"""
    response = await participant_client.post(
        "/admin/participants",
        data={"display_name": "ShouldNotExist"},
        follow_redirects=False
    )

    # Should return 403 Forbidden
    assert response.status_code == 403


# ============ Admin Auth Tests ============

@pytest.mark.asyncio
async def test_admin_login_correct_credentials(client):
    """POST /admin/login with chrson/optiver -> success"""
    response = await client.post(
        "/admin/login",
        data={"username": "chrson", "password": "optiver"},
        follow_redirects=False
    )

    # Should redirect to /markets
    assert response.status_code == 303
    assert response.headers["location"] == "/markets"

    # Should have session cookie set
    assert "session" in response.cookies


@pytest.mark.asyncio
async def test_admin_login_wrong_credentials(client):
    """POST /admin/login with wrong password -> redirect with error"""
    response = await client.post(
        "/admin/login",
        data={"username": "chrson", "password": "wrongpassword"},
        follow_redirects=False
    )

    # Should redirect to / with error
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    assert "invalid" in response.headers["location"].lower() or "/" == response.headers["location"].split("?")[0]


# ============ Market CRUD Tests ============

@pytest.mark.asyncio
async def test_create_market_as_admin(admin_client):
    """POST /admin/markets as admin -> market created"""
    response = await admin_client.post(
        "/admin/markets",
        data={"question": "Test question?", "description": "Test description"},
        follow_redirects=False
    )

    # Should redirect to /admin with success message
    assert response.status_code == 303
    assert "/admin" in response.headers["location"]
    assert "success=" in response.headers["location"]


@pytest.mark.asyncio
async def test_create_market_as_participant_rejected(participant_client):
    """POST /admin/markets as non-admin -> 403"""
    response = await participant_client.post(
        "/admin/markets",
        data={"question": "Test question?", "description": "Test description"},
        follow_redirects=False
    )

    # Should return 403 Forbidden
    assert response.status_code == 403


# ============ Order Tests ============

@pytest.mark.asyncio
async def test_place_order(admin_client):
    """POST /markets/{id}/orders -> order created"""
    # First create a market
    await admin_client.post(
        "/admin/markets",
        data={"question": "Order test market?"},
        follow_redirects=True
    )

    # Get markets list to find the market ID
    markets = await db.get_all_markets()
    market = next((m for m in markets if "Order test market" in m.question), None)
    assert market is not None

    # Place an order
    response = await admin_client.post(
        f"/markets/{market.id}/orders",
        data={"side": "BID", "price": "100", "quantity": "5"},
        follow_redirects=False
    )

    # Should redirect back to market page with success
    assert response.status_code == 303
    assert f"/markets/{market.id}" in response.headers["location"]
    assert "success=" in response.headers["location"] or "error=" not in response.headers["location"]


@pytest.mark.asyncio
async def test_place_order_on_closed_market_rejected(admin_client):
    """POST /markets/{id}/orders on CLOSED market -> redirect with error"""
    # Create a market
    await admin_client.post(
        "/admin/markets",
        data={"question": "Closed market test?"},
        follow_redirects=True
    )

    # Find the market
    markets = await db.get_all_markets()
    market = next((m for m in markets if "Closed market test" in m.question), None)
    assert market is not None

    # Close the market
    await admin_client.post(
        f"/admin/markets/{market.id}/close",
        follow_redirects=True
    )

    # Try to place an order
    response = await admin_client.post(
        f"/markets/{market.id}/orders",
        data={"side": "BID", "price": "100", "quantity": "5"},
        follow_redirects=False
    )

    # Should redirect with error about market not open
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    # URL-encoded: "not open" becomes "not+open"
    location = response.headers["location"].lower()
    assert "not+open" in location or "not%20open" in location or "closed" in location


# ============ Order Cancellation Tests ============

@pytest.mark.asyncio
async def test_cancel_own_order(admin_client):
    """POST /orders/{id}/cancel on own order -> success"""
    # Create a market
    await admin_client.post(
        "/admin/markets",
        data={"question": "Cancel test market?"},
        follow_redirects=True
    )

    # Find the market
    markets = await db.get_all_markets()
    market = next((m for m in markets if "Cancel test market" in m.question), None)
    assert market is not None

    # Place an order
    await admin_client.post(
        f"/markets/{market.id}/orders",
        data={"side": "BID", "price": "100", "quantity": "5"},
        follow_redirects=True
    )

    # Find the order
    orders = await db.get_open_orders(market.id)
    assert len(orders) > 0
    order = orders[0]

    # Cancel the order
    response = await admin_client.post(
        f"/orders/{order.id}/cancel",
        follow_redirects=False
    )

    # Should redirect with success
    assert response.status_code == 303
    assert "success=" in response.headers["location"]
    assert "cancelled" in response.headers["location"].lower()


@pytest.mark.asyncio
async def test_cancel_other_user_order_rejected():
    """POST /orders/{id}/cancel on other's order -> error"""
    # Create admin client and participant client
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as admin_cl:
        # Login as admin
        await admin_cl.post(
            "/admin/login",
            data={"username": "chrson", "password": "optiver"},
            follow_redirects=False
        )

        # Create a market
        await admin_cl.post(
            "/admin/markets",
            data={"question": "Other user cancel test?"},
            follow_redirects=True
        )

        # Find the market
        markets = await db.get_all_markets()
        market = next((m for m in markets if "Other user cancel test" in m.question), None)
        assert market is not None

        # Admin places an order
        await admin_cl.post(
            f"/markets/{market.id}/orders",
            data={"side": "BID", "price": "100", "quantity": "5"},
            follow_redirects=True
        )

        # Find the order
        orders = await db.get_open_orders(market.id)
        assert len(orders) > 0
        order = orders[0]

    # Now create a different user to try to cancel
    async with AsyncClient(transport=transport, base_url="http://test") as other_cl:
        # Create and join as different participant
        other_participant_id = await create_participant_and_get_id("OtherCancelUser")
        await other_cl.post(
            "/join",
            data={"participant_id": other_participant_id},
            follow_redirects=False
        )

        # Try to cancel admin's order
        response = await other_cl.post(
            f"/orders/{order.id}/cancel",
            follow_redirects=False
        )

        # Should redirect with error (not their order)
        assert response.status_code == 303
        assert "error=" in response.headers["location"]


# ============ Settlement Tests ============

@pytest.mark.asyncio
async def test_settle_market_as_admin(admin_client):
    """POST /admin/markets/{id}/settle -> market settled"""
    # Create a market
    await admin_client.post(
        "/admin/markets",
        data={"question": "Settlement test market?"},
        follow_redirects=True
    )

    # Find the market
    markets = await db.get_all_markets()
    market = next((m for m in markets if "Settlement test market" in m.question), None)
    assert market is not None

    # Settle the market
    response = await admin_client.post(
        f"/admin/markets/{market.id}/settle",
        data={"settlement_value": "100"},
        follow_redirects=False
    )

    # Should redirect to results page
    assert response.status_code == 303
    assert f"/markets/{market.id}/results" in response.headers["location"]

    # Verify market is settled
    updated_market = await db.get_market(market.id)
    assert updated_market.status.value == "SETTLED"
    assert updated_market.settlement_value == 100.0


@pytest.mark.asyncio
async def test_settle_open_market_cancels_orders(admin_client):
    """POST /admin/markets/{id}/settle on OPEN market -> orders cancelled, market settled"""
    # Create a market (starts as OPEN)
    await admin_client.post(
        "/admin/markets",
        data={"question": "Settle open market test?"},
        follow_redirects=True
    )

    # Find the market
    markets = await db.get_all_markets()
    market = next((m for m in markets if "Settle open market test" in m.question), None)
    assert market is not None
    assert market.status.value == "OPEN"

    # Place some orders that should be cancelled on settle
    await admin_client.post(
        f"/markets/{market.id}/orders",
        data={"side": "BID", "price": "95", "quantity": "5"},
        follow_redirects=True
    )
    await admin_client.post(
        f"/markets/{market.id}/orders",
        data={"side": "OFFER", "price": "105", "quantity": "5"},
        follow_redirects=True
    )

    # Verify orders exist
    open_orders = await db.get_open_orders(market.id)
    assert len(open_orders) == 2

    # Settle the OPEN market directly (without closing first)
    response = await admin_client.post(
        f"/admin/markets/{market.id}/settle",
        data={"settlement_value": "100"},
        follow_redirects=False
    )

    # Should redirect to results page
    assert response.status_code == 303
    assert f"/markets/{market.id}/results" in response.headers["location"]

    # Verify market is settled (went from OPEN directly to SETTLED)
    updated_market = await db.get_market(market.id)
    assert updated_market.status.value == "SETTLED"
    assert updated_market.settlement_value == 100.0

    # Verify open orders were cancelled
    open_orders_after = await db.get_open_orders(market.id)
    assert len(open_orders_after) == 0


# ============ Full Trade Lifecycle Test ============

@pytest.mark.asyncio
async def test_full_trade_lifecycle():
    """
    1. Admin creates market
    2. User A places offer at 100 for 5
    3. User B places bid at 100 for 5
    4. Verify trade created, positions updated
    5. Admin settles at 110
    6. Verify P&L: A = -50 (sold at 100, settled 110), B = +50
    """
    transport = ASGITransport(app=app)

    # Step 1: Admin creates market
    async with AsyncClient(transport=transport, base_url="http://test") as admin_cl:
        await admin_cl.post(
            "/admin/login",
            data={"username": "chrson", "password": "optiver"},
            follow_redirects=False
        )

        await admin_cl.post(
            "/admin/markets",
            data={"question": "Full lifecycle test market?"},
            follow_redirects=True
        )

        # Find the market
        markets = await db.get_all_markets()
        market = next((m for m in markets if "Full lifecycle test market" in m.question), None)
        assert market is not None

    # Step 2: User A places offer at 100 for 5
    user_a_participant_id = await create_participant_and_get_id("LifecycleUserA")
    async with AsyncClient(transport=transport, base_url="http://test") as user_a_cl:
        await user_a_cl.post(
            "/join",
            data={"participant_id": user_a_participant_id},
            follow_redirects=False
        )

        await user_a_cl.post(
            f"/markets/{market.id}/orders",
            data={"side": "OFFER", "price": "100", "quantity": "5"},
            follow_redirects=True
        )

        # Get User A's info
        user_a = await db.get_user_by_name("LifecycleUserA")
        assert user_a is not None

    # Step 3: User B places bid at 100 for 5 (should match)
    user_b_participant_id = await create_participant_and_get_id("LifecycleUserB")
    async with AsyncClient(transport=transport, base_url="http://test") as user_b_cl:
        await user_b_cl.post(
            "/join",
            data={"participant_id": user_b_participant_id},
            follow_redirects=False
        )

        await user_b_cl.post(
            f"/markets/{market.id}/orders",
            data={"side": "BID", "price": "100", "quantity": "5"},
            follow_redirects=True
        )

        # Get User B's info
        user_b = await db.get_user_by_name("LifecycleUserB")
        assert user_b is not None

    # Step 4: Verify trade created, positions updated
    trades = await db.get_recent_trades(market.id, limit=10)
    assert len(trades) >= 1

    trade = trades[0]
    assert trade.price == 100.0
    assert trade.quantity == 5
    assert trade.buyer_id == user_b.id
    assert trade.seller_id == user_a.id

    # Check positions
    pos_a = await db.get_position(market.id, user_a.id)
    pos_b = await db.get_position(market.id, user_b.id)

    assert pos_a.net_quantity == -5  # Sold 5
    assert pos_b.net_quantity == 5   # Bought 5

    # Step 5: Admin settles at 110
    async with AsyncClient(transport=transport, base_url="http://test") as admin_cl2:
        await admin_cl2.post(
            "/admin/login",
            data={"username": "chrson", "password": "optiver"},
            follow_redirects=False
        )

        await admin_cl2.post(
            f"/admin/markets/{market.id}/settle",
            data={"settlement_value": "110"},
            follow_redirects=True
        )

    # Step 6: Verify P&L
    # User A: sold 5 @ 100, settled at 110 → linear P&L = -5 * (110 - 100) = -50 (LOSS)
    # User B: bought 5 @ 100, settled at 110 → linear P&L = 5 * (110 - 100) = +50 (WIN)

    import settlement as settle_module
    results = await settle_module.get_market_results(market.id)

    result_a = next((r for r in results if r.user_id == user_a.id), None)
    result_b = next((r for r in results if r.user_id == user_b.id), None)

    assert result_a is not None
    assert result_b is not None

    assert result_a.linear_pnl == -50.0
    assert result_a.binary_pnl == -5  # Sold 5 lots below settlement = lost 5 lots

    assert result_b.linear_pnl == 50.0
    assert result_b.binary_pnl == 5  # Bought 5 lots below settlement = won 5 lots


# ============ Combined Partial Endpoint Tests (TODO-028) ============

@pytest.mark.asyncio
async def test_combined_partial_returns_all_sections(admin_client):
    """GET /partials/market/{id} returns position, orderbook, and trades in one response."""
    # Create a market
    await admin_client.post(
        "/admin/markets",
        data={"question": "Combined partial test market?"},
        follow_redirects=True
    )

    # Find the market
    markets = await db.get_all_markets()
    market = next((m for m in markets if "Combined partial test market" in m.question), None)
    assert market is not None

    # Place some orders for orderbook
    await admin_client.post(
        f"/markets/{market.id}/orders",
        data={"side": "BID", "price": "95", "quantity": "3"},
        follow_redirects=True
    )
    await admin_client.post(
        f"/markets/{market.id}/orders",
        data={"side": "OFFER", "price": "105", "quantity": "3"},
        follow_redirects=True
    )

    # Get combined partial
    response = await admin_client.get(f"/partials/market/{market.id}")

    assert response.status_code == 200
    content = response.text

    # Verify all 3 sections are present
    # Position section
    assert 'id="position-content"' in content

    # Orderbook section with OOB swap
    assert 'id="orderbook"' in content
    assert 'hx-swap-oob="innerHTML"' in content
    assert "Bids (Buy Orders)" in content
    assert "Offers (Sell Orders)" in content

    # Trades section with OOB swap
    assert 'id="trades"' in content
    # The trades div should have OOB attribute
    assert content.count('hx-swap-oob="innerHTML"') >= 2  # orderbook and trades both have it


@pytest.mark.asyncio
async def test_combined_partial_shows_position_data(admin_client):
    """GET /partials/market/{id} shows user's position correctly."""
    # Create a market
    await admin_client.post(
        "/admin/markets",
        data={"question": "Position partial test?"},
        follow_redirects=True
    )

    markets = await db.get_all_markets()
    market = next((m for m in markets if "Position partial test" in m.question), None)
    assert market is not None

    # No trades yet - position should show "No position"
    response = await admin_client.get(f"/partials/market/{market.id}")
    assert response.status_code == 200
    assert "No position" in response.text


@pytest.mark.asyncio
async def test_combined_partial_shows_orderbook_data(admin_client):
    """GET /partials/market/{id} shows orders in the orderbook."""
    # Create a market
    await admin_client.post(
        "/admin/markets",
        data={"question": "Orderbook partial test?"},
        follow_redirects=True
    )

    markets = await db.get_all_markets()
    market = next((m for m in markets if "Orderbook partial test" in m.question), None)
    assert market is not None

    # Place a bid
    await admin_client.post(
        f"/markets/{market.id}/orders",
        data={"side": "BID", "price": "99.50", "quantity": "7"},
        follow_redirects=True
    )

    response = await admin_client.get(f"/partials/market/{market.id}")
    assert response.status_code == 200

    # Should show the bid price and quantity
    assert "99.50" in response.text
    assert "7" in response.text or ">7<" in response.text


@pytest.mark.asyncio
async def test_combined_partial_redirects_when_settled(admin_client):
    """GET /partials/market/{id} returns HX-Redirect header when market is settled."""
    # Create and settle a market
    await admin_client.post(
        "/admin/markets",
        data={"question": "Settled partial test?"},
        follow_redirects=True
    )

    markets = await db.get_all_markets()
    market = next((m for m in markets if "Settled partial test" in m.question), None)
    assert market is not None

    # Settle the market
    await admin_client.post(
        f"/admin/markets/{market.id}/settle",
        data={"settlement_value": "100"},
        follow_redirects=True
    )

    # Now request the combined partial
    response = await admin_client.get(f"/partials/market/{market.id}")

    # Should return HX-Redirect header for HTMX to redirect to results
    assert response.status_code == 200
    assert "HX-Redirect" in response.headers
    assert f"/markets/{market.id}/results" in response.headers["HX-Redirect"]


# ============ Backward Compatibility Tests for Old Partials (TODO-028) ============

@pytest.mark.asyncio
async def test_deprecated_orderbook_partial_still_works(admin_client):
    """GET /partials/orderbook/{id} (deprecated) still returns orderbook HTML."""
    # Create a market
    await admin_client.post(
        "/admin/markets",
        data={"question": "Deprecated orderbook test?"},
        follow_redirects=True
    )

    markets = await db.get_all_markets()
    market = next((m for m in markets if "Deprecated orderbook test" in m.question), None)
    assert market is not None

    # Place an order
    await admin_client.post(
        f"/markets/{market.id}/orders",
        data={"side": "OFFER", "price": "102", "quantity": "4"},
        follow_redirects=True
    )

    # Use deprecated endpoint
    response = await admin_client.get(f"/partials/orderbook/{market.id}")

    assert response.status_code == 200
    assert "Bids (Buy Orders)" in response.text
    assert "Offers (Sell Orders)" in response.text
    assert "102" in response.text  # Our order price


@pytest.mark.asyncio
async def test_deprecated_position_partial_still_works(admin_client):
    """GET /partials/position/{id} (deprecated) still returns position HTML."""
    # Create a market
    await admin_client.post(
        "/admin/markets",
        data={"question": "Deprecated position test?"},
        follow_redirects=True
    )

    markets = await db.get_all_markets()
    market = next((m for m in markets if "Deprecated position test" in m.question), None)
    assert market is not None

    response = await admin_client.get(f"/partials/position/{market.id}")

    assert response.status_code == 200
    # Should show "No position" since we haven't traded
    assert "No position" in response.text or "position" in response.text.lower()


@pytest.mark.asyncio
async def test_deprecated_trades_partial_still_works(admin_client):
    """GET /partials/trades/{id} (deprecated) still returns trades HTML."""
    # Create a market
    await admin_client.post(
        "/admin/markets",
        data={"question": "Deprecated trades test?"},
        follow_redirects=True
    )

    markets = await db.get_all_markets()
    market = next((m for m in markets if "Deprecated trades test" in m.question), None)
    assert market is not None

    response = await admin_client.get(f"/partials/trades/{market.id}")

    assert response.status_code == 200
    # Should show "No trades yet" since we haven't traded
    assert "No trades" in response.text or "trades" in response.text.lower()
