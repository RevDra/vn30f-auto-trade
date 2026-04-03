"""Comprehensive test suite for Phase 2 — Dashboard Backend + Frontend scaffold.

10 test classes covering:
  1. WSManager — connect, broadcast, disconnect, throttle
  2. RedisBridge — message parsing, channel routing
  3. Dashboard health endpoint
  4. Dashboard PnL proxy (mocked replay-engine)
  5. Dashboard trades proxy
  6. Dashboard equity-curve proxy
  7. Dashboard order proxy (LONG/SHORT/CLOSE + validation)
  8. Dashboard session management (create, activate, delete)
  9. WebSocket /ws/live endpoint
 10. Frontend file structure validation
"""

import os
import sys
import json
import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

# Add dashboard root to path
DASHBOARD_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DASHBOARD_ROOT)

from backend.ws_manager import WSManager
from backend.redis_bridge import RedisBridge


# ────────────────────────────────────────────────────────────────────────────
# Test 1: WSManager — connect, broadcast, disconnect
# ────────────────────────────────────────────────────────────────────────────
class TestWSManager:
    def setup_method(self):
        self.mgr = WSManager(max_rate=100)  # high rate for testing

    @pytest.mark.asyncio
    async def test_connect(self):
        ws = AsyncMock()
        await self.mgr.connect(ws)
        assert self.mgr.active_count == 1
        ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self):
        ws = AsyncMock()
        await self.mgr.connect(ws)
        self.mgr.disconnect(ws)
        assert self.mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_dict(self):
        ws = AsyncMock()
        await self.mgr.connect(ws)
        await self.mgr.broadcast({"type": "test", "value": 42}, throttle=False)
        ws.send_text.assert_called_once()
        sent = json.loads(ws.send_text.call_args[0][0])
        assert sent["type"] == "test"
        assert sent["value"] == 42

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self):
        ws_alive = AsyncMock()
        ws_dead = AsyncMock()
        ws_dead.send_text.side_effect = Exception("connection closed")

        await self.mgr.connect(ws_alive)
        await self.mgr.connect(ws_dead)
        assert self.mgr.active_count == 2

        await self.mgr.broadcast({"test": True}, throttle=False)
        assert self.mgr.active_count == 1  # dead one removed

    @pytest.mark.asyncio
    async def test_broadcast_throttle(self):
        """With max_rate=2, second broadcast within 0.5s should be skipped."""
        mgr = WSManager(max_rate=2)
        ws = AsyncMock()
        await mgr.connect(ws)

        await mgr.broadcast({"n": 1}, throttle=True)
        await mgr.broadcast({"n": 2}, throttle=True)  # should be throttled

        assert ws.send_text.call_count == 1

    @pytest.mark.asyncio
    async def test_send_to_specific(self):
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await self.mgr.connect(ws1)
        await self.mgr.connect(ws2)

        await self.mgr.send_to(ws1, {"for": "ws1"})
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_not_called()


# ────────────────────────────────────────────────────────────────────────────
# Test 2: RedisBridge — message parsing
# ────────────────────────────────────────────────────────────────────────────
class TestRedisBridge:
    def test_init(self):
        redis_mock = MagicMock()
        ws_mgr = WSManager()
        bridge = RedisBridge(redis_mock, ws_mgr)
        assert bridge.channels == ["market_data_vn30f1m", "engine_updates"]
        assert bridge.is_running is False

    def test_custom_channels(self):
        bridge = RedisBridge(MagicMock(), WSManager(), channels=["custom_ch"])
        assert bridge.channels == ["custom_ch"]

    @pytest.mark.asyncio
    async def test_stop(self):
        bridge = RedisBridge(MagicMock(), WSManager())
        bridge._running = True
        bridge._pubsub = AsyncMock()
        await bridge.stop()
        assert bridge.is_running is False


