"""Unit tests for settlement logic.

Tests cover:
- Linear P&L for long positions (profit and loss)
- Linear P&L for short positions (profit and loss)
- Binary P&L calculation per-trade (lots won/lost)
- Binary result classification (WIN, LOSS, BREAKEVEN)
- Settlement cancels open orders
- Zero position with closed trades (total_cost tracking)
- Average price calculation with multiple trades
"""

import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import database as db
from settlement import (
    calculate_linear_pnl,
    calculate_binary_result,
    calculate_binary_pnl_for_user,
    settle_market,
    get_market_results
)
from models import OrderSide, OrderStatus, MarketStatus, BinaryResult, Trade
from conftest import create_resting_order, set_user_position


# ============ Pure function tests for calculate_linear_pnl ============

def test_linear_pnl_long_profit():
    """
    Given: User long 10 lots @ avg price 50
    When: Market settles at 60
    Then: Linear P&L = 10 * (60 - 50) = +100
    """
    net_quantity = 10
    total_cost = 500.0  # 10 * 50 = 500
    settlement_value = 60.0

    pnl = calculate_linear_pnl(net_quantity, total_cost, settlement_value)

    assert pnl == 100.0


def test_linear_pnl_long_loss():
    """
    Given: User long 10 lots @ avg price 50
    When: Market settles at 40
    Then: Linear P&L = 10 * (40 - 50) = -100
    """
    net_quantity = 10
    total_cost = 500.0  # 10 * 50 = 500
    settlement_value = 40.0

    pnl = calculate_linear_pnl(net_quantity, total_cost, settlement_value)

    assert pnl == -100.0


def test_linear_pnl_short_profit():
    """
    Given: User short 10 lots @ avg price 50
    When: Market settles at 40
    Then: Linear P&L = -10 * (40 - 50) = +100

    Short position: net_quantity = -10, total_cost = -500 (sold for 500)
    avg_price = -500 / -10 = 50
    P&L = -10 * (40 - 50) = -10 * -10 = +100
    """
    net_quantity = -10
    total_cost = -500.0  # Sold 10 @ 50, so negative cost
    settlement_value = 40.0

    pnl = calculate_linear_pnl(net_quantity, total_cost, settlement_value)

    assert pnl == 100.0


def test_linear_pnl_short_loss():
    """
    Given: User short 10 lots @ avg price 50
    When: Market settles at 60
    Then: Linear P&L = -10 * (60 - 50) = -100

    Short position: net_quantity = -10, total_cost = -500 (sold for 500)
    avg_price = -500 / -10 = 50
    P&L = -10 * (60 - 50) = -10 * 10 = -100
    """
    net_quantity = -10
    total_cost = -500.0  # Sold 10 @ 50
    settlement_value = 60.0

    pnl = calculate_linear_pnl(net_quantity, total_cost, settlement_value)

    assert pnl == -100.0


# ============ Pure function tests for calculate_binary_result ============

def test_binary_win():
    """
    Given: User has positive linear P&L
    Then: Binary result = WIN
    """
    assert calculate_binary_result(100.0) == BinaryResult.WIN
    assert calculate_binary_result(0.01) == BinaryResult.WIN
    assert calculate_binary_result(1000000.0) == BinaryResult.WIN


def test_binary_loss():
    """
    Given: User has negative linear P&L
    Then: Binary result = LOSS
    """
    assert calculate_binary_result(-100.0) == BinaryResult.LOSS
    assert calculate_binary_result(-0.01) == BinaryResult.LOSS
    assert calculate_binary_result(-1000000.0) == BinaryResult.LOSS


def test_binary_breakeven():
    """
    Given: User has zero linear P&L
    Then: Binary result = BREAKEVEN
    """
    assert calculate_binary_result(0.0) == BinaryResult.BREAKEVEN


# ============ Pure function tests for calculate_binary_pnl_for_user ============

