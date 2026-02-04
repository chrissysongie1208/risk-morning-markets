"""Unit tests for the matching engine.

Tests cover:
- Exact match
- Partial fill
- No match when bid below offer
- Price improvement (taker gets maker's price)
- Multiple fills across price levels
- Time priority at same price
- Position limit rejection
- Position limit allows reducing orders
- Position limit after partial fill
- Self-trade prevention
"""

import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import database as db
from matching import place_order, PositionLimitExceeded, MarketNotOpen
from models import OrderSide, OrderStatus
from conftest import create_resting_order, set_user_position


@pytest.mark.asyncio
async def test_exact_match(market, user_alice, user_bob):
    """
    Given: Offer at 100 for 5 lots exists
    When: Bid at 100 for 5 lots placed
    Then: Full match, trade at 100, both orders filled
    """
    # Setup: Alice places offer at 100 for 5 lots
    await create_resting_order(market.id, user_alice.id, OrderSide.OFFER, 100.0, 5)

    # Action: Bob places bid at 100 for 5 lots
    result = await place_order(market.id, user_bob.id, OrderSide.BID, 100.0, 5)

    # Assert
    assert result.fully_filled is True
    assert result.rejected is False
    assert result.order is None  # No resting order
    assert len(result.trades) == 1

    trade = result.trades[0]
    assert trade.price == 100.0
    assert trade.quantity == 5
    assert trade.buyer_id == user_bob.id
    assert trade.seller_id == user_alice.id

    # Check positions
    alice_pos = await db.get_position(market.id, user_alice.id)
    bob_pos = await db.get_position(market.id, user_bob.id)
    assert alice_pos.net_quantity == -5  # Alice sold
    assert bob_pos.net_quantity == 5  # Bob bought


@pytest.mark.asyncio
async def test_partial_fill(market, user_alice, user_bob):
    """
    Given: Offer at 100 for 3 lots exists
    When: Bid at 100 for 10 lots placed
    Then: Partial match (3 lots at 100), bid has 7 lots resting
    """
    # Setup: Alice places offer at 100 for 3 lots
    await create_resting_order(market.id, user_alice.id, OrderSide.OFFER, 100.0, 3)

    # Action: Bob places bid at 100 for 10 lots
    result = await place_order(market.id, user_bob.id, OrderSide.BID, 100.0, 10)

    # Assert
    assert result.fully_filled is False
    assert result.rejected is False
    assert result.order is not None  # Has resting order
    assert result.order.remaining_quantity == 7
    assert result.order.price == 100.0
    assert len(result.trades) == 1

    trade = result.trades[0]
    assert trade.price == 100.0
    assert trade.quantity == 3

    # Check positions
    alice_pos = await db.get_position(market.id, user_alice.id)
    bob_pos = await db.get_position(market.id, user_bob.id)
    assert alice_pos.net_quantity == -3  # Alice sold 3
    assert bob_pos.net_quantity == 3  # Bob bought 3


@pytest.mark.asyncio
async def test_no_match_bid_below_offer(market, user_alice, user_bob):
    """
    Given: Offer at 100 for 5 lots exists
    When: Bid at 90 for 5 lots placed
    Then: No match, both orders rest in book
    """
    # Setup: Alice places offer at 100 for 5 lots
    await create_resting_order(market.id, user_alice.id, OrderSide.OFFER, 100.0, 5)

    # Action: Bob places bid at 90 for 5 lots (below offer)
    result = await place_order(market.id, user_bob.id, OrderSide.BID, 90.0, 5)

    # Assert
    assert result.fully_filled is False
    assert result.rejected is False
    assert result.order is not None  # Has resting order
    assert result.order.remaining_quantity == 5
    assert result.order.price == 90.0
    assert len(result.trades) == 0  # No trades

    # Check positions - should be zero (no trades)
    alice_pos = await db.get_position(market.id, user_alice.id)
    bob_pos = await db.get_position(market.id, user_bob.id)
    assert alice_pos.net_quantity == 0
    assert bob_pos.net_quantity == 0


