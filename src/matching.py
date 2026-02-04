"""Matching engine for the Morning Markets prediction market.

Implements price-time priority order matching with:
- Cross detection (bid >= best offer price triggers match)
- Position limit enforcement (including open order exposure)
- Self-trade prevention (user can't trade against themselves)
"""

from dataclasses import dataclass
from typing import Optional

import database as db
from models import Order, OrderSide, OrderStatus, MarketStatus, Trade


class PositionLimitExceeded(Exception):
    """Raised when an order would exceed the position limit."""
    pass


class MarketNotOpen(Exception):
    """Raised when trying to place an order on a non-OPEN market."""
    pass


class SpoofingRejected(Exception):
    """Raised when an order would cross the user's own resting orders."""
    pass


@dataclass
class MatchResult:
    """Result of attempting to place an order."""
    order: Optional[Order]  # The resting order (if any remaining quantity)
    trades: list[Trade]     # Trades that were executed
    fully_filled: bool      # True if entire order quantity was filled
    rejected: bool          # True if order was rejected (e.g., position limit)
    reject_reason: Optional[str] = None


async def check_spoofing(
    market_id: str,
    user_id: str,
    side: OrderSide,
    price: float
) -> tuple[bool, str]:
    """
    Check if placing an order would cross the user's own resting orders (spoofing).

    Anti-spoofing rules:
    - BID at price P: reject if user has any OFFER at price <= P
    - OFFER at price P: reject if user has any BID at price >= P

    This prevents users from manipulating the market by placing orders on both
    sides that would immediately cross if placed by different users.

    Returns:
        Tuple of (allowed: bool, reason: str if rejected)
    """
    if side == OrderSide.BID:
        # Check if user has any offers at or below this bid price
        user_offers = await db.get_open_orders(market_id, side=OrderSide.OFFER)
        user_offers = [o for o in user_offers if o.user_id == user_id and o.price <= price]
        if user_offers:
            best_offer = min(o.price for o in user_offers)
            return False, f"Cannot bid at {price} when you have an offer at {best_offer}"
    else:
        # Check if user has any bids at or above this offer price
        user_bids = await db.get_open_orders(market_id, side=OrderSide.BID)
        user_bids = [o for o in user_bids if o.user_id == user_id and o.price >= price]
        if user_bids:
            best_bid = max(o.price for o in user_bids)
            return False, f"Cannot offer at {price} when you have a bid at {best_bid}"

    return True, ""


async def check_position_limit(
    market_id: str,
    user_id: str,
    side: OrderSide,
    quantity: int,
    position_limit: int
) -> tuple[bool, str]:
    """
    Check if placing an order would violate position limits.

    Position limits consider:
    1. Current net position (from filled trades)
    2. Open order exposure (potential position change from resting orders)

    The worst-case position is calculated as:
    - Max long = position + open_bids
    - Max short = position - open_offers

    For a new order:
    - BID: max_long_after = position + open_bids + quantity
    - OFFER: max_short_after = position - open_offers - quantity

    Returns:
        Tuple of (allowed: bool, reason: str if rejected)
    """
    position = await db.get_position(market_id, user_id)
    bid_exposure, offer_exposure = await db.get_user_open_order_exposure(market_id, user_id)

    current_pos = position.net_quantity

    if side == OrderSide.BID:
        # Adding a bid - check max long position
        # Worst case: all bids fill (including this one)
        max_long_after = current_pos + bid_exposure + quantity
        if max_long_after > position_limit:
            max_allowed = position_limit - current_pos - bid_exposure
            if max_allowed <= 0:
                return False, f"Position limit ({position_limit}) exceeded. Current position: {current_pos}, open bids: {bid_exposure}"
            return False, f"Position limit ({position_limit}) exceeded. Max buy: {max_allowed}"
    else:
        # Adding an offer - check max short position
        # Worst case: all offers fill (including this one)
        max_short_after = current_pos - offer_exposure - quantity
        if max_short_after < -position_limit:
            max_allowed = current_pos + offer_exposure + position_limit
            if max_allowed <= 0:
                return False, f"Position limit ({position_limit}) exceeded. Current position: {current_pos}, open offers: {offer_exposure}"
            return False, f"Position limit ({position_limit}) exceeded. Max sell: {max_allowed}"

    return True, ""