def make_trade(buyer_id: str, seller_id: str, price: float, quantity: int) -> Trade:
    """Helper to create Trade objects for testing."""
    from datetime import datetime
    return Trade(
        id="test-trade",
        market_id="test-market",
        buy_order_id="buy-order",
        sell_order_id="sell-order",
        buyer_id=buyer_id,
        seller_id=seller_id,
        price=price,
        quantity=quantity,
        created_at=datetime.utcnow()
    )


def test_binary_pnl_single_winning_buy():
    """
    Given: User bought 5 lots @ 100
    When: Market settles at 110
    Then: Binary P&L = +5 (bought below settlement = won those lots)
    """
    user_id = "user-1"
    trades = [make_trade(buyer_id=user_id, seller_id="other", price=100.0, quantity=5)]
    settlement_value = 110.0

    binary_pnl = calculate_binary_pnl_for_user(user_id, trades, settlement_value)

    assert binary_pnl == 5


def test_binary_pnl_single_losing_buy():
    """
    Given: User bought 5 lots @ 100
    When: Market settles at 90
    Then: Binary P&L = -5 (bought above settlement = lost those lots)
    """
    user_id = "user-1"
    trades = [make_trade(buyer_id=user_id, seller_id="other", price=100.0, quantity=5)]
    settlement_value = 90.0

    binary_pnl = calculate_binary_pnl_for_user(user_id, trades, settlement_value)

    assert binary_pnl == -5


def test_binary_pnl_single_winning_sell():
    """
    Given: User sold 5 lots @ 100
    When: Market settles at 90
    Then: Binary P&L = +5 (sold above settlement = won those lots)
    """
    user_id = "user-1"
    trades = [make_trade(buyer_id="other", seller_id=user_id, price=100.0, quantity=5)]
    settlement_value = 90.0

    binary_pnl = calculate_binary_pnl_for_user(user_id, trades, settlement_value)

    assert binary_pnl == 5


def test_binary_pnl_single_losing_sell():
    """
    Given: User sold 5 lots @ 100
    When: Market settles at 110
    Then: Binary P&L = -5 (sold below settlement = lost those lots)
    """
    user_id = "user-1"
    trades = [make_trade(buyer_id="other", seller_id=user_id, price=100.0, quantity=5)]
    settlement_value = 110.0

    binary_pnl = calculate_binary_pnl_for_user(user_id, trades, settlement_value)

    assert binary_pnl == -5


def test_binary_pnl_multiple_trades():
    """
    Given: User sold 10 lots @ 100, bought 5 lots @ 115
    When: Market settles at 110
    Then: Binary P&L = -10 (sold below settlement) + -5 (bought above settlement) = -15
    """
    user_id = "user-1"
    trades = [
        make_trade(buyer_id="other", seller_id=user_id, price=100.0, quantity=10),  # Sell 10 @ 100
        make_trade(buyer_id=user_id, seller_id="other2", price=115.0, quantity=5),   # Buy 5 @ 115
    ]
    settlement_value = 110.0

    binary_pnl = calculate_binary_pnl_for_user(user_id, trades, settlement_value)

    # Sell 10 @ 100: settlement 110 > 100 → lost 10
    # Buy 5 @ 115: settlement 110 < 115 → lost 5
    # Total = -15
    assert binary_pnl == -15


def test_binary_pnl_breakeven_trade():
    """
    Given: User bought 5 lots at exactly the settlement price
    When: Market settles at 100
    Then: Binary P&L = 0 (trade at settlement price = breakeven)
    """
    user_id = "user-1"
    trades = [make_trade(buyer_id=user_id, seller_id="other", price=100.0, quantity=5)]
    settlement_value = 100.0

    binary_pnl = calculate_binary_pnl_for_user(user_id, trades, settlement_value)

    assert binary_pnl == 0


