"""Main FastAPI application for Morning Markets prediction market."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from fastapi import FastAPI, Request, Form, Cookie, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from websocket import manager as ws_manager

import database as db
import auth
import matching
import settlement
from models import MarketStatus, OrderSide, OrderStatus, OrderWithUser, TradeWithUsers, PositionWithPnL

# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=TEMPLATE_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup, cleanup on shutdown."""
    await db.connect_db()
    await db.init_db()
    yield
    await db.disconnect_db()


app = FastAPI(title="Morning Markets", lifespan=lifespan)


# ============ Helper Functions ============

def set_session_cookie(response: RedirectResponse, token: str) -> RedirectResponse:
    """Set the session cookie on a response."""
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7  # 7 days
    )
    return response


# ============ Landing Page ============

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, session: Optional[str] = Cookie(None), error: Optional[str] = None):
    """Landing page with join/login options."""
    user = await auth.get_current_user(session)

    # If already logged in, redirect to markets
    if user:
        return RedirectResponse(url="/markets", status_code=status.HTTP_303_SEE_OTHER)

    # Cleanup stale participants before showing available list
    # This auto-releases participants whose users have been inactive
    await db.cleanup_stale_participants(auth.SESSION_ACTIVITY_TIMEOUT)

    # Get available (unclaimed) participants for dropdown
    available_participants = await db.get_available_participants()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": None,
            "error": error,
            "participants": available_participants
        }
    )


# ============ Participant Join ============

