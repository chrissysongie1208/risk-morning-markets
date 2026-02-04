"""Main FastAPI application for Morning Markets prediction market."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from fastapi import FastAPI, Request, Form, Cookie, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

import database as db
import auth
import matching
import settlement
from models import MarketStatus, OrderSide, OrderWithUser, TradeWithUsers, PositionWithPnL

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

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "user": None, "error": error}
    )


# ============ Participant Join ============

@app.post("/join")
async def join(display_name: str = Form(...)):
    """Join as a participant with a display name."""
    display_name = display_name.strip()

    if not display_name:
        return RedirectResponse(
            url="/?error=Display name cannot be empty",
            status_code=status.HTTP_303_SEE_OTHER
        )

    if len(display_name) > 50:
        return RedirectResponse(
            url="/?error=Display name too long (max 50 characters)",
            status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        user, token = await auth.login_participant(display_name)
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

@app.post("/markets/{market_id}/orders")
async def place_order(
    market_id: str,
    side: str = Form(...),
    price: float = Form(...),
    quantity: int = Form(...),
    session: Optional[str] = Cookie(None)
):
    """Place a new order on a market."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    # Validate side
    try:
        order_side = OrderSide(side)
    except ValueError:
        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"error": "Invalid order side"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Validate price and quantity
    if price <= 0:
        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"error": "Price must be positive"}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    if quantity <= 0:
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
            return RedirectResponse(
                url=f"/markets/{market_id}?" + urlencode({"error": result.reject_reason or "Order rejected"}),
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

        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"success": msg}),
            status_code=status.HTTP_303_SEE_OTHER
        )

    except matching.MarketNotOpen:
        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"error": "Market is not open for trading"}),
            status_code=status.HTTP_303_SEE_OTHER
        )


@app.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, session: Optional[str] = Cookie(None)):
    """Cancel an open order."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    # Get order to find market_id for redirect
    order = await db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    market_id = order.market_id

    try:
        success = await matching.cancel_order(order_id, user.id)

        if success:
            return RedirectResponse(
                url=f"/markets/{market_id}?" + urlencode({"success": "Order cancelled"}),
                status_code=status.HTTP_303_SEE_OTHER
            )
        else:
            return RedirectResponse(
                url=f"/markets/{market_id}?" + urlencode({"error": "Could not cancel order (already filled or cancelled)"}),
                status_code=status.HTTP_303_SEE_OTHER
            )

    except ValueError as e:
        return RedirectResponse(
            url=f"/markets/{market_id}?" + urlencode({"error": str(e)}),
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

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": user,
            "markets": markets,
            "position_limit": position_limit,
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


# ============ Settlement Routes ============

@app.get("/admin/markets/{market_id}/settle", response_class=HTMLResponse)
async def settle_market_page(
    request: Request,
    market_id: str,
    session: Optional[str] = Cookie(None),
    error: Optional[str] = None,
    success: Optional[str] = None
):
    """Admin page to settle a market."""
    user = await auth.get_current_user(session)
    if not user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    market = await db.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