def test_binary_pnl_mixed_wins_losses():
    """
    Given: User bought 10 @ 90 (win), sold 5 @ 85 (loss), bought 3 @ 105 (loss)
    When: Market settles at 100
    Then: Binary P&L = +10 - 5 - 3 = +2
    """
    user_id = "user-1"
    trades = [
        make_trade(buyer_id=user_id, seller_id="other", price=90.0, quantity=10),   # Buy 10 @ 90 → +10
        make_trade(buyer_id="other", seller_id=user_id, price=85.0, quantity=5),    # Sell 5 @ 85 → -5
        make_trade(buyer_id=user_id, seller_id="other2", price=105.0, quantity=3),  # Buy 3 @ 105 → -3
    ]
    settlement_value = 100.0

    binary_pnl = calculate_binary_pnl_for_user(user_id, trades, settlement_value)

    assert binary_pnl == 2


def test_binary_pnl_no_trades():
    """
    Given: User has no trades
    When: Market settles
    Then: Binary P&L = 0
    """
    user_id = "user-1"
    trades = []
    settlement_value = 100.0

    binary_pnl = calculate_binary_pnl_for_user(user_id, trades, settlement_value)

    assert binary_pnl == 0


def test_binary_pnl_ignores_other_users_trades():
    """
    Given: Trades exist between other users (not the target user)
    When: Calculating binary P&L for target user
    Then: Binary P&L = 0 (only counts user's trades)
    """
    user_id = "user-1"
    trades = [
        make_trade(buyer_id="other1", seller_id="other2", price=100.0, quantity=10),
        make_trade(buyer_id="other2", seller_id="other3", price=105.0, quantity=5),
    ]
    settlement_value = 110.0

    binary_pnl = calculate_binary_pnl_for_user(user_id, trades, settlement_value)

    assert binary_pnl == 0


# ============ Integration tests for settle_market ============

@pytest.mark.asyncio
async def test_settlement_cancels_open_orders(market, user_alice, user_bob):
    """
    Given: Market has open orders
    When: Market is settled
    Then: All open orders cancelled
    """
    # Setup: Create some open orders
    await create_resting_order(market.id, user_alice.id, OrderSide.BID, 100.0, 5)
    await create_resting_order(market.id, user_bob.id, OrderSide.OFFER, 110.0, 3)

    # Verify orders exist and are open
    open_orders_before = await db.get_open_orders(market.id)
    assert len(open_orders_before) == 2

    # Action: Settle the market
    await settle_market(market.id, 105.0)

    # Assert: All orders should be cancelled
    open_orders_after = await db.get_open_orders(market.id)
    assert len(open_orders_after) == 0

    # Verify orders are cancelled (not deleted)
    alice_order = await db.get_order(open_orders_before[0].id)
    bob_order = await db.get_order(open_orders_before[1].id)
    assert alice_order.status == OrderStatus.CANCELLED
    assert bob_order.status == OrderStatus.CANCELLED


@pytest.mark.asyncio
async def test_zero_position_no_pnl(market, user_alice):
    """
    Given: User has 0 net position (bought and sold equal amounts)
    When: Market settles
    Then: P&L calculated on closed trades, not just final position

    Example: User buys 5 @ 100 (cost +500), sells 5 @ 110 (cost -550)
    Net quantity = 0, total_cost = 500 - 550 = -50
    Since position is flat, P&L = -total_cost = -(-50) = +50
    """
    # Setup: User has zero position but made a profit on round-trip
    # Bought 5 @ 100, sold 5 @ 110 -> profit of 50
    # net_quantity = 0, total_cost = -50 (because sold for more than bought)
    await set_user_position(market.id, user_alice.id, net_quantity=0, total_cost=-50.0)

    # Settle market (settlement value doesn't matter for flat positions)
    await settle_market(market.id, 120.0)

    # Get results
    results = await get_market_results(market.id)

    # Find Alice's result
    alice_result = next((r for r in results if r.user_id == user_alice.id), None)
    assert alice_result is not None

    # P&L should be +50 (the profit from the round-trip)
    assert alice_result.linear_pnl == 50.0
    assert alice_result.binary_result == BinaryResult.WIN