@pytest.mark.asyncio
async def test_price_improvement(market, user_alice, user_bob):
    """
    Given: Offer at 100 for 5 lots exists
    When: Bid at 110 for 5 lots placed
    Then: Match at 100 (maker's price), not 110
    """
    # Setup: Alice places offer at 100 for 5 lots
    await create_resting_order(market.id, user_alice.id, OrderSide.OFFER, 100.0, 5)

    # Action: Bob places bid at 110 for 5 lots (above offer - aggressive)
    result = await place_order(market.id, user_bob.id, OrderSide.BID, 110.0, 5)

    # Assert
    assert result.fully_filled is True
    assert len(result.trades) == 1

    trade = result.trades[0]
    assert trade.price == 100.0  # Maker's price, not 110
    assert trade.quantity == 5

    # Check positions - Bob got price improvement
    bob_pos = await db.get_position(market.id, user_bob.id)
    assert bob_pos.net_quantity == 5
    assert bob_pos.total_cost == 500.0  # 5 * 100, not 5 * 110


@pytest.mark.asyncio
async def test_multiple_fills(market, user_alice, user_bob, user_charlie):
    """
    Given: Offers at 100 (3 lots), 101 (3 lots), 102 (3 lots)
    When: Bid at 102 for 8 lots placed
    Then: Fills 3@100, 3@101, 2@102 = 8 lots total, fully filled.
    """
    # Setup: Create offers at different price levels
    await create_resting_order(market.id, user_alice.id, OrderSide.OFFER, 100.0, 3)
    await create_resting_order(market.id, user_bob.id, OrderSide.OFFER, 101.0, 3)
    await create_resting_order(market.id, user_charlie.id, OrderSide.OFFER, 102.0, 3)

    # Need another user for the aggressive bid
    user_dave = await db.create_user("Dave")

    # Action: Dave places bid at 102 for 8 lots
    result = await place_order(market.id, user_dave.id, OrderSide.BID, 102.0, 8)

    # Assert - 3+3+2 = 8 lots, fully filled
    assert result.fully_filled is True
    assert result.rejected is False
    assert len(result.trades) == 3  # Three separate fills

    # Trades should be in price order (best first)
    assert result.trades[0].price == 100.0
    assert result.trades[0].quantity == 3
    assert result.trades[1].price == 101.0
    assert result.trades[1].quantity == 3
    assert result.trades[2].price == 102.0
    assert result.trades[2].quantity == 2

    # No resting order since all 8 lots filled
    assert result.order is None

    # Check Dave's position
    dave_pos = await db.get_position(market.id, user_dave.id)
    assert dave_pos.net_quantity == 8
    # Total cost: 3*100 + 3*101 + 2*102 = 300 + 303 + 204 = 807
    assert dave_pos.total_cost == 807.0


@pytest.mark.asyncio
async def test_time_priority(market, user_alice, user_bob, user_charlie):
    """
    Given: Two offers at 100, first for 3 lots, second for 3 lots
    When: Bid at 100 for 4 lots placed
    Then: First offer fully filled, second partially (1 lot)
    """
    # Setup: Alice places first offer, then Bob places second offer (both at 100)
    await create_resting_order(market.id, user_alice.id, OrderSide.OFFER, 100.0, 3)
    await create_resting_order(market.id, user_bob.id, OrderSide.OFFER, 100.0, 3)

    # Action: Charlie places bid at 100 for 4 lots
    result = await place_order(market.id, user_charlie.id, OrderSide.BID, 100.0, 4)

    # Assert
    assert result.fully_filled is True
    assert len(result.trades) == 2

    # First trade should be with Alice (time priority)
    assert result.trades[0].seller_id == user_alice.id
    assert result.trades[0].quantity == 3  # Fully filled

    # Second trade should be with Bob (partial)
    assert result.trades[1].seller_id == user_bob.id
    assert result.trades[1].quantity == 1  # Partially filled

    # Check positions
    alice_pos = await db.get_position(market.id, user_alice.id)
    bob_pos = await db.get_position(market.id, user_bob.id)
    charlie_pos = await db.get_position(market.id, user_charlie.id)

    assert alice_pos.net_quantity == -3  # Alice sold all 3
    assert bob_pos.net_quantity == -1  # Bob sold 1
    assert charlie_pos.net_quantity == 4  # Charlie bought 4


