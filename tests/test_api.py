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
async def test_join_already_claimed_blocks_if_active(client):
    """POST /join with already claimed participant -> blocked if user is active (session exclusivity)"""
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

    # Another attempt to join with the same participant should be blocked
    # (because the first user just logged in and is considered "active")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client2:
        response2 = await client2.post(
            "/join",
            data={"participant_id": participant_id},
            follow_redirects=False
        )

        # Should be rejected with "already in use" error (session exclusivity)
        assert response2.status_code == 303
        assert "error=" in response2.headers["location"]
        assert "in+use" in response2.headers["location"].lower() or "already" in response2.headers["location"].lower()


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

    # Orderbook section with OOB swap (price ladder layout)
    assert 'id="orderbook"' in content
    assert 'hx-swap-oob="innerHTML"' in content
    assert 'class="price-ladder"' in content
    assert "ladder-bid-info" in content
    assert "ladder-offer-info" in content

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
    # Price ladder layout uses different structure
    assert 'class="price-ladder"' in response.text
    assert "ladder-bid-info" in response.text or "ladder-offer-info" in response.text
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


# ============ Admin Settle on Market Page Tests (TODO-029) ============

@pytest.mark.asyncio
async def test_admin_sees_settle_form_on_market_page(admin_client):
    """GET /markets/{id} as admin on OPEN market shows settle form."""
    # Create a market
    await admin_client.post(
        "/admin/markets",
        data={"question": "Admin settle form visibility test?"},
        follow_redirects=True
    )

    markets = await db.get_all_markets()
    market = next((m for m in markets if "Admin settle form visibility test" in m.question), None)
    assert market is not None
    assert market.status.value == "OPEN"

    # View the market page as admin
    response = await admin_client.get(f"/markets/{market.id}")

    assert response.status_code == 200
    content = response.text

    # Should show the admin settle form
    assert "Admin: Settle Market" in content
    assert 'action="/admin/markets/' in content
    assert "/settle" in content
    assert "Settlement Value" in content


@pytest.mark.asyncio
async def test_non_admin_does_not_see_settle_form(participant_client):
    """GET /markets/{id} as non-admin does not show settle form."""
    # First create a market as admin
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as admin_cl:
        await admin_cl.post(
            "/admin/login",
            data={"username": "chrson", "password": "optiver"},
            follow_redirects=False
        )
        await admin_cl.post(
            "/admin/markets",
            data={"question": "Non-admin no settle form test?"},
            follow_redirects=True
        )

    markets = await db.get_all_markets()
    market = next((m for m in markets if "Non-admin no settle form test" in m.question), None)
    assert market is not None

    # View the market page as regular participant
    response = await participant_client.get(f"/markets/{market.id}")

    assert response.status_code == 200
    content = response.text

    # Should NOT show the admin settle form
    assert "Admin: Settle Market" not in content
    # But should still show the market question (sanity check)
    assert "Non-admin no settle form test" in content


@pytest.mark.asyncio
async def test_admin_settle_form_not_shown_on_settled_market(admin_client):
    """GET /markets/{id} on SETTLED market does not show settle form."""
    # Create and settle a market
    await admin_client.post(
        "/admin/markets",
        data={"question": "Settled no form test?"},
        follow_redirects=True
    )

    markets = await db.get_all_markets()
    market = next((m for m in markets if "Settled no form test" in m.question), None)
    assert market is not None

    # Settle the market
    await admin_client.post(
        f"/admin/markets/{market.id}/settle",
        data={"settlement_value": "100"},
        follow_redirects=True
    )

    # View the market page as admin
    response = await admin_client.get(f"/markets/{market.id}")

    assert response.status_code == 200
    content = response.text

    # Should NOT show the settle form (market is already settled)
    assert "Admin: Settle Market" not in content
    # Should show link to results instead
    assert "View Results" in content


@pytest.mark.asyncio
async def test_settle_from_market_page_works(admin_client):
    """POST /admin/markets/{id}/settle from market page successfully settles."""
    # Create a market
    await admin_client.post(
        "/admin/markets",
        data={"question": "Settle from market page test?"},
        follow_redirects=True
    )

    markets = await db.get_all_markets()
    market = next((m for m in markets if "Settle from market page test" in m.question), None)
    assert market is not None
    assert market.status.value == "OPEN"

    # Place some orders
    await admin_client.post(
        f"/markets/{market.id}/orders",
        data={"side": "BID", "price": "95", "quantity": "3"},
        follow_redirects=True
    )

    # Settle directly from market page (same endpoint as admin panel)
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


