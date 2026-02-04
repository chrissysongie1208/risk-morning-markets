"""Settlement logic for the Morning Markets prediction market.

Implements:
- Linear P&L calculation: net_quantity * (settlement_value - avg_price)
- Binary P&L calculation: Per-trade lots won/lost
- Market settlement process (cancel open orders, calculate results)
"""

from typing import Optional

import database as db
from models import (
    Market, Position, Trade, MarketStatus,
    PositionWithPnL, LeaderboardEntry
)


def calculate_linear_pnl(
    net_quantity: int,
    total_cost: float,
    settlement_value: float
) -> float:
    """
    Calculate linear P&L for a position.

    Linear P&L represents the actual profit/loss amount.
    Formula: net_quantity * (settlement_value - avg_price)

    For long positions (net_quantity > 0):
        - Profit if settlement > avg_price
        - Loss if settlement < avg_price

    For short positions (net_quantity < 0):
        - Profit if settlement < avg_price
        - Loss if settlement > avg_price

    Args:
        net_quantity: The user's net position (positive=long, negative=short)
        total_cost: Sum of (price * quantity) for all fills
        settlement_value: The final settlement value of the market

    Returns:
        Linear P&L as a float
    """
    if net_quantity == 0:
        # No position means no P&L from final position
        # But if they had trades, they realized P&L already
        # This is handled by the total_cost being non-zero
        # For a flat position, P&L is the negative of total_cost
        # (e.g., bought 5 @ 100, sold 5 @ 110 -> total_cost = 500 - 550 = -50, P&L = +50)
        return -total_cost

    # Calculate average price
    avg_price = total_cost / net_quantity

    # Linear P&L = position * (settlement - avg_price)
    return net_quantity * (settlement_value - avg_price)


def calculate_binary_pnl_for_user(
    user_id: str,
    trades: list[Trade],
    settlement_value: float
) -> int:
    """
    Calculate binary P&L for a user based on their trades.

    Binary P&L counts how many lots were "won" or "lost" per trade:
    - For a BUY at price P: +quantity if settlement > P (won), -quantity if settlement < P (lost)
    - For a SELL at price P: +quantity if settlement < P (won), -quantity if settlement > P (lost)

    Example: User sold 10 @ 100, bought 5 @ 115, settlement 110
    - Sell 10 @ 100: settlement 110 > 100, so wrong side → -10
    - Buy 5 @ 115: settlement 110 < 115, so wrong side → -5
    - Total binary P&L = -15

    Args:
        user_id: The user to calculate for
        trades: All trades in the market
        settlement_value: The final settlement value

    Returns:
        Binary P&L (lots won minus lots lost)
    """
    binary_pnl = 0

    for trade in trades:
        if trade.buyer_id == user_id:
            # User was the buyer
            if settlement_value > trade.price:
                # Bought below settlement = won
                binary_pnl += trade.quantity
            elif settlement_value < trade.price:
                # Bought above settlement = lost
                binary_pnl -= trade.quantity
            # If equal, breakeven on this trade (0 contribution)

        if trade.seller_id == user_id:
            # User was the seller
            if settlement_value < trade.price:
                # Sold above settlement = won
                binary_pnl += trade.quantity
            elif settlement_value > trade.price:
                # Sold below settlement = lost
                binary_pnl -= trade.quantity
            # If equal, breakeven on this trade (0 contribution)

    return binary_pnl


async def settle_market(market_id: str, settlement_value: float) -> Market:
    """
    Settle a market with the given value.

    This process:
    1. Updates market status to SETTLED
    2. Records settlement value and timestamp
    3. Cancels all open orders

    Args:
        market_id: The market to settle
        settlement_value: The final settlement value

    Returns:
        The updated Market object

    Raises:
        ValueError: If market not found or already settled
    """
    market = await db.get_market(market_id)
    if not market:
        raise ValueError("Market not found")

    if market.status == MarketStatus.SETTLED:
        raise ValueError("Market already settled")

    # Cancel all open orders first
    await db.cancel_all_market_orders(market_id)

    # Update market to settled
    await db.settle_market(market_id, settlement_value)

    # Return updated market
    return await db.get_market(market_id)


async def get_market_results(market_id: str) -> list[PositionWithPnL]:
    """
    Get settlement results for all positions in a market.

    Args:
        market_id: The settled market

    Returns:
        List of PositionWithPnL objects with calculated P&L for each user
    """
    market = await db.get_market(market_id)
    if not market:
        return []

    if market.status != MarketStatus.SETTLED:
        return []

    settlement_value = market.settlement_value
    positions = await db.get_all_positions(market_id)
    trades = await db.get_all_trades(market_id)
    results = []

    for position in positions:
        user = await db.get_user_by_id(position.user_id)
        display_name = user.display_name if user else "Unknown"

        # Calculate linear P&L
        linear_pnl = calculate_linear_pnl(
            position.net_quantity,
            position.total_cost,
            settlement_value
        )

        # Calculate binary P&L (per-trade lots won/lost)
        binary_pnl = calculate_binary_pnl_for_user(
            position.user_id,
            trades,
            settlement_value
        )

        # Calculate average price (for display)
        avg_price = None
        if position.net_quantity != 0:
            avg_price = position.total_cost / position.net_quantity

        results.append(PositionWithPnL(
            user_id=position.user_id,
            display_name=display_name,
            net_quantity=position.net_quantity,
            total_cost=position.total_cost,
            avg_price=avg_price,
            linear_pnl=linear_pnl,
            binary_pnl=binary_pnl
        ))

    # Sort by linear P&L descending (winners first)
    results.sort(key=lambda x: x.linear_pnl or 0, reverse=True)

    return results


async def get_leaderboard() -> list[LeaderboardEntry]:
    """
    Get aggregate leaderboard across all settled markets.

    Returns:
        List of LeaderboardEntry objects sorted by total P&L descending
    """
    # Get all settled markets
    all_markets = await db.get_all_markets()
    settled_markets = [m for m in all_markets if m.status == MarketStatus.SETTLED]

    if not settled_markets:
        return []

    # Aggregate P&L by user
    user_totals: dict[str, dict] = {}

    for market in settled_markets:
        results = await get_market_results(market.id)

        for result in results:
            user_id = result.user_id

            if user_id not in user_totals:
                user_totals[user_id] = {
                    "display_name": result.display_name,
                    "total_linear_pnl": 0.0,
                    "total_binary_pnl": 0,
                    "markets_traded": 0
                }

            user_totals[user_id]["total_linear_pnl"] += result.linear_pnl or 0
            user_totals[user_id]["total_binary_pnl"] += result.binary_pnl
            user_totals[user_id]["markets_traded"] += 1

    # Convert to LeaderboardEntry objects
    entries = [
        LeaderboardEntry(
            user_id=user_id,
            display_name=data["display_name"],
            total_linear_pnl=data["total_linear_pnl"],
            total_binary_pnl=data["total_binary_pnl"],
            markets_traded=data["markets_traded"]
        )
        for user_id, data in user_totals.items()
    ]

    # Sort by total P&L descending
    entries.sort(key=lambda x: x.total_linear_pnl, reverse=True)

    return entries