@app.post("/join")
async def join(participant_id: str = Form(...)):
    """Join as a participant by selecting a pre-registered name."""
    participant_id = participant_id.strip()

    if not participant_id:
        return RedirectResponse(
            url="/?error=Please select a participant name",
            status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        user, token = await auth.login_participant(participant_id)
        response = RedirectResponse(url="/markets", status_code=status.HTTP_303_SEE_OTHER)
        return set_session_cookie(response, token)
    except ValueError as e:
        return RedirectResponse(
            url=f"/?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER
        )


# ============ Admin Login ============

@app.post("/admin/login")
async def admin_login(username: str = Form(...), password: str = Form(...)):
    """Login as admin."""
    try:
        user, token = await auth.login_admin(username, password)
        response = RedirectResponse(url="/markets", status_code=status.HTTP_303_SEE_OTHER)
        return set_session_cookie(response, token)
    except ValueError:
        return RedirectResponse(
            url="/?error=Invalid admin credentials",
            status_code=status.HTTP_303_SEE_OTHER
        )


# ============ Current User Info ============

@app.get("/me")
async def get_me(session: Optional[str] = Cookie(None)):
    """Get current user info as JSON."""
    user = await auth.get_current_user(session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return {
        "id": user.id,
        "display_name": user.display_name,
        "is_admin": user.is_admin
    }


# ============ Logout ============

@app.get("/logout")
async def logout(session: Optional[str] = Cookie(None)):
    """Log out the current user."""
    if session:
        auth.delete_session(session)
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="session")
    return response


# ============ Markets Routes ============

@app.get("/markets", response_class=HTMLResponse)
async def markets_list(request: Request, session: Optional[str] = Cookie(None)):
    """List all markets."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    markets = await db.get_all_markets()

    return templates.TemplateResponse(
        "markets.html",
        {"request": request, "user": user, "markets": markets}
    )


@app.get("/markets/{market_id}", response_class=HTMLResponse)
async def market_detail(
    request: Request,
    market_id: str,
    session: Optional[str] = Cookie(None),
    error: Optional[str] = None,
    success: Optional[str] = None
):
    """Market detail view with order book and trading form."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    market = await db.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    # Get order book (all open orders)
    bids = await db.get_open_orders(market_id, side=OrderSide.BID)
    offers = await db.get_open_orders(market_id, side=OrderSide.OFFER)

    # Enrich orders with user display names
    bids_with_users = []
    for order in bids:
        order_user = await db.get_user_by_id(order.user_id)
        bids_with_users.append(OrderWithUser(
            id=order.id,
            user_id=order.user_id,
            display_name=order_user.display_name if order_user else "Unknown",
            side=order.side,
            price=order.price,
            quantity=order.quantity,
            remaining_quantity=order.remaining_quantity,
            status=order.status,
            created_at=order.created_at
        ))

    offers_with_users = []
    for order in offers:
        order_user = await db.get_user_by_id(order.user_id)
        offers_with_users.append(OrderWithUser(
            id=order.id,
            user_id=order.user_id,
            display_name=order_user.display_name if order_user else "Unknown",
            side=order.side,
            price=order.price,
            quantity=order.quantity,
            remaining_quantity=order.remaining_quantity,
            status=order.status,
            created_at=order.created_at
        ))

    # Get recent trades with user names
    recent_trades = await db.get_recent_trades(market_id, limit=10)
    trades_with_users = []
    for trade in recent_trades:
        buyer = await db.get_user_by_id(trade.buyer_id)
        seller = await db.get_user_by_id(trade.seller_id)
        trades_with_users.append(TradeWithUsers(
            id=trade.id,
            buyer_name=buyer.display_name if buyer else "Unknown",
            seller_name=seller.display_name if seller else "Unknown",
            price=trade.price,
            quantity=trade.quantity,
            created_at=trade.created_at
        ))

    # Get user's position
    position = await db.get_position(market_id, user.id)
    position_limit = await db.get_position_limit()

    return templates.TemplateResponse(
        "market.html",
        {
            "request": request,
            "user": user,
            "market": market,
            "bids": bids_with_users,
            "offers": offers_with_users,
            "trades": trades_with_users,
            "position": position,
            "position_limit": position_limit,
            "error": error,
            "success": success
        }
    )


# ============ Order Routes ============

def is_htmx_request(request: Request) -> bool:
    """Check if request is from HTMX (inline form submission)."""
    return request.headers.get("HX-Request") == "true"


@app.post("/markets/{market_id}/orders")
async def place_order(
    request: Request,
    market_id: str,
    side: str = Form(...),
    price: float = Form(...),
    quantity: int = Form(...),
    session: Optional[str] = Cookie(None)
):
    """Place a new order on a market."""
    user = await auth.get_current_user(session)
    if not user:
        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Error": "Session expired"})
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    # Validate side
    try:
        order_side = OrderSide(side)
    except ValueError:
        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Error": "Invalid order side"})
        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"error": "Invalid order side"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate price and quantity
    if price <= 0:
        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Error": "Price must be positive"})
        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"error": "Price must be positive"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    if quantity <= 0:
        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Error": "Quantity must be positive"})
        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"error": "Quantity must be positive"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        result = await matching.place_order(
            market_id=market_id,
            user_id=user.id,
            side=order_side,
            price=price,
            quantity=quantity
        )

        if result.rejected:
            error_msg = result.reject_reason or "Order rejected"
            if is_htmx_request(request):
                return HTMLResponse(content="", headers={"HX-Toast-Error": error_msg})
            return RedirectResponse(
                url=f"/markets/{market_id}?" + urlencode({"error": error_msg}),
                status_code=status.HTTP_303_SEE_OTHER
            )

        # Build success message
        if result.trades:
            total_filled = sum(t.quantity for t in result.trades)
            if result.fully_filled:
                msg = f"Order fully filled: {total_filled} lots"
            else:
                msg = f"Partial fill: {total_filled} lots, {quantity - total_filled} lots resting"
        else:
            msg = f"Order placed: {quantity} lots @ {price}"

        # Broadcast update to all WebSocket clients
        await broadcast_market_update(market_id)

        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Success": msg})
        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"success": msg}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    except matching.MarketNotOpen:
        error_msg = "Market is not open for trading"
        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Error": error_msg})
        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"error": error_msg}),
            status_code=status.HTTP_303_SEE_OTHER
        )