# ============ Auto-redirect Tests (TODO-029) ============

@pytest.mark.asyncio
async def test_auto_redirect_on_settled_market():
    """HTMX partial returns HX-Redirect when viewing settled market."""
    transport = ASGITransport(app=app)

    # Create and settle market as admin
    async with AsyncClient(transport=transport, base_url="http://test") as admin_cl:
        await admin_cl.post(
            "/admin/login",
            data={"username": "chrson", "password": "optiver"},
            follow_redirects=False
        )

        await admin_cl.post(
            "/admin/markets",
            data={"question": "Auto-redirect test market?"},
            follow_redirects=True
        )

        markets = await db.get_all_markets()
        market = next((m for m in markets if "Auto-redirect test market" in m.question), None)
        assert market is not None

        # Settle the market
        await admin_cl.post(
            f"/admin/markets/{market.id}/settle",
            data={"settlement_value": "100"},
            follow_redirects=True
        )

    # Now as a participant, request the combined partial
    participant_id = await create_participant_and_get_id("AutoRedirectUser")
    async with AsyncClient(transport=transport, base_url="http://test") as user_cl:
        await user_cl.post(
            "/join",
            data={"participant_id": participant_id},
            follow_redirects=False
        )

        # Request the combined partial endpoint (as if HTMX polling)
        response = await user_cl.get(f"/partials/market/{market.id}")

        # Should return HX-Redirect header
        assert response.status_code == 200
        assert "HX-Redirect" in response.headers
        assert f"/markets/{market.id}/results" in response.headers["HX-Redirect"]


@pytest.mark.asyncio
async def test_no_redirect_on_open_market(admin_client):
    """HTMX partial does NOT return HX-Redirect for open market."""
    # Create a market (stays OPEN)
    await admin_client.post(
        "/admin/markets",
        data={"question": "No redirect open market test?"},
        follow_redirects=True
    )

    markets = await db.get_all_markets()
    market = next((m for m in markets if "No redirect open market test" in m.question), None)
    assert market is not None
    assert market.status.value == "OPEN"

    # Request the combined partial
    response = await admin_client.get(f"/partials/market/{market.id}")

    # Should NOT have HX-Redirect header
    assert response.status_code == 200
    assert "HX-Redirect" not in response.headers
    # Should contain the position content
    assert 'id="position-content"' in response.text


# ============ Session Exclusivity Tests (TODO-030) ============

@pytest.mark.asyncio
async def test_active_session_blocks_new_login():
    """If participant is claimed and user is active, reject new login attempt."""
    transport = ASGITransport(app=app)

    # Create a participant
    participant_id = await create_participant_and_get_id("ActiveUser")

    # First user claims the participant
    async with AsyncClient(transport=transport, base_url="http://test") as user1:
        response1 = await user1.post(
            "/join",
            data={"participant_id": participant_id},
            follow_redirects=False
        )
        assert response1.status_code == 303
        assert response1.headers["location"] == "/markets"

        # Simulate activity by polling the partial endpoint
        # First need to create a market for the partial endpoint to work
        async with AsyncClient(transport=transport, base_url="http://test") as admin_cl:
            await admin_cl.post(
                "/admin/login",
                data={"username": "chrson", "password": "optiver"},
                follow_redirects=False
            )
            await admin_cl.post(
                "/admin/markets",
                data={"question": "Activity tracking test?"},
                follow_redirects=True
            )

        markets = await db.get_all_markets()
        market = next((m for m in markets if "Activity tracking test" in m.question), None)
        assert market is not None

        # User 1 polls the partial endpoint - this updates their activity
        await user1.get(f"/partials/market/{market.id}")

    # Now another user tries to login with the same participant
    # (within the 30 second window)
    async with AsyncClient(transport=transport, base_url="http://test") as user2:
        response2 = await user2.post(
            "/join",
            data={"participant_id": participant_id},
            follow_redirects=False
        )

        # Should be rejected with error
        assert response2.status_code == 303
        assert "error=" in response2.headers["location"]
        assert "in+use" in response2.headers["location"].lower() or "already" in response2.headers["location"].lower()