# ────────────────────────────────────────────────────────────────────────────
# Test 3: Health endpoint
# ────────────────────────────────────────────────────────────────────────────
class TestHealthEndpoint:
    @pytest.fixture(autouse=True)
    def setup_client(self):
        from fastapi.testclient import TestClient
        from backend.app import app
        self.client = TestClient(app, raise_server_exceptions=False)
        yield

    def test_health_returns_200(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "redis_connected" in data
        assert "engine_connected" in data
        assert "ws_clients" in data
        assert "timestamp" in data


# ────────────────────────────────────────────────────────────────────────────
# Test 4: Dashboard PnL proxy
# ────────────────────────────────────────────────────────────────────────────
class TestDashboardPnL:
    @pytest.fixture(autouse=True)
    def setup_client(self):
        from fastapi.testclient import TestClient
        from backend.app import app
        self.client = TestClient(app, raise_server_exceptions=False)
        yield

    @patch("backend.app._proxy_get")
    def test_pnl_proxy(self, mock_proxy):
        mock_proxy.return_value = {
            "timestamp": "2025-04-03T10:00:00",
            "symbol": "VN30F1M",
            "session_id": "default",
            "balance": 500000000,
            "equity": 500100000,
            "session_summary": {
                "total_trades": 5,
                "win_rate": 0.6,
                "pnl_vnd": 100000,
                "max_drawdown_percent": 1.5,
                "sharpe_ratio": 1.2,
                "total_commission": 36250,
                "total_tax": 22100,
            },
            "active_position": None,
        }

        resp = self.client.get("/api/dashboard/pnl")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "VN30F1M"
        assert data["session_summary"]["total_trades"] == 5
        mock_proxy.assert_called_once_with("/api/v1/pnl")


# ────────────────────────────────────────────────────────────────────────────
# Test 5: Dashboard trades proxy
# ────────────────────────────────────────────────────────────────────────────
class TestDashboardTrades:
    @pytest.fixture(autouse=True)
    def setup_client(self):
        from fastapi.testclient import TestClient
        from backend.app import app
        self.client = TestClient(app, raise_server_exceptions=False)
        yield

    @patch("backend.app._proxy_get")
    def test_trades_proxy(self, mock_proxy):
        mock_proxy.return_value = {
            "total": 2,
            "page": 1,
            "page_size": 50,
            "trades": [
                {
                    "entry_time": "2025-04-03T10:00:00",
                    "exit_time": "2025-04-03T10:05:00",
                    "type": "LONG",
                    "volume": 1,
                    "entry_price": 1300.2,
                    "exit_price": 1305.0,
                    "gross_pnl": 480000,
                    "commission": 14500,
                    "tax": 44200,
                    "net_pnl": 421300,
                },
            ],
        }
        resp = self.client.get("/api/dashboard/trades")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["trades"]) == 1
        assert data["trades"][0]["type"] == "LONG"