@app.post("/orders/{order_id}/cancel")
async def cancel_order(request: Request, order_id: str, session: Optional[str] = Cookie(None)):
    """Cancel an open order."""
    user = await auth.get_current_user(session)
    if not user:
        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Error": "Session expired"})
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    # Get order to find market_id for redirect
    order = await db.get_order(order_id)
    if not order:
        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Error": "Order not found"})
        raise HTTPException(status_code=404, detail="Order not found")

    market_id = order.market_id

    try:
        success = await matching.cancel_order(order_id, user.id)

        if success:
            # Broadcast update to all WebSocket clients
            await broadcast_market_update(market_id)

            if is_htmx_request(request):
                return HTMLResponse(content="", headers={"HX-Toast-Success": "Order cancelled"})
            return RedirectResponse(
                url=f"/markets/{market_id}?" + urlencode({"success": "Order cancelled"}),
                status_code=status.HTTP_303_SEE_OTHER
            )
        else:
            error_msg = "Could not cancel order (already filled or cancelled)"
            if is_htmx_request(request):
                return HTMLResponse(content="", headers={"HX-Toast-Error": error_msg})
            return RedirectResponse(
                url=f"/markets/{market_id}?" + urlencode({"error": error_msg}),
                status_code=status.HTTP_303_SEE_OTHER
            )

    except ValueError as e:
        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Error": str(e)})
        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"error": str(e)}),
            status_code=status.HTTP_303_SEE_OTHER
        )


@app.post("/orders/{order_id}/aggress")
async def aggress_order(
    request: Request,
    order_id: str,
    quantity: int = Form(...),
    fill_and_kill: bool = Form(False),
    session: Optional[str] = Cookie(None)
):
    """Aggress a resting order by trading against it.

    Creates a crossing order that immediately matches with the target order.
    For offers: creates a BID at the offer price (hitting the offer).
    For bids: creates an OFFER at the bid price (lifting the bid).

    If fill_and_kill is True, any unfilled quantity is cancelled (no resting order).
    """
    user = await auth.get_current_user(session)
    if not user:
        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Error": "Session expired"})
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    # Get the target order
    target_order = await db.get_order(order_id)
    if not target_order:
        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Error": "Order no longer available"})
        raise HTTPException(status_code=404, detail="Order not found")

    market_id = target_order.market_id

    # Check if order is still open
    if target_order.status != OrderStatus.OPEN:
        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Error": "Order no longer available"})
        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"error": "Order no longer available"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Can't aggress your own order
    if target_order.user_id == user.id:
        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Error": "Cannot trade against your own order"})
        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"error": "Cannot trade against your own order"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate quantity
    if quantity <= 0:
        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Error": "Quantity must be positive"})
        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"error": "Quantity must be positive"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Determine the crossing order side and price
    # To hit an OFFER (sell), we place a BID at that price
    # To lift a BID (buy), we place an OFFER at that price
    if target_order.side == OrderSide.OFFER:
        aggress_side = OrderSide.BID
        action_verb = "Bought"
    else:
        aggress_side = OrderSide.OFFER
        action_verb = "Sold"

    aggress_price = target_order.price

    # Cap the quantity at what's available in the target order
    available_qty = target_order.remaining_quantity
    actual_qty = min(quantity, available_qty)

    try:
        result = await matching.place_order(
            market_id=market_id,
            user_id=user.id,
            side=aggress_side,
            price=aggress_price,
            quantity=actual_qty
        )

        if result.rejected:
            error_msg = result.reject_reason or "Order rejected"
            if is_htmx_request(request):
                return HTMLResponse(content="", headers={"HX-Toast-Error": error_msg})
            return RedirectResponse(
                url=f"/markets/{market_id}?" + urlencode({"error": error_msg}),
                status_code=status.HTTP_303_SEE_OTHER
            )

        # Handle fill-and-kill: cancel any resting order (unfilled portion)
        unfilled_qty = 0
        if fill_and_kill and result.order and result.order.remaining_quantity > 0:
            unfilled_qty = result.order.remaining_quantity
            await matching.cancel_order(result.order.id, user.id)

        # Build success message
        if result.trades:
            total_filled = sum(t.quantity for t in result.trades)
            if total_filled < quantity:
                if fill_and_kill and unfilled_qty > 0:
                    msg = f"{action_verb} {total_filled} of {quantity} requested @ {aggress_price:.2f} ({unfilled_qty} killed)"
                else:
                    msg = f"{action_verb} {total_filled} of {quantity} requested @ {aggress_price:.2f}"
            else:
                msg = f"{action_verb} {total_filled} @ {aggress_price:.2f}"
        else:
            # This shouldn't happen for an aggress (should always match)
            # But with fill_and_kill, if no matches happened, the order was cancelled
            if fill_and_kill:
                msg = f"No fill available, order killed"
            else:
                msg = f"Order placed: {actual_qty} lots @ {aggress_price}"

        # Broadcast update to all WebSocket clients
        await broadcast_market_update(market_id)

        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Success": msg})
        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"success": msg}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    except matching.MarketNotOpen:
        error_msg = "Market is not open for trading"
        if is_htmx_request(request):
            return HTMLResponse(content="", headers={"HX-Toast-Error": error_msg})
        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"error": error_msg}),
            status_code=status.HTTP_303_SEE_OTHER
        )