@pytest.mark.asyncio
async def test_stale_session_allows_takeover():
    """If participant is claimed but user is inactive (>SESSION_ACTIVITY_TIMEOUT), allow takeover."""
    from datetime import datetime, timedelta
    from auth import SESSION_ACTIVITY_TIMEOUT

    transport = ASGITransport(app=app)

    # Create a participant
    participant_id = await create_participant_and_get_id("StaleSessionUser")

    # First user claims the participant
    async with AsyncClient(transport=transport, base_url="http://test") as user1:
        response1 = await user1.post(
            "/join",
            data={"participant_id": participant_id},
            follow_redirects=False
        )
        assert response1.status_code == 303
        assert response1.headers["location"] == "/markets"

    # Manually set the last_activity to beyond the timeout to simulate stale session
    participant = await db.get_participant_by_id(participant_id)
    assert participant is not None
    assert participant.claimed_by_user_id is not None

    stale_time = (datetime.utcnow() - timedelta(seconds=SESSION_ACTIVITY_TIMEOUT + 30)).isoformat()
    await db.database.execute(
        "UPDATE users SET last_activity = :stale WHERE id = :id",
        {"stale": stale_time, "id": participant.claimed_by_user_id}
    )

    # Now another user tries to login - should be allowed (stale session)
    async with AsyncClient(transport=transport, base_url="http://test") as user2:
        response2 = await user2.post(
            "/join",
            data={"participant_id": participant_id},
            follow_redirects=False
        )

        # Should succeed - takeover allowed
        assert response2.status_code == 303
        assert response2.headers["location"] == "/markets"
        assert "session" in response2.cookies


@pytest.mark.asyncio
async def test_activity_updates_on_partial_poll(admin_client):
    """HTMX partial endpoint updates user's last_activity timestamp."""
    from datetime import datetime, timedelta

    # Create a market
    await admin_client.post(
        "/admin/markets",
        data={"question": "Activity update test market?"},
        follow_redirects=True
    )

    markets = await db.get_all_markets()
    market = next((m for m in markets if "Activity update test market" in m.question), None)
    assert market is not None

    # Get the admin user and check their activity before
    admin_user = await db.get_user_by_name("chrson")
    assert admin_user is not None

    # Set activity to old timestamp
    old_time = (datetime.utcnow() - timedelta(seconds=60)).isoformat()
    await db.database.execute(
        "UPDATE users SET last_activity = :old WHERE id = :id",
        {"old": old_time, "id": admin_user.id}
    )

    # Verify it's old
    user_before = await db.get_user_by_id(admin_user.id)
    assert user_before.last_activity is not None
    assert (datetime.utcnow() - user_before.last_activity).total_seconds() > 30

    # Poll the partial endpoint
    response = await admin_client.get(f"/partials/market/{market.id}")
    assert response.status_code == 200

    # Check that activity was updated
    user_after = await db.get_user_by_id(admin_user.id)
    assert user_after.last_activity is not None

    # Activity should be recent (within 5 seconds)
    elapsed = (datetime.utcnow() - user_after.last_activity).total_seconds()
    assert elapsed < 5, f"Expected activity to be updated recently, but elapsed time was {elapsed}s"


@pytest.mark.asyncio
async def test_first_login_sets_activity():
    """First login (new participant claim) sets last_activity timestamp."""
    from datetime import datetime

    transport = ASGITransport(app=app)

    # Create a participant
    participant_id = await create_participant_and_get_id("FirstLoginUser")

    # Join as this participant
    async with AsyncClient(transport=transport, base_url="http://test") as user_cl:
        response = await user_cl.post(
            "/join",
            data={"participant_id": participant_id},
            follow_redirects=False
        )
        assert response.status_code == 303

    # Check that the user has last_activity set
    user = await db.get_user_by_name("FirstLoginUser")
    assert user is not None
    assert user.last_activity is not None

    # Activity should be very recent (within 5 seconds)
    elapsed = (datetime.utcnow() - user.last_activity).total_seconds()
    assert elapsed < 5


@pytest.mark.asyncio
async def test_unclaimed_participant_no_active_check():
    """Unclaimed participant can always be claimed (no active session to check)."""
    transport = ASGITransport(app=app)

    # Create TWO participants
    participant1_id = await create_participant_and_get_id("UnclaimedTestUser1")
    participant2_id = await create_participant_and_get_id("UnclaimedTestUser2")

    # First user claims participant1
    async with AsyncClient(transport=transport, base_url="http://test") as user1:
        response1 = await user1.post(
            "/join",
            data={"participant_id": participant1_id},
            follow_redirects=False
        )
        assert response1.status_code == 303

    # Second user should be able to claim the UNCLAIMED participant2
    # (regardless of participant1's activity)
    async with AsyncClient(transport=transport, base_url="http://test") as user2:
        response2 = await user2.post(
            "/join",
            data={"participant_id": participant2_id},
            follow_redirects=False
        )

        # Should succeed - different unclaimed participant
        assert response2.status_code == 303
        assert response2.headers["location"] == "/markets"


