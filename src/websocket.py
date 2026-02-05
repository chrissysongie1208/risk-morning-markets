"""WebSocket connection manager for real-time market updates.

Handles:
- Client connections per market
- Broadcasting HTML updates to all connected clients
- Ping/pong keepalive for stale connection detection
- Timing logging for latency diagnosis
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState


# Configure logger
logger = logging.getLogger("morning-markets.websocket")

# Keepalive interval in seconds
WEBSOCKET_PING_INTERVAL = 30

# Slow operation threshold in seconds
SLOW_OPERATION_THRESHOLD = 0.5


class ConnectionManager:
    """Manages WebSocket connections for market updates.

    Tracks connected clients per market and provides broadcast functionality.
    Includes ping/pong keepalive to detect stale connections.
    """

    def __init__(self):
        # market_id -> set of (websocket, user_id) tuples
        self._connections: dict[str, set[tuple[WebSocket, str]]] = defaultdict(set)
        # websocket -> last_pong timestamp
        self._last_pong: dict[WebSocket, datetime] = {}
        # Background task for keepalive
        self._keepalive_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket, market_id: str, user_id: str):
        """Accept a new WebSocket connection for a market."""
        await websocket.accept()
        self._connections[market_id].add((websocket, user_id))
        self._last_pong[websocket] = datetime.utcnow()

        # Start keepalive task if not running
        if self._keepalive_task is None or self._keepalive_task.done():
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    def disconnect(self, websocket: WebSocket, market_id: str, user_id: str):
        """Remove a WebSocket connection."""
        self._connections[market_id].discard((websocket, user_id))
        self._last_pong.pop(websocket, None)

        # Clean up empty market sets
        if not self._connections[market_id]:
            del self._connections[market_id]

    async def broadcast(self, market_id: str, message: str):
        """Send HTML update to all clients connected to a market."""
        if market_id not in self._connections:
            return

        start_time = time.perf_counter()

        # Create list copy to avoid modification during iteration
        connections = list(self._connections[market_id])
        disconnected = []
        sent_count = 0

        for websocket, user_id in connections:
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    send_start = time.perf_counter()
                    await websocket.send_text(message)
                    send_time = (time.perf_counter() - send_start) * 1000
                    sent_count += 1

                    if send_time > SLOW_OPERATION_THRESHOLD * 1000:
                        logger.warning(
                            f"SLOW: WebSocket send to user {user_id} took {send_time:.2f}ms"
                        )
            except Exception:
                # Mark for removal
                disconnected.append((websocket, user_id))

        # Clean up disconnected clients
        for ws, uid in disconnected:
            self.disconnect(ws, market_id, uid)

        total_time = (time.perf_counter() - start_time) * 1000
        if sent_count > 0:
            logger.debug(
                f"WebSocket broadcast: market={market_id}, clients={sent_count}, "
                f"total_time={total_time:.1f}ms, avg={total_time/sent_count:.1f}ms"
            )

    async def send_personal_update(
        self,
        market_id: str,
        user_id: str,
        message: str
    ):
        """Send a personal update to a specific user in a market."""
        if market_id not in self._connections:
            logger.debug(f"send_personal_update: No connections for market {market_id}")
            return

        for websocket, uid in list(self._connections[market_id]):
            if uid == user_id:
                try:
                    if websocket.client_state == WebSocketState.CONNECTED:
                        send_start = time.perf_counter()
                        await websocket.send_text(message)
                        send_time = (time.perf_counter() - send_start) * 1000

                        if send_time > SLOW_OPERATION_THRESHOLD * 1000:
                            logger.warning(
                                f"SLOW: WebSocket personal send to user {user_id} took {send_time:.2f}ms"
                            )
                    else:
                        logger.warning(
                            f"WebSocket not connected for user {user_id}, state={websocket.client_state}"
                        )
                        self.disconnect(websocket, market_id, uid)
                except Exception as e:
                    logger.warning(f"WebSocket send failed for user {user_id}: {e}")
                    self.disconnect(websocket, market_id, uid)

    def record_pong(self, websocket: WebSocket):
        """Record that a pong was received from a client."""
        self._last_pong[websocket] = datetime.utcnow()

    async def _keepalive_loop(self):
        """Background task to send pings and clean up stale connections."""
        while True:
            await asyncio.sleep(WEBSOCKET_PING_INTERVAL)

            if not self._connections:
                # No connections, stop the task
                break

            # Send ping to all connections and check for stale ones
            stale_timeout = datetime.utcnow() - timedelta(seconds=WEBSOCKET_PING_INTERVAL * 2)

            for market_id in list(self._connections.keys()):
                for websocket, user_id in list(self._connections[market_id]):
                    try:
                        # Check if connection is stale
                        last_pong = self._last_pong.get(websocket)
                        if last_pong and last_pong < stale_timeout:
                            # Stale connection, close it
                            await websocket.close()
                            self.disconnect(websocket, market_id, user_id)
                            continue

                        # Send ping
                        if websocket.client_state == WebSocketState.CONNECTED:
                            await websocket.send_text('{"type": "ping"}')
                    except Exception:
                        self.disconnect(websocket, market_id, user_id)

    def get_connection_count(self, market_id: str) -> int:
        """Get number of connected clients for a market."""
        return len(self._connections.get(market_id, set()))

    def get_total_connections(self) -> int:
        """Get total number of connected clients across all markets."""
        return sum(len(conns) for conns in self._connections.values())


# Global connection manager instance
manager = ConnectionManager()