async def place_order(
    market_id: str,
    user_id: str,
    side: OrderSide,
    price: float,
    quantity: int
) -> MatchResult:
    """
    Place an order and attempt to match it against the order book.

    Matching rules:
    - Price-time priority: orders match at the maker's (resting order's) price
    - For BID: matches against OFFERs at or below the bid price (best offer first)
    - For OFFER: matches against BIDs at or above the offer price (best bid first)
    - Self-trade prevention: skip orders from the same user
    - Position limit: considers both current position AND open order exposure

    Returns:
        MatchResult with the outcome of the order placement
    """
    # 1. Validate market is open
    market = await db.get_market(market_id)
    if not market or market.status != MarketStatus.OPEN:
        raise MarketNotOpen("Market is not open for trading")

    # 2. Get position limit
    position_limit = await db.get_position_limit()

    # 3. Check position limit (considering open order exposure)
    allowed, reject_reason = await check_position_limit(
        market_id, user_id, side, quantity, position_limit
    )
    if not allowed:
        return MatchResult(
            order=None,
            trades=[],
            fully_filled=False,
            rejected=True,
            reject_reason=reject_reason
        )

    # 4. Check for spoofing (order crossing user's own orders)
    allowed, reject_reason = await check_spoofing(market_id, user_id, side, price)
    if not allowed:
        return MatchResult(
            order=None,
            trades=[],
            fully_filled=False,
            rejected=True,
            reject_reason=reject_reason
        )

    # 5. Get current position for tracking during matching
    position = await db.get_position(market_id, user_id)

    # 6. Get matching orders from the book (excluding self)
    if side == OrderSide.BID:
        # Looking for offers at or below my bid price
        counter_orders = await db.get_open_orders(
            market_id,
            side=OrderSide.OFFER,
            exclude_user_id=user_id
        )
        # Filter to only offers at or below our bid price
        counter_orders = [o for o in counter_orders if o.price <= price]
    else:
        # Looking for bids at or above my offer price
        counter_orders = await db.get_open_orders(
            market_id,
            side=OrderSide.BID,
            exclude_user_id=user_id
        )
        # Filter to only bids at or above our offer price
        counter_orders = [o for o in counter_orders if o.price >= price]

    # 7. Create the incoming order first (needed for trade foreign key constraints)
    # This order will track its remaining quantity as matches happen
    incoming_order = await db.create_order(
        market_id=market_id,
        user_id=user_id,
        side=side,
        price=price,
        quantity=quantity
    )

    # 8. Match against counter orders
    remaining_quantity = quantity
    trades = []
    current_position = position.net_quantity

    for counter_order in counter_orders:
        if remaining_quantity <= 0:
            break

        # Calculate fill quantity
        fill_qty = min(remaining_quantity, counter_order.remaining_quantity)

        # Check position limit after this fill
        fill_delta = fill_qty if side == OrderSide.BID else -fill_qty
        new_position = current_position + fill_delta

        # For fills, we check against the actual position (not including other open orders)
        # because fills reduce open order exposure while changing position
        if abs(new_position) > position_limit:
            # Partial fill limited by position
            if side == OrderSide.BID:
                max_fill = position_limit - current_position
            else:
                max_fill = current_position + position_limit

            if max_fill <= 0:
                break  # Can't fill any more

            fill_qty = min(fill_qty, max_fill)

        if fill_qty <= 0:
            break

        # Execute the trade at maker's price
        fill_price = counter_order.price

        # Determine buyer and seller
        if side == OrderSide.BID:
            buyer_id = user_id
            seller_id = counter_order.user_id
            buy_order_id = incoming_order.id
            sell_order_id = counter_order.id
        else:
            buyer_id = counter_order.user_id
            seller_id = user_id
            buy_order_id = counter_order.id
            sell_order_id = incoming_order.id

        # Create trade record
        trade = await db.create_trade(
            market_id=market_id,
            buy_order_id=buy_order_id,
            sell_order_id=sell_order_id,
            buyer_id=buyer_id,
            seller_id=seller_id,
            price=fill_price,
            quantity=fill_qty
        )
        trades.append(trade)

        # Update positions
        # Buyer: +quantity, +cost (buying at fill_price)
        await db.update_position(
            market_id=market_id,
            user_id=buyer_id,
            quantity_delta=fill_qty,
            cost_delta=fill_qty * fill_price
        )
        # Seller: -quantity, -cost (selling at fill_price)
        await db.update_position(
            market_id=market_id,
            user_id=seller_id,
            quantity_delta=-fill_qty,
            cost_delta=-fill_qty * fill_price
        )

        # Update counter order
        new_remaining = counter_order.remaining_quantity - fill_qty
        await db.update_order_quantity(counter_order.id, new_remaining)

        # Update tracking
        remaining_quantity -= fill_qty
        current_position += fill_delta

    # 9. Update incoming order with final remaining quantity
    await db.update_order_quantity(incoming_order.id, remaining_quantity)

    # Return the resting order (if any quantity remains) or None if fully filled
    resting_order = None
    if remaining_quantity > 0:
        # Refresh the order to get updated state
        resting_order = await db.get_order(incoming_order.id)

    return MatchResult(
        order=resting_order,
        trades=trades,
        fully_filled=(remaining_quantity == 0),
        rejected=False
    )


async def cancel_order(order_id: str, user_id: str) -> bool:
    """
    Cancel an order.

    Args:
        order_id: The order to cancel
        user_id: The user requesting cancellation (must own the order)

    Returns:
        True if cancelled successfully, False if order not found or not owned

    Raises:
        ValueError if order belongs to another user
    """
    order = await db.get_order(order_id)

    if not order:
        return False

    if order.user_id != user_id:
        raise ValueError("Cannot cancel another user's order")

    if order.status != OrderStatus.OPEN:
        return False  # Already filled or cancelled

    await db.cancel_order(order_id)
    return True