# ============ Auto-Unclaim Stale Participants Tests (TODO-031) ============

@pytest.mark.asyncio
async def test_stale_participants_auto_unclaim_on_index():
    """GET / cleans up stale participants before showing available list."""
    from datetime import datetime, timedelta
    from auth import SESSION_ACTIVITY_TIMEOUT

    transport = ASGITransport(app=app)

    # Create a participant
    participant_id = await create_participant_and_get_id("StaleAutoUnclaim")

    # Have a user claim the participant
    async with AsyncClient(transport=transport, base_url="http://test") as user1:
        response = await user1.post(
            "/join",
            data={"participant_id": participant_id},
            follow_redirects=False
        )
        assert response.status_code == 303

    # Verify participant is claimed
    participant = await db.get_participant_by_id(participant_id)
    assert participant is not None
    assert participant.claimed_by_user_id is not None

    # Make the user's session stale (beyond SESSION_ACTIVITY_TIMEOUT)
    stale_time = (datetime.utcnow() - timedelta(seconds=SESSION_ACTIVITY_TIMEOUT + 30)).isoformat()
    await db.database.execute(
        "UPDATE users SET last_activity = :stale WHERE id = :id",
        {"stale": stale_time, "id": participant.claimed_by_user_id}
    )

    # Request the index page (which triggers cleanup)
    async with AsyncClient(transport=transport, base_url="http://test") as visitor:
        response = await visitor.get("/")
        assert response.status_code == 200

    # Participant should now be unclaimed (auto-released due to stale session)
    participant_after = await db.get_participant_by_id(participant_id)
    assert participant_after is not None
    assert participant_after.claimed_by_user_id is None, \
        "Stale participant should be auto-unclaimed on index page load"


@pytest.mark.asyncio
async def test_active_participants_not_unclaimed_on_index():
    """GET / does NOT unclaim participants with recent activity."""
    from datetime import datetime, timedelta

    transport = ASGITransport(app=app)

    # Create a participant
    participant_id = await create_participant_and_get_id("ActiveNotUnclaim")

    # Have a user claim the participant
    async with AsyncClient(transport=transport, base_url="http://test") as user1:
        response = await user1.post(
            "/join",
            data={"participant_id": participant_id},
            follow_redirects=False
        )
        assert response.status_code == 303

    # Verify participant is claimed
    participant = await db.get_participant_by_id(participant_id)
    assert participant is not None
    assert participant.claimed_by_user_id is not None
    user_id = participant.claimed_by_user_id

    # Ensure the user's activity is RECENT (within timeout)
    recent_time = (datetime.utcnow() - timedelta(seconds=5)).isoformat()
    await db.database.execute(
        "UPDATE users SET last_activity = :recent WHERE id = :id",
        {"recent": recent_time, "id": user_id}
    )

    # Request the index page (which triggers cleanup)
    async with AsyncClient(transport=transport, base_url="http://test") as visitor:
        response = await visitor.get("/")
        assert response.status_code == 200

    # Participant should STILL be claimed (active session)
    participant_after = await db.get_participant_by_id(participant_id)
    assert participant_after is not None
    assert participant_after.claimed_by_user_id == user_id, \
        "Active participant should NOT be unclaimed"