# ============ Admin Routes ============

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(
    request: Request,
    session: Optional[str] = Cookie(None),
    error: Optional[str] = None,
    success: Optional[str] = None
):
    """Admin panel for market management."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    markets = await db.get_all_markets()
    position_limit = await db.get_position_limit()
    participants = await db.get_all_participants()

    # Get user names for claimed participants
    participants_with_users = []
    for p in participants:
        claimed_by_name = None
        if p.claimed_by_user_id:
            claimed_user = await db.get_user_by_id(p.claimed_by_user_id)
            claimed_by_name = claimed_user.display_name if claimed_user else "Unknown"
        participants_with_users.append({
            "id": p.id,
            "display_name": p.display_name,
            "created_at": p.created_at,
            "claimed_by_user_id": p.claimed_by_user_id,
            "claimed_by_name": claimed_by_name
        })

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": user,
            "markets": markets,
            "position_limit": position_limit,
            "participants": participants_with_users,
            "error": error,
            "success": success
        }
    )


@app.post("/admin/markets")
async def create_market(
    question: str = Form(...),
    description: Optional[str] = Form(None),
    session: Optional[str] = Cookie(None)
):
    """Create a new market (admin only)."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    question = question.strip()
    description = description.strip() if description else None

    if not question:
        return RedirectResponse(
            url="/admin?" + urlencode({"error": "Question cannot be empty"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    market = await db.create_market(question, description)

    return RedirectResponse(
        url="/admin?" + urlencode({"success": f"Market created: {question[:50]}..."}),
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/admin/markets/{market_id}/close")
async def close_market(market_id: str, session: Optional[str] = Cookie(None)):
    """Close a market (no new orders accepted)."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    market = await db.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    if market.status != MarketStatus.OPEN:
        return RedirectResponse(
            url="/admin?" + urlencode({"error": "Only OPEN markets can be closed"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    await db.update_market_status(market_id, MarketStatus.CLOSED)

    return RedirectResponse(
        url="/admin?" + urlencode({"success": "Market closed successfully"}),
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/admin/config")
async def update_config(
    position_limit: int = Form(...),
    session: Optional[str] = Cookie(None)
):
    """Update global configuration (admin only)."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    if position_limit < 1:
        return RedirectResponse(
            url="/admin?" + urlencode({"error": "Position limit must be at least 1"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    await db.set_position_limit(position_limit)

    return RedirectResponse(
        url="/admin?" + urlencode({"success": f"Position limit updated to {position_limit}"}),
        status_code=status.HTTP_303_SEE_OTHER
    )


# ============ Participant Management Routes ============

@app.post("/admin/participants")
async def create_participant(
    display_name: str = Form(...),
    session: Optional[str] = Cookie(None)
):
    """Create a new pre-registered participant (admin only)."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    display_name = display_name.strip()

    if not display_name:
        return RedirectResponse(
            url="/admin?" + urlencode({"error": "Participant name cannot be empty"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    if len(display_name) > 50:
        return RedirectResponse(
            url="/admin?" + urlencode({"error": "Participant name too long (max 50 characters)"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        await db.create_participant(display_name)
        return RedirectResponse(
            url="/admin?" + urlencode({"success": f"Participant '{display_name}' created"}),
            status_code=status.HTTP_303_SEE_OTHER
        )
    except ValueError as e:
        return RedirectResponse(
            url="/admin?" + urlencode({"error": str(e)}),
            status_code=status.HTTP_303_SEE_OTHER
        )


@app.post("/admin/participants/{participant_id}/delete")
async def delete_participant(
    participant_id: str,
    session: Optional[str] = Cookie(None)
):
    """Delete a pre-registered participant (admin only). Cannot delete claimed participants."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    participant = await db.get_participant_by_id(participant_id)
    if not participant:
        return RedirectResponse(
            url="/admin?" + urlencode({"error": "Participant not found"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    if participant.claimed_by_user_id:
        return RedirectResponse(
            url="/admin?" + urlencode({"error": "Cannot delete claimed participant"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    await db.delete_participant(participant_id)
    return RedirectResponse(
        url="/admin?" + urlencode({"success": f"Participant '{participant.display_name}' deleted"}),
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/admin/participants/{participant_id}/release")
async def release_participant(
    participant_id: str,
    session: Optional[str] = Cookie(None)
):
    """Release a claimed participant back to available (admin only)."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    participant = await db.get_participant_by_id(participant_id)
    if not participant:
        return RedirectResponse(
            url="/admin?" + urlencode({"error": "Participant not found"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    await db.unclaim_participant(participant_id)
    return RedirectResponse(
        url="/admin?" + urlencode({"success": f"Participant '{participant.display_name}' released"}),
        status_code=status.HTTP_303_SEE_OTHER
    )


# ============ Settlement Routes ============

@app.get("/admin/markets/{market_id}/settle", response_class=HTMLResponse)
async def settle_market_page(
    request: Request,
    market_id: str,
    session: Optional[str] = Cookie(None),
    error: Optional[str] = None,
    success: Optional[str] = None
):
    """Admin page to settle a market (can settle OPEN or CLOSED markets)."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    market = await db.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    # Can only settle OPEN or CLOSED markets
    if market.status == MarketStatus.SETTLED:
        return RedirectResponse(
            url=f"/markets/{market_id}/results",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Get positions for preview
    positions = await db.get_all_positions(market_id)
    positions_with_names = []
    for pos in positions:
        pos_user = await db.get_user_by_id(pos.user_id)
        positions_with_names.append({
            "display_name": pos_user.display_name if pos_user else "Unknown",
            "net_quantity": pos.net_quantity,
            "total_cost": pos.total_cost
        })

    return templates.TemplateResponse(
        "settle.html",
        {
            "request": request,
            "user": user,
            "market": market,
            "positions": positions_with_names,
            "error": error,
            "success": success
        }
    )


@app.post("/admin/markets/{market_id}/settle")
async def settle_market_action(
    market_id: str,
    settlement_value: float = Form(...),
    session: Optional[str] = Cookie(None)
):
    """Settle a market with the given value."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    market = await db.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    if market.status == MarketStatus.SETTLED:
        return RedirectResponse(
            url=f"/admin/markets/{market_id}/settle?" + urlencode({"error": "Market already settled"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        await settlement.settle_market(market_id, settlement_value)

        # Broadcast update to all WebSocket clients (will trigger redirect to results)
        await broadcast_market_update(market_id)

        return RedirectResponse(
            url=f"/markets/{market_id}/results",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except ValueError as e:
        return RedirectResponse(
            url=f"/admin/markets/{market_id}/settle?" + urlencode({"error": str(e)}),
            status_code=status.HTTP_303_SEE_OTHER
        )


@app.get("/markets/{market_id}/results", response_class=HTMLResponse)
async def market_results(
    request: Request,
    market_id: str,
    session: Optional[str] = Cookie(None)
):
    """View results for a settled market."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    market = await db.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    if market.status != MarketStatus.SETTLED:
        return RedirectResponse(
            url=f"/markets/{market_id}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Get results with P&L
    results = await settlement.get_market_results(market_id)

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "user": user,
            "market": market,
            "results": results
        }
    )


# ============ HTMX Partial Routes ============

@app.get("/partials/market/{market_id}", response_class=HTMLResponse)
async def partial_market_all(
    request: Request,
    market_id: str,
    session: Optional[str] = Cookie(None)
):
    """HTMX partial: Combined position, orderbook, and trades for a market.

    Returns all three sections in one response using hx-swap-oob.
    This reduces HTTP requests from 3/sec to 1/sec per user.
    Auto-redirects to results page when market is settled.
    Also updates user's last_activity timestamp for session exclusivity.
    """
    user = await auth.get_current_user(session)
    if not user:
        return HTMLResponse(content="<p>Session expired. Please refresh.</p>")

    # Update user activity timestamp for session exclusivity tracking
    await db.update_user_activity(user.id)

    market = await db.get_market(market_id)
    if not market:
        return HTMLResponse(content="<p>Market not found.</p>")

    # Auto-redirect to results when market is settled
    if market.status == MarketStatus.SETTLED:
        return HTMLResponse(
            content="",
            headers={"HX-Redirect": f"/markets/{market_id}/results"}
        )

    # Get order book (all open orders)
    bids = await db.get_open_orders(market_id, side=OrderSide.BID)
    offers = await db.get_open_orders(market_id, side=OrderSide.OFFER)

    # Enrich orders with user display names
    bids_with_users = []
    for order in bids:
        order_user = await db.get_user_by_id(order.user_id)
        bids_with_users.append(OrderWithUser(
            id=order.id,
            user_id=order.user_id,
            display_name=order_user.display_name if order_user else "Unknown",
            side=order.side,
            price=order.price,
            quantity=order.quantity,
            remaining_quantity=order.remaining_quantity,
            status=order.status,
            created_at=order.created_at
        ))

    offers_with_users = []
    for order in offers:
        order_user = await db.get_user_by_id(order.user_id)
        offers_with_users.append(OrderWithUser(
            id=order.id,
            user_id=order.user_id,
            display_name=order_user.display_name if order_user else "Unknown",
            side=order.side,
            price=order.price,
            quantity=order.quantity,
            remaining_quantity=order.remaining_quantity,
            status=order.status,
            created_at=order.created_at
        ))

    # Get recent trades with user names
    recent_trades = await db.get_recent_trades(market_id, limit=10)
    trades_with_users = []
    for trade in recent_trades:
        buyer = await db.get_user_by_id(trade.buyer_id)
        seller = await db.get_user_by_id(trade.seller_id)
        trades_with_users.append(TradeWithUsers(
            id=trade.id,
            buyer_name=buyer.display_name if buyer else "Unknown",
            seller_name=seller.display_name if seller else "Unknown",
            price=trade.price,
            quantity=trade.quantity,
            created_at=trade.created_at
        ))

    # Get user's position
    position = await db.get_position(market_id, user.id)

    return templates.TemplateResponse(
        "partials/market_all.html",
        {
            "request": request,
            "user": user,
            "market": market,
            "bids": bids_with_users,
            "offers": offers_with_users,
            "trades": trades_with_users,
            "position": position
        }
    )


# Deprecated: Individual partial endpoints kept for backward compatibility
@app.get("/partials/orderbook/{market_id}", response_class=HTMLResponse)
async def partial_orderbook(
    request: Request,
    market_id: str,
    session: Optional[str] = Cookie(None)
):
    """HTMX partial: Order book for a market."""
    user = await auth.get_current_user(session)
    if not user:
        return HTMLResponse(content="<p>Session expired. Please refresh.</p>")

    market = await db.get_market(market_id)
    if not market:
        return HTMLResponse(content="<p>Market not found.</p>")

    # Get order book (all open orders)
    bids = await db.get_open_orders(market_id, side=OrderSide.BID)
    offers = await db.get_open_orders(market_id, side=OrderSide.OFFER)

    # Enrich orders with user display names
    bids_with_users = []
    for order in bids:
        order_user = await db.get_user_by_id(order.user_id)
        bids_with_users.append(OrderWithUser(
            id=order.id,
            user_id=order.user_id,
            display_name=order_user.display_name if order_user else "Unknown",
            side=order.side,
            price=order.price,
            quantity=order.quantity,
            remaining_quantity=order.remaining_quantity,
            status=order.status,
            created_at=order.created_at
        ))

    offers_with_users = []
    for order in offers:
        order_user = await db.get_user_by_id(order.user_id)
        offers_with_users.append(OrderWithUser(
            id=order.id,
            user_id=order.user_id,
            display_name=order_user.display_name if order_user else "Unknown",
            side=order.side,
            price=order.price,
            quantity=order.quantity,
            remaining_quantity=order.remaining_quantity,
            status=order.status,
            created_at=order.created_at
        ))

    return templates.TemplateResponse(
        "partials/orderbook.html",
        {
            "request": request,
            "user": user,
            "market": market,
            "bids": bids_with_users,
            "offers": offers_with_users
        }
    )


@app.get("/partials/position/{market_id}", response_class=HTMLResponse)
async def partial_position(
    request: Request,
    market_id: str,
    session: Optional[str] = Cookie(None)
):
    """HTMX partial: User's position in a market."""
    user = await auth.get_current_user(session)
    if not user:
        return HTMLResponse(content="<p>Session expired. Please refresh.</p>")

    position = await db.get_position(market_id, user.id)

    return templates.TemplateResponse(
        "partials/position.html",
        {
            "request": request,
            "position": position
        }
    )


@app.get("/partials/trades/{market_id}", response_class=HTMLResponse)
async def partial_trades(
    request: Request,
    market_id: str,
    session: Optional[str] = Cookie(None)
):
    """HTMX partial: Recent trades for a market."""
    user = await auth.get_current_user(session)
    if not user:
        return HTMLResponse(content="<p>Session expired. Please refresh.</p>")

    # Get recent trades with user names
    recent_trades = await db.get_recent_trades(market_id, limit=10)
    trades_with_users = []
    for trade in recent_trades:
        buyer = await db.get_user_by_id(trade.buyer_id)
        seller = await db.get_user_by_id(trade.seller_id)
        trades_with_users.append(TradeWithUsers(
            id=trade.id,
            buyer_name=buyer.display_name if buyer else "Unknown",
            seller_name=seller.display_name if seller else "Unknown",
            price=trade.price,
            quantity=trade.quantity,
            created_at=trade.created_at
        ))

    return templates.TemplateResponse(
        "partials/trades.html",
        {
            "request": request,
            "trades": trades_with_users
        }
    )


# ============ Leaderboard Routes ============

@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard(request: Request, session: Optional[str] = Cookie(None)):
    """Leaderboard showing aggregate P&L across all settled markets."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    entries = await settlement.get_leaderboard()

    return templates.TemplateResponse(
        "leaderboard.html",
        {
            "request": request,
            "user": user,
            "entries": entries
        }
    )


# ============ WebSocket Routes ============

async def generate_market_html_for_user(market_id: str, user_id: str) -> str:
    """Generate HTML update for a market to send via WebSocket.

    Returns the same content as the combined partial endpoint.
    """
    market = await db.get_market(market_id)
    if not market:
        return '<div id="position-content"><p>Market not found.</p></div>'

    # Check if market is settled - send redirect instruction
    if market.status == MarketStatus.SETTLED:
        return f'{{"type": "redirect", "url": "/markets/{market_id}/results"}}'

    # Get user for context
    user = await db.get_user_by_id(user_id)
    if not user:
        return '<div id="position-content"><p>Session expired.</p></div>'

    # Get order book
    bids = await db.get_open_orders(market_id, side=OrderSide.BID)
    offers = await db.get_open_orders(market_id, side=OrderSide.OFFER)

    # Enrich orders with user display names
    bids_with_users = []
    for order in bids:
        order_user = await db.get_user_by_id(order.user_id)
        bids_with_users.append(OrderWithUser(
            id=order.id,
            user_id=order.user_id,
            display_name=order_user.display_name if order_user else "Unknown",
            side=order.side,
            price=order.price,
            quantity=order.quantity,
            remaining_quantity=order.remaining_quantity,
            status=order.status,
            created_at=order.created_at
        ))

    offers_with_users = []
    for order in offers:
        order_user = await db.get_user_by_id(order.user_id)
        offers_with_users.append(OrderWithUser(
            id=order.id,
            user_id=order.user_id,
            display_name=order_user.display_name if order_user else "Unknown",
            side=order.side,
            price=order.price,
            quantity=order.quantity,
            remaining_quantity=order.remaining_quantity,
            status=order.status,
            created_at=order.created_at
        ))

    # Get recent trades
    recent_trades = await db.get_recent_trades(market_id, limit=10)
    trades_with_users = []
    for trade in recent_trades:
        buyer = await db.get_user_by_id(trade.buyer_id)
        seller = await db.get_user_by_id(trade.seller_id)
        trades_with_users.append(TradeWithUsers(
            id=trade.id,
            buyer_name=buyer.display_name if buyer else "Unknown",
            seller_name=seller.display_name if seller else "Unknown",
            price=trade.price,
            quantity=trade.quantity,
            created_at=trade.created_at
        ))

    # Get user's position
    position = await db.get_position(market_id, user_id)

    # Render the template (without request - use None for url_for if needed)
    return templates.get_template("partials/market_all.html").render(
        request=None,
        user=user,
        market=market,
        bids=bids_with_users,
        offers=offers_with_users,
        trades=trades_with_users,
        position=position
    )


async def broadcast_market_update(market_id: str):
    """Broadcast market update to all connected WebSocket clients.

    Each client receives a personalized HTML update based on their user_id.
    """
    # Get all connected users for this market
    if market_id not in ws_manager._connections:
        return

    for websocket, user_id in list(ws_manager._connections[market_id]):
        try:
            html = await generate_market_html_for_user(market_id, user_id)
            await ws_manager.send_personal_update(market_id, user_id, html)
        except Exception:
            # Connection error, will be cleaned up by manager
            pass


@app.websocket("/ws/market/{market_id}")
async def websocket_market(websocket: WebSocket, market_id: str):
    """WebSocket endpoint for real-time market updates.

    Clients connect to receive push updates instead of polling.
    Supports ping/pong keepalive for stale connection detection.
    """
    # Get user from cookie (need to parse manually for WebSocket)
    session_cookie = websocket.cookies.get("session")
    user = await auth.get_current_user(session_cookie) if session_cookie else None

    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Verify market exists
    market = await db.get_market(market_id)
    if not market:
        await websocket.close(code=4004, reason="Market not found")
        return

    # Connect
    await ws_manager.connect(websocket, market_id, user.id)

    # Update user activity for session tracking
    await db.update_user_activity(user.id)

    # Send initial state
    try:
        html = await generate_market_html_for_user(market_id, user.id)
        await websocket.send_text(html)
    except Exception:
        ws_manager.disconnect(websocket, market_id, user.id)
        return

    # Listen for messages (pong responses)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle pong response
            if data == '{"type": "pong"}' or data == 'pong':
                ws_manager.record_pong(websocket)
            # Update user activity on any message
            await db.update_user_activity(user.id)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, market_id, user.id)
    except Exception:
        ws_manager.disconnect(websocket, market_id, user.id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