@pytest.mark.asyncio
async def test_average_price_multiple_trades(market, user_alice):
    """
    Given: User buys 5 @ 100, then buys 5 @ 110
    Then: Average price = (5*100 + 5*110) / 10 = 105
    When: Settles at 120
    Then: P&L = 10 * (120 - 105) = +150
    """
    # Setup: User has position from two trades at different prices
    # Trade 1: Buy 5 @ 100 -> position +5, cost +500
    # Trade 2: Buy 5 @ 110 -> position +10, cost +1050
    # Average price = 1050 / 10 = 105
    await set_user_position(market.id, user_alice.id, net_quantity=10, total_cost=1050.0)

    # Settle at 120
    await settle_market(market.id, 120.0)

    # Get results
    results = await get_market_results(market.id)

    # Find Alice's result
    alice_result = next((r for r in results if r.user_id == user_alice.id), None)
    assert alice_result is not None

    # Average price should be 105
    assert alice_result.avg_price == 105.0

    # P&L = 10 * (120 - 105) = 150
    assert alice_result.linear_pnl == 150.0
    assert alice_result.binary_result == BinaryResult.WIN


@pytest.mark.asyncio
async def test_settlement_updates_market_status(market):
    """Test that settling updates market status to SETTLED."""
    # Market starts as OPEN
    assert market.status == MarketStatus.OPEN

    # Settle the market
    settled_market = await settle_market(market.id, 100.0)

    # Market should now be SETTLED
    assert settled_market.status == MarketStatus.SETTLED
    assert settled_market.settlement_value == 100.0
    assert settled_market.settled_at is not None


@pytest.mark.asyncio
async def test_settlement_already_settled_raises_error(market):
    """Test that settling an already settled market raises an error."""
    # Settle the market first
    await settle_market(market.id, 100.0)

    # Try to settle again
    with pytest.raises(ValueError, match="already settled"):
        await settle_market(market.id, 110.0)


@pytest.mark.asyncio
async def test_settlement_results_sorted_by_pnl(market, user_alice, user_bob, user_charlie):
    """Test that settlement results are sorted by P&L descending (winners first)."""
    # Setup positions with different P&L outcomes
    # Alice: Long 10 @ 50, settles at 60 -> P&L = +100
    await set_user_position(market.id, user_alice.id, net_quantity=10, total_cost=500.0)
    # Bob: Long 10 @ 70, settles at 60 -> P&L = -100
    await set_user_position(market.id, user_bob.id, net_quantity=10, total_cost=700.0)
    # Charlie: Long 5 @ 60, settles at 60 -> P&L = 0 (breakeven)
    await set_user_position(market.id, user_charlie.id, net_quantity=5, total_cost=300.0)

    # Settle at 60
    await settle_market(market.id, 60.0)

    # Get results
    results = await get_market_results(market.id)

    # Results should be sorted by P&L descending
    assert len(results) == 3
    assert results[0].user_id == user_alice.id  # +100 (best)
    assert results[0].linear_pnl == 100.0
    assert results[1].user_id == user_charlie.id  # 0 (middle)
    assert results[1].linear_pnl == 0.0
    assert results[2].user_id == user_bob.id  # -100 (worst)
    assert results[2].linear_pnl == -100.0


@pytest.mark.asyncio
async def test_get_market_results_empty_for_unsettled_market(market):
    """Test that get_market_results returns empty list for unsettled markets."""
    # Market is not settled
    results = await get_market_results(market.id)
    assert results == []


@pytest.mark.asyncio
async def test_get_market_results_nonexistent_market():
    """Test that get_market_results returns empty list for nonexistent market."""
    results = await get_market_results("nonexistent-market-id")
    assert results == []