@pytest.mark.asyncio
async def test_cleanup_stale_participants_returns_count():
    """cleanup_stale_participants() returns the number of participants unclaimed."""
    from datetime import datetime, timedelta

    # Create two participants
    participant1_id = await create_participant_and_get_id("CleanupCount1")
    participant2_id = await create_participant_and_get_id("CleanupCount2")

    transport = ASGITransport(app=app)

    # Have users claim both participants
    async with AsyncClient(transport=transport, base_url="http://test") as user1:
        await user1.post("/join", data={"participant_id": participant1_id}, follow_redirects=False)

    async with AsyncClient(transport=transport, base_url="http://test") as user2:
        await user2.post("/join", data={"participant_id": participant2_id}, follow_redirects=False)

    # Make both users stale
    stale_time = (datetime.utcnow() - timedelta(seconds=60)).isoformat()

    participant1 = await db.get_participant_by_id(participant1_id)
    participant2 = await db.get_participant_by_id(participant2_id)

    await db.database.execute(
        "UPDATE users SET last_activity = :stale WHERE id = :id",
        {"stale": stale_time, "id": participant1.claimed_by_user_id}
    )
    await db.database.execute(
        "UPDATE users SET last_activity = :stale WHERE id = :id",
        {"stale": stale_time, "id": participant2.claimed_by_user_id}
    )

    # Call cleanup directly
    unclaimed_count = await db.cleanup_stale_participants(timeout_seconds=30)

    # Should have unclaimed both
    assert unclaimed_count == 2

    # Verify both are now unclaimed
    p1_after = await db.get_participant_by_id(participant1_id)
    p2_after = await db.get_participant_by_id(participant2_id)
    assert p1_after.claimed_by_user_id is None
    assert p2_after.claimed_by_user_id is None


@pytest.mark.asyncio
async def test_cleanup_stale_participants_with_no_activity():
    """cleanup_stale_participants() unclaims participants whose user has NULL last_activity."""
    transport = ASGITransport(app=app)

    # Create a participant
    participant_id = await create_participant_and_get_id("NullActivityUser")

    # Have a user claim the participant
    async with AsyncClient(transport=transport, base_url="http://test") as user1:
        await user1.post("/join", data={"participant_id": participant_id}, follow_redirects=False)

    # Get the participant and user
    participant = await db.get_participant_by_id(participant_id)
    assert participant.claimed_by_user_id is not None

    # Set last_activity to NULL (simulating old data before activity tracking)
    await db.database.execute(
        "UPDATE users SET last_activity = NULL WHERE id = :id",
        {"id": participant.claimed_by_user_id}
    )

    # Call cleanup
    unclaimed_count = await db.cleanup_stale_participants(timeout_seconds=30)

    # Should have unclaimed (NULL activity is considered stale)
    assert unclaimed_count >= 1

    # Verify participant is unclaimed
    participant_after = await db.get_participant_by_id(participant_id)
    assert participant_after.claimed_by_user_id is None


# ============ One-Click Trading (Aggress) Tests ============

@pytest.mark.asyncio
async def test_aggress_offer_creates_buy():
    """POST /orders/{id}/aggress on an offer creates a buy order and matches."""
    transport = ASGITransport(app=app)

    # Create two participants
    seller_id = await create_participant_and_get_id("AggressSeller")
    buyer_id = await create_participant_and_get_id("AggressBuyer")

    async with AsyncClient(transport=transport, base_url="http://test") as seller:
        await seller.post("/join", data={"participant_id": seller_id}, follow_redirects=False)

        # Admin creates a market
        await seller.post("/admin/login", data={"username": "chrson", "password": "optiver"})
        response = await seller.post(
            "/admin/markets",
            data={"question": "Aggress test market?"},
            follow_redirects=True
        )

        # Get the market ID
        markets = await db.get_all_markets()
        market = [m for m in markets if "Aggress test" in m.question][0]

        # Seller places an offer at 50
        await seller.post(
            f"/markets/{market.id}/orders",
            data={"side": "OFFER", "price": "50", "quantity": "5"},
            follow_redirects=True
        )

    # Get the seller's order
    offers = await db.get_open_orders(market.id, side=db.OrderSide.OFFER)
    assert len(offers) == 1
    offer_id = offers[0].id

    # Buyer aggresses the offer
    async with AsyncClient(transport=transport, base_url="http://test") as buyer:
        await buyer.post("/join", data={"participant_id": buyer_id}, follow_redirects=False)

        response = await buyer.post(
            f"/orders/{offer_id}/aggress",
            data={"quantity": "3"},
            follow_redirects=False
        )

        # Should succeed
        assert response.status_code == 303

    # Check a trade happened
    trades = await db.get_recent_trades(market.id)
    assert len(trades) >= 1
    trade = trades[0]
    assert trade.quantity == 3
    assert trade.price == 50.0

    # The offer should have remaining quantity of 2
    offer_after = await db.get_order(offer_id)
    assert offer_after.remaining_quantity == 2