@pytest.mark.asyncio
async def test_position_limit_rejects_order(market, user_alice, user_bob):
    """
    Given: User has +18 position, limit is 20
    When: User places bid for 5 lots
    Then: Order rejected (would result in +23 position)
    """
    # Setup: Set position limit to 20 and give Alice a +18 position
    await db.set_position_limit(20)
    await set_user_position(market.id, user_alice.id, 18, 1800.0)

    # Create an offer for Alice to buy against (not strictly needed but good for completeness)
    await create_resting_order(market.id, user_bob.id, OrderSide.OFFER, 100.0, 10)

    # Action: Alice tries to place bid for 5 lots (would result in +23 if filled)
    result = await place_order(market.id, user_alice.id, OrderSide.BID, 100.0, 5)

    # Assert
    assert result.rejected is True
    assert result.reject_reason is not None
    assert "limit" in result.reject_reason.lower() or "exceeded" in result.reject_reason.lower()
    assert len(result.trades) == 0

    # Position should remain unchanged
    alice_pos = await db.get_position(market.id, user_alice.id)
    assert alice_pos.net_quantity == 18


@pytest.mark.asyncio
async def test_position_limit_allows_reducing_order(market, user_alice, user_bob):
    """
    Given: User has +18 position, limit is 20
    When: User places offer for 5 lots
    Then: Order accepted (would result in +13 position)
    """
    # Setup: Set position limit to 20 and give Alice a +18 position
    await db.set_position_limit(20)
    await set_user_position(market.id, user_alice.id, 18, 1800.0)

    # Action: Alice places offer for 5 lots (reducing position to +13)
    result = await place_order(market.id, user_alice.id, OrderSide.OFFER, 100.0, 5)

    # Assert
    assert result.rejected is False
    assert result.order is not None  # Order rests in book
    assert result.order.remaining_quantity == 5


@pytest.mark.asyncio
async def test_position_limit_after_partial_fill(market, user_alice, user_bob):
    """
    Given: User has +15 position, limit is 20, offer exists for 10 lots
    When: User places bid for 10 lots
    Then: Fills 5 lots (to +20), remaining 5 rejected or not posted
    """
    # Setup: Set position limit to 20, give Alice +15 position
    await db.set_position_limit(20)
    await set_user_position(market.id, user_alice.id, 15, 1500.0)

    # Bob has offer for 10 lots
    await create_resting_order(market.id, user_bob.id, OrderSide.OFFER, 100.0, 10)

    # Action: Alice places bid for 10 lots
    result = await place_order(market.id, user_alice.id, OrderSide.BID, 100.0, 10)

    # The order is rejected upfront because position + open orders would exceed limit
    # Alice at +15, trying to add bid for 10 -> max long would be +25, which exceeds 20
    assert result.rejected is True

    # Position should remain at 15 (no fills)
    alice_pos = await db.get_position(market.id, user_alice.id)
    assert alice_pos.net_quantity == 15


@pytest.mark.asyncio
async def test_self_trade_prevention(market, user_alice):
    """
    Given: User A has offer at 100
    When: User A places bid at 100
    Then: No self-match occurs, bid rests in book
    """
    # Setup: Alice places offer at 100 for 5 lots
    await create_resting_order(market.id, user_alice.id, OrderSide.OFFER, 100.0, 5)

    # Action: Alice places bid at 100 for 5 lots (same user!)
    result = await place_order(market.id, user_alice.id, OrderSide.BID, 100.0, 5)

    # Assert
    assert result.rejected is False
    assert len(result.trades) == 0  # No self-trade
    assert result.order is not None  # Bid rests in book
    assert result.order.remaining_quantity == 5

    # Check position - should be zero (no trades)
    alice_pos = await db.get_position(market.id, user_alice.id)
    assert alice_pos.net_quantity == 0

    # Both orders should still be in the book
    open_orders = await db.get_open_orders(market.id)
    assert len(open_orders) == 2  # Both offer and bid


@pytest.mark.asyncio
async def test_market_not_open_rejects_order(market, user_alice):
    """Test that orders are rejected on closed markets."""
    from models import MarketStatus

    # Close the market
    await db.update_market_status(market.id, MarketStatus.CLOSED)

    # Try to place an order
    with pytest.raises(MarketNotOpen):
        await place_order(market.id, user_alice.id, OrderSide.BID, 100.0, 5)
