"""Dashboard FastAPI backend — REST proxy + WebSocket server."""

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import redis.asyncio as aioredis
import httpx

from backend.ws_manager import WSManager
from backend.redis_bridge import RedisBridge

logger = logging.getLogger("dashboard")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# --- Config ---

REPLAY_ENGINE_URL = os.getenv("REPLAY_ENGINE_URL", "http://localhost:8001")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# --- Globals ---

ws_manager = WSManager(max_rate=10.0)
redis_client: Optional[aioredis.Redis] = None
redis_bridge: Optional[RedisBridge] = None
background_tasks = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, redis_bridge

    # Connect to Redis
    try:
        redis_client = aioredis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
        )
        await redis_client.ping()
        logger.info(f"Dashboard connected to Redis at {REDIS_HOST}:{REDIS_PORT}")

        # Start Redis → WS bridge
        redis_bridge = RedisBridge(redis_client, ws_manager)
        task = asyncio.create_task(redis_bridge.start())
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
        redis_client = None

    yield

    # Cleanup
    if redis_bridge:
        await redis_bridge.stop()
    for task in background_tasks:
        task.cancel()
    if redis_client:
        await redis_client.close()


app = FastAPI(
    title="VN30F Trading Dashboard",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Helper: proxy to replay-engine ---

async def _proxy_get(path: str, params: dict = None) -> dict:
    """Proxy GET request to replay-engine."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{REPLAY_ENGINE_URL}{path}", params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(502, "Replay engine unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)


async def _proxy_post(path: str, json_data: dict = None) -> dict:
    """Proxy POST request to replay-engine."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{REPLAY_ENGINE_URL}{path}", json=json_data)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(502, "Replay engine unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)


async def _proxy_put(path: str, json_data: dict = None) -> dict:
    """Proxy PUT request to replay-engine."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.put(f"{REPLAY_ENGINE_URL}{path}", json=json_data)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(502, "Replay engine unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)


async def _proxy_delete(path: str) -> dict:
    """Proxy DELETE request to replay-engine."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.delete(f"{REPLAY_ENGINE_URL}{path}")
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(502, "Replay engine unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)


# --- Health ---

@app.get("/health")
async def health():
    redis_ok = False
    if redis_client:
        try:
            await redis_client.ping()
            redis_ok = True
        except Exception:
            pass

    engine_ok = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{REPLAY_ENGINE_URL}/health")
            engine_ok = resp.status_code == 200
    except Exception:
        pass

    return {
        "status": "ok" if (redis_ok and engine_ok) else "degraded",
        "redis_connected": redis_ok,
        "engine_connected": engine_ok,
        "ws_clients": ws_manager.active_count,
        "redis_bridge_active": redis_bridge.is_running if redis_bridge else False,
        "timestamp": datetime.now().isoformat(),
    }


# --- Dashboard REST proxies ---

@app.get("/api/dashboard/pnl")
async def dashboard_pnl():
    return await _proxy_get("/api/v1/pnl")


@app.get("/api/dashboard/trades")
async def dashboard_trades(page: int = 1, page_size: int = 50):
    return await _proxy_get("/api/v1/trades", {"page": page, "page_size": page_size})


@app.get("/api/dashboard/equity-curve")
async def dashboard_equity_curve():
    return await _proxy_get("/api/v1/equity-curve")


@app.get("/api/dashboard/sessions")
async def dashboard_sessions():
    return await _proxy_get("/api/v1/sessions")


# --- Order proxies ---

class OrderRequest(BaseModel):
    action: str = Field(..., pattern="^(LONG|SHORT)$")
    volume: int = Field(..., gt=0, le=500)


class SessionCreateRequest(BaseModel):
    session_id: str = "default"
    strategy: str = "manual"
    initial_balance: float = 500_000_000
    strict_hours: bool = False


@app.post("/api/dashboard/order")
async def dashboard_order(req: OrderRequest):
    return await _proxy_post("/api/v1/order", req.model_dump())


@app.post("/api/dashboard/close-position")
async def dashboard_close():
    return await _proxy_post("/api/v1/close-position")


@app.post("/api/dashboard/reset")
async def dashboard_reset():
    return await _proxy_post("/api/v1/reset")


@app.post("/api/dashboard/sessions")
async def dashboard_create_session(req: SessionCreateRequest):
    return await _proxy_post("/api/v1/sessions", req.model_dump())


@app.put("/api/dashboard/sessions/{session_id}/activate")
async def dashboard_activate_session(session_id: str):
    return await _proxy_put(f"/api/v1/sessions/{session_id}/activate")


@app.delete("/api/dashboard/sessions/{session_id}")
async def dashboard_delete_session(session_id: str):
    return await _proxy_delete(f"/api/v1/sessions/{session_id}")


# --- WebSocket ---

@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """Live WebSocket endpoint for real-time market data + engine updates."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; handle client messages if needed
            data = await websocket.receive_text()
            # Client can send ping or commands
            if data == "ping":
                await ws_manager.send_to(websocket, {"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