@pytest.mark.asyncio
async def test_aggress_bid_creates_sell():
    """POST /orders/{id}/aggress on a bid creates a sell order and matches."""
    transport = ASGITransport(app=app)

    # Create two participants
    buyer_id = await create_participant_and_get_id("AggressBidBuyer")
    seller_id = await create_participant_and_get_id("AggressBidSeller")

    async with AsyncClient(transport=transport, base_url="http://test") as buyer:
        await buyer.post("/join", data={"participant_id": buyer_id}, follow_redirects=False)

        # Admin creates a market
        await buyer.post("/admin/login", data={"username": "chrson", "password": "optiver"})
        response = await buyer.post(
            "/admin/markets",
            data={"question": "Aggress bid test market?"},
            follow_redirects=True
        )

        # Get the market ID
        markets = await db.get_all_markets()
        market = [m for m in markets if "Aggress bid test" in m.question][0]

        # Buyer places a bid at 48
        await buyer.post(
            f"/markets/{market.id}/orders",
            data={"side": "BID", "price": "48", "quantity": "4"},
            follow_redirects=True
        )

    # Get the buyer's bid order
    bids = await db.get_open_orders(market.id, side=db.OrderSide.BID)
    assert len(bids) == 1
    bid_id = bids[0].id

    # Seller aggresses the bid (sells to it)
    async with AsyncClient(transport=transport, base_url="http://test") as seller:
        await seller.post("/join", data={"participant_id": seller_id}, follow_redirects=False)

        response = await seller.post(
            f"/orders/{bid_id}/aggress",
            data={"quantity": "2"},
            follow_redirects=False
        )

        # Should succeed
        assert response.status_code == 303

    # Check a trade happened
    trades = await db.get_recent_trades(market.id)
    assert len(trades) >= 1
    trade = trades[0]
    assert trade.quantity == 2
    assert trade.price == 48.0

    # The bid should have remaining quantity of 2
    bid_after = await db.get_order(bid_id)
    assert bid_after.remaining_quantity == 2


@pytest.mark.asyncio
async def test_aggress_own_order_rejected():
    """POST /orders/{id}/aggress on your own order is rejected."""
    transport = ASGITransport(app=app)

    # Create a participant
    participant_id = await create_participant_and_get_id("AggressOwnOrder")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/join", data={"participant_id": participant_id}, follow_redirects=False)

        # Admin creates a market
        await client.post("/admin/login", data={"username": "chrson", "password": "optiver"})
        await client.post(
            "/admin/markets",
            data={"question": "Aggress own order test?"},
            follow_redirects=True
        )

        markets = await db.get_all_markets()
        market = [m for m in markets if "Aggress own order" in m.question][0]

        # Place an offer
        await client.post(
            f"/markets/{market.id}/orders",
            data={"side": "OFFER", "price": "50", "quantity": "5"},
            follow_redirects=True
        )

        # Get the order
        offers = await db.get_open_orders(market.id, side=db.OrderSide.OFFER)
        assert len(offers) == 1
        offer_id = offers[0].id

        # Try to aggress own order
        response = await client.post(
            f"/orders/{offer_id}/aggress",
            data={"quantity": "3"},
            follow_redirects=False,
            headers={"HX-Request": "true"}
        )

        # Should get error via toast header
        assert response.status_code == 200
        assert "HX-Toast-Error" in response.headers
        assert "own order" in response.headers["HX-Toast-Error"].lower()


@pytest.mark.asyncio
async def test_aggress_nonexistent_order():
    """POST /orders/{id}/aggress on a non-existent order returns error."""
    transport = ASGITransport(app=app)

    participant_id = await create_participant_and_get_id("AggressNonexistent")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/join", data={"participant_id": participant_id}, follow_redirects=False)

        # Try to aggress a fake order ID
        response = await client.post(
            "/orders/fake-order-id-12345/aggress",
            data={"quantity": "1"},
            follow_redirects=False,
            headers={"HX-Request": "true"}
        )

        # Should get error
        assert response.status_code == 200
        assert "HX-Toast-Error" in response.headers
        assert "no longer available" in response.headers["HX-Toast-Error"].lower()