# ────────────────────────────────────────────────────────────────────────────
# Test 6: Dashboard equity-curve proxy
# ────────────────────────────────────────────────────────────────────────────
class TestDashboardEquityCurve:
    @pytest.fixture(autouse=True)
    def setup_client(self):
        from fastapi.testclient import TestClient
        from backend.app import app
        self.client = TestClient(app, raise_server_exceptions=False)
        yield

    @patch("backend.app._proxy_get")
    def test_equity_curve_proxy(self, mock_proxy):
        mock_proxy.return_value = {
            "session_id": "default",
            "initial_balance": 500000000,
            "points": 100,
            "equity_curve": [500000000, 500100000, 500050000],
            "timeseries": [
                {"time": "2025-04-03T10:00:00", "equity": 500000000, "pnl": 0, "regime": "bull"},
            ],
        }
        resp = self.client.get("/api/dashboard/equity-curve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["initial_balance"] == 500000000
        assert len(data["equity_curve"]) == 3


# ────────────────────────────────────────────────────────────────────────────
# Test 7: Dashboard order proxy (LONG/SHORT/CLOSE + validation)
# ────────────────────────────────────────────────────────────────────────────
class TestDashboardOrder:
    @pytest.fixture(autouse=True)
    def setup_client(self):
        from fastapi.testclient import TestClient
        from backend.app import app
        self.client = TestClient(app, raise_server_exceptions=False)
        yield

    @patch("backend.app._proxy_post")
    def test_order_long(self, mock_proxy):
        mock_proxy.return_value = {"status": "ok", "action": "OPEN", "type": "LONG", "volume": 1}
        resp = self.client.post("/api/dashboard/order", json={"action": "LONG", "volume": 1})
        assert resp.status_code == 200
        mock_proxy.assert_called_once_with("/api/v1/order", {"action": "LONG", "volume": 1})

    @patch("backend.app._proxy_post")
    def test_order_short(self, mock_proxy):
        mock_proxy.return_value = {"status": "ok", "action": "OPEN", "type": "SHORT", "volume": 2}
        resp = self.client.post("/api/dashboard/order", json={"action": "SHORT", "volume": 2})
        assert resp.status_code == 200

    def test_order_invalid_action(self):
        resp = self.client.post("/api/dashboard/order", json={"action": "BUY", "volume": 1})
        assert resp.status_code == 422

    def test_order_invalid_volume_zero(self):
        resp = self.client.post("/api/dashboard/order", json={"action": "LONG", "volume": 0})
        assert resp.status_code == 422

    def test_order_invalid_volume_too_high(self):
        resp = self.client.post("/api/dashboard/order", json={"action": "LONG", "volume": 501})
        assert resp.status_code == 422

    @patch("backend.app._proxy_post")
    def test_close_position(self, mock_proxy):
        mock_proxy.return_value = {"status": "ok", "action": "CLOSE"}
        resp = self.client.post("/api/dashboard/close-position")
        assert resp.status_code == 200
        mock_proxy.assert_called_once_with("/api/v1/close-position")


# ────────────────────────────────────────────────────────────────────────────
# Test 8: Dashboard session management
# ────────────────────────────────────────────────────────────────────────────
class TestDashboardSessions:
    @pytest.fixture(autouse=True)
    def setup_client(self):
        from fastapi.testclient import TestClient
        from backend.app import app
        self.client = TestClient(app, raise_server_exceptions=False)
        yield

    @patch("backend.app._proxy_get")
    def test_list_sessions(self, mock_proxy):
        mock_proxy.return_value = {
            "sessions": [
                {"session_id": "default", "strategy": "manual", "active": True},
            ]
        }
        resp = self.client.get("/api/dashboard/sessions")
        assert resp.status_code == 200
        assert len(resp.json()["sessions"]) == 1

    @patch("backend.app._proxy_post")
    def test_create_session(self, mock_proxy):
        mock_proxy.return_value = {"status": "ok", "session_id": "new_s"}
        resp = self.client.post(
            "/api/dashboard/sessions",
            json={"session_id": "new_s", "strategy": "algo_v1"},
        )
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "new_s"

    @patch("backend.app._proxy_put")
    def test_activate_session(self, mock_proxy):
        mock_proxy.return_value = {"status": "ok", "active_session": "s2"}
        resp = self.client.put("/api/dashboard/sessions/s2/activate")
        assert resp.status_code == 200

    @patch("backend.app._proxy_delete")
    def test_delete_session(self, mock_proxy):
        mock_proxy.return_value = {"status": "ok", "deleted": "s2"}
        resp = self.client.delete("/api/dashboard/sessions/s2")
        assert resp.status_code == 200

    @patch("backend.app._proxy_post")
    def test_reset(self, mock_proxy):
        mock_proxy.return_value = {"status": "ok", "message": "Engine reset"}
        resp = self.client.post("/api/dashboard/reset")
        assert resp.status_code == 200


# ────────────────────────────────────────────────────────────────────────────
# Test 9: WebSocket /ws/live endpoint
# ────────────────────────────────────────────────────────────────────────────
class TestWebSocket:
    @pytest.fixture(autouse=True)
    def setup_client(self):
        from fastapi.testclient import TestClient
        from backend.app import app, ws_manager
        self.client = TestClient(app)
        self.ws_manager = ws_manager
        yield

    def test_ws_connect_and_ping(self):
        with self.client.websocket_connect("/ws/live") as ws:
            ws.send_text("ping")
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_ws_increases_connection_count(self):
        initial = self.ws_manager.active_count
        with self.client.websocket_connect("/ws/live") as ws:
            ws.send_text("ping")
            ws.receive_json()
            # active count should be >= initial + 1
            assert self.ws_manager.active_count >= initial + 1


# ────────────────────────────────────────────────────────────────────────────
# Test 10: Frontend file structure validation
# ────────────────────────────────────────────────────────────────────────────
class TestFrontendStructure:
    """Verify all required frontend files exist with correct structure."""

    FRONTEND_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend"
    )

    def test_package_json_exists(self):
        path = os.path.join(self.FRONTEND_DIR, "package.json")
        assert os.path.isfile(path)
        with open(path) as f:
            pkg = json.load(f)
        assert "lightweight-charts" in pkg.get("dependencies", {})
        assert "react" in pkg.get("dependencies", {})
        assert "tailwindcss" in pkg.get("devDependencies", {})

    def test_vite_config_exists(self):
        assert os.path.isfile(os.path.join(self.FRONTEND_DIR, "vite.config.ts"))

    def test_index_html_exists(self):
        path = os.path.join(self.FRONTEND_DIR, "index.html")
        assert os.path.isfile(path)
        with open(path) as f:
            content = f.read()
        assert 'class="dark"' in content

    def test_main_tsx_exists(self):
        assert os.path.isfile(os.path.join(self.FRONTEND_DIR, "src", "main.tsx"))

    def test_app_tsx_exists(self):
        assert os.path.isfile(os.path.join(self.FRONTEND_DIR, "src", "App.tsx"))

    def test_all_components_exist(self):
        components = [
            "CandlestickChart.tsx",
            "EquityMetrics.tsx",
            "TradePosition.tsx",
            "OrderPanel.tsx",
        ]
        comp_dir = os.path.join(self.FRONTEND_DIR, "src", "components")
        for name in components:
            assert os.path.isfile(os.path.join(comp_dir, name)), f"Missing {name}"

    def test_hooks_exist(self):
        hooks = ["useWebSocket.ts", "useApi.ts"]
        hooks_dir = os.path.join(self.FRONTEND_DIR, "src", "hooks")
        for name in hooks:
            assert os.path.isfile(os.path.join(hooks_dir, name)), f"Missing {name}"

    def test_types_exist(self):
        assert os.path.isfile(os.path.join(self.FRONTEND_DIR, "src", "types", "api.ts"))

    def test_tailwind_config(self):
        path = os.path.join(self.FRONTEND_DIR, "tailwind.config.js")
        assert os.path.isfile(path)
        with open(path) as f:
            content = f.read()
        assert "darkMode" in content

    def test_docker_files(self):
        assert os.path.isfile(os.path.join(self.FRONTEND_DIR, "Dockerfile"))
        assert os.path.isfile(os.path.join(self.FRONTEND_DIR, "nginx.conf"))
