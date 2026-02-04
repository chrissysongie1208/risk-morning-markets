"""Pydantic models for the Morning Markets prediction market app."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class MarketStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    SETTLED = "SETTLED"


class OrderSide(str, Enum):
    BID = "BID"
    OFFER = "OFFER"


class OrderStatus(str, Enum):
    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


# Database models (what we store/retrieve)
class User(BaseModel):
    id: str
    display_name: str
    is_admin: bool = False
    created_at: datetime
    last_activity: Optional[datetime] = None


class Participant(BaseModel):
    """Pre-registered participant name created by admin."""
    id: str
    display_name: str
    created_by_admin: bool = True
    created_at: datetime
    claimed_by_user_id: Optional[str] = None  # User ID who claimed this name


class Market(BaseModel):
    id: str
    question: str
    description: Optional[str] = None
    status: MarketStatus = MarketStatus.OPEN
    settlement_value: Optional[float] = None
    created_at: datetime
    settled_at: Optional[datetime] = None


class Order(BaseModel):
    id: str
    market_id: str
    user_id: str
    side: OrderSide
    price: float
    quantity: int
    remaining_quantity: int
    status: OrderStatus = OrderStatus.OPEN
    created_at: datetime


class Trade(BaseModel):
    id: str
    market_id: str
    buy_order_id: str
    sell_order_id: str
    buyer_id: str
    seller_id: str
    price: float
    quantity: int
    created_at: datetime


class Position(BaseModel):
    id: str
    market_id: str
    user_id: str
    net_quantity: int = 0
    total_cost: float = 0.0


# Request/Response models
class JoinRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=50)


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class CreateMarketRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=2000)


class PlaceOrderRequest(BaseModel):
    side: OrderSide
    price: float = Field(..., gt=0)
    quantity: int = Field(..., gt=0)


class SettleMarketRequest(BaseModel):
    settlement_value: float


class UpdateConfigRequest(BaseModel):
    position_limit: int = Field(..., gt=0)


# Response models with computed fields
class PositionWithPnL(BaseModel):
    """Position with P&L calculated after settlement."""
    user_id: str
    display_name: str
    net_quantity: int
    total_cost: float
    avg_price: Optional[float] = None
    linear_pnl: Optional[float] = None
    binary_pnl: int = 0  # Lots won (positive) or lost (negative), calculated per-trade


class LeaderboardEntry(BaseModel):
    """Aggregated P&L across all settled markets."""
    user_id: str
    display_name: str
    total_linear_pnl: float
    total_binary_pnl: int = 0  # Total lots won/lost across all markets
    markets_traded: int


class OrderWithUser(BaseModel):
    """Order with user display name for order book display."""
    id: str
    user_id: str
    display_name: str
    side: OrderSide
    price: float
    quantity: int
    remaining_quantity: int
    status: OrderStatus
    created_at: datetime


class TradeWithUsers(BaseModel):
    """Trade with buyer/seller display names."""
    id: str
    buyer_name: str
    seller_name: str
    price: float
    quantity: int
    created_at: datetime