@pytest.mark.asyncio
async def test_aggress_filled_order():
    """POST /orders/{id}/aggress on a filled order returns error."""
    transport = ASGITransport(app=app)

    # Create participants
    maker_id = await create_participant_and_get_id("AggressFilledMaker")
    taker1_id = await create_participant_and_get_id("AggressFilledTaker1")
    taker2_id = await create_participant_and_get_id("AggressFilledTaker2")

    async with AsyncClient(transport=transport, base_url="http://test") as maker:
        await maker.post("/join", data={"participant_id": maker_id}, follow_redirects=False)

        # Admin creates a market
        await maker.post("/admin/login", data={"username": "chrson", "password": "optiver"})
        await maker.post(
            "/admin/markets",
            data={"question": "Aggress filled order test?"},
            follow_redirects=True
        )

        markets = await db.get_all_markets()
        market = [m for m in markets if "Aggress filled order" in m.question][0]

        # Maker places a small offer
        await maker.post(
            f"/markets/{market.id}/orders",
            data={"side": "OFFER", "price": "50", "quantity": "2"},
            follow_redirects=True
        )

    offers = await db.get_open_orders(market.id, side=db.OrderSide.OFFER)
    offer_id = offers[0].id

    # First taker fills the order completely
    async with AsyncClient(transport=transport, base_url="http://test") as taker1:
        await taker1.post("/join", data={"participant_id": taker1_id}, follow_redirects=False)
        await taker1.post(
            f"/orders/{offer_id}/aggress",
            data={"quantity": "2"},
            follow_redirects=False
        )

    # Second taker tries to aggress the now-filled order
    async with AsyncClient(transport=transport, base_url="http://test") as taker2:
        await taker2.post("/join", data={"participant_id": taker2_id}, follow_redirects=False)

        response = await taker2.post(
            f"/orders/{offer_id}/aggress",
            data={"quantity": "1"},
            follow_redirects=False,
            headers={"HX-Request": "true"}
        )

        # Should get error
        assert response.status_code == 200
        assert "HX-Toast-Error" in response.headers
        assert "no longer available" in response.headers["HX-Toast-Error"].lower()


# ============ Anti-Spoofing Error Toast Tests (TODO-039) ============

@pytest.mark.asyncio
async def test_anti_spoofing_rejection_returns_error_toast():
    """POST /markets/{id}/orders with spoofing violation returns HX-Toast-Error header."""
    transport = ASGITransport(app=app)

    participant_id = await create_participant_and_get_id("SpoofingTestUser")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/join", data={"participant_id": participant_id}, follow_redirects=False)

        # Admin creates a market
        await client.post("/admin/login", data={"username": "chrson", "password": "optiver"})
        await client.post(
            "/admin/markets",
            data={"question": "Spoofing error toast test?"},
            follow_redirects=True
        )

        markets = await db.get_all_markets()
        market = [m for m in markets if "Spoofing error toast" in m.question][0]

        # Place a resting BID at 150
        await client.post(
            f"/markets/{market.id}/orders",
            data={"side": "BID", "price": "150", "quantity": "5"},
            follow_redirects=True
        )

        # Verify the bid exists
        bids = await db.get_open_orders(market.id, side=db.OrderSide.BID)
        assert len(bids) == 1
        assert bids[0].price == 150.0

        # Now try to place an OFFER at 150 (same price as bid) - should trigger spoofing rejection
        response = await client.post(
            f"/markets/{market.id}/orders",
            data={"side": "OFFER", "price": "150", "quantity": "3"},
            follow_redirects=False,
            headers={"HX-Request": "true"}  # Simulate HTMX request
        )

        # Should return success status code (200) with error header for HTMX
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}"
        assert "HX-Toast-Error" in response.headers, \
            f"Expected HX-Toast-Error header, got headers: {dict(response.headers)}"

        # Error message should mention the spoofing issue
        error_msg = response.headers["HX-Toast-Error"]
        assert "bid" in error_msg.lower() or "offer" in error_msg.lower(), \
            f"Error message should mention bid/offer: {error_msg}"


@pytest.mark.asyncio
async def test_anti_spoofing_rejection_non_htmx_returns_redirect():
    """POST /markets/{id}/orders with spoofing violation redirects with error (non-HTMX)."""
    transport = ASGITransport(app=app)

    participant_id = await create_participant_and_get_id("SpoofingRedirectUser")

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/join", data={"participant_id": participant_id}, follow_redirects=False)

        # Admin creates a market
        await client.post("/admin/login", data={"username": "chrson", "password": "optiver"})
        await client.post(
            "/admin/markets",
            data={"question": "Spoofing redirect test?"},
            follow_redirects=True
        )

        markets = await db.get_all_markets()
        market = [m for m in markets if "Spoofing redirect test" in m.question][0]

        # Place a resting OFFER at 100
        await client.post(
            f"/markets/{market.id}/orders",
            data={"side": "OFFER", "price": "100", "quantity": "5"},
            follow_redirects=True
        )

        # Try to place a BID at 100 (same price as offer) - spoofing violation
        response = await client.post(
            f"/markets/{market.id}/orders",
            data={"side": "BID", "price": "100", "quantity": "3"},
            follow_redirects=False
            # No HX-Request header - regular form submission
        )

        # Should redirect with error in URL
        assert response.status_code == 303
        assert "error=" in response.headers["location"]


@pytest.mark.asyncio
async def test_aggress_partial_fill():
    """POST /orders/{id}/aggress with more quantity than available fills what's available."""
    transport = ASGITransport(app=app)

    seller_id = await create_participant_and_get_id("AggressPartialSeller")
    buyer_id = await create_participant_and_get_id("AggressPartialBuyer")

    async with AsyncClient(transport=transport, base_url="http://test") as seller:
        await seller.post("/join", data={"participant_id": seller_id}, follow_redirects=False)

        # Admin creates a market
        await seller.post("/admin/login", data={"username": "chrson", "password": "optiver"})
        await seller.post(
            "/admin/markets",
            data={"question": "Aggress partial test?"},
            follow_redirects=True
        )

        markets = await db.get_all_markets()
        market = [m for m in markets if "Aggress partial" in m.question][0]

        # Seller places offer for 3 lots
        await seller.post(
            f"/markets/{market.id}/orders",
            data={"side": "OFFER", "price": "50", "quantity": "3"},
            follow_redirects=True
        )

    offers = await db.get_open_orders(market.id, side=db.OrderSide.OFFER)
    offer_id = offers[0].id

    # Buyer tries to aggress for 10 lots (more than available)
    async with AsyncClient(transport=transport, base_url="http://test") as buyer:
        await buyer.post("/join", data={"participant_id": buyer_id}, follow_redirects=False)

        response = await buyer.post(
            f"/orders/{offer_id}/aggress",
            data={"quantity": "10"},
            follow_redirects=False,
            headers={"HX-Request": "true"}
        )

        # Should succeed (capped at available quantity)
        assert response.status_code == 200
        assert "HX-Toast-Success" in response.headers
        # Message should indicate actual fill amount
        success_msg = response.headers["HX-Toast-Success"]
        assert "3" in success_msg  # Filled 3 lots (what was available)

    # Check order is fully filled
    offer_after = await db.get_order(offer_id)
    assert offer_after.remaining_quantity == 0


@pytest.mark.asyncio
async def test_aggress_htmx_returns_toast_success():
    """POST /orders/{id}/aggress with HX-Request header returns HX-Toast-Success header."""
    transport = ASGITransport(app=app)

    # Create two participants
    seller_id = await create_participant_and_get_id("AggressHTMXSeller")
    buyer_id = await create_participant_and_get_id("AggressHTMXBuyer")

    async with AsyncClient(transport=transport, base_url="http://test") as seller:
        await seller.post("/join", data={"participant_id": seller_id}, follow_redirects=False)

        # Admin creates a market
        await seller.post("/admin/login", data={"username": "chrson", "password": "optiver"})
        await seller.post(
            "/admin/markets",
            data={"question": "Aggress HTMX test?"},
            follow_redirects=True
        )

        markets = await db.get_all_markets()
        market = [m for m in markets if "Aggress HTMX" in m.question][0]

        # Seller places offer
        await seller.post(
            f"/markets/{market.id}/orders",
            data={"side": "OFFER", "price": "50", "quantity": "5"},
            follow_redirects=True
        )

    offers = await db.get_open_orders(market.id, side=db.OrderSide.OFFER)
    offer_id = offers[0].id

    # Buyer aggresses the offer via HTMX
    async with AsyncClient(transport=transport, base_url="http://test") as buyer:
        await buyer.post("/join", data={"participant_id": buyer_id}, follow_redirects=False)

        response = await buyer.post(
            f"/orders/{offer_id}/aggress",
            data={"quantity": "2"},
            follow_redirects=False,
            headers={"HX-Request": "true"}
        )

        # Should return 200 with toast header
        assert response.status_code == 200
        assert "HX-Toast-Success" in response.headers
        success_msg = response.headers["HX-Toast-Success"]
        # Should contain "Bought" and the price
        assert "Bought" in success_msg
        assert "50" in success_msg
