"""Phase 3 tests — Persistence layer (SQLite in-memory for testing).

10 test classes covering:
1. DatabaseManager init + table creation
2. TradingSessionModel CRUD
3. TradeModel CRUD
4. EquitySnapshotModel CRUD
5. Repository session operations
6. Repository trade operations
7. Repository equity operations
8. AutoSaver trade detection + persistence
9. Session history API endpoints
10. Session comparison API
"""

import asyncio
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

# SQLAlchemy + persistence imports
from sqlalchemy import select, text

# Add parent to path
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.persistence.database import DatabaseManager, Base
from app.persistence.models import TradingSessionModel, TradeModel, EquitySnapshotModel
from app.persistence.repository import TradingRepository
from app.persistence.auto_saver import AutoSaver
from app.persistence.history_api import router as history_router, init_history_router


SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db():
    """Create an in-memory SQLite database for testing."""
    manager = DatabaseManager(url=SQLITE_URL)
    await manager.init(echo=False)
    yield manager
    await manager.close()


@pytest_asyncio.fixture
async def repo(db):
    """Create a repository backed by the test database."""
    return TradingRepository(db)


@pytest_asyncio.fixture
async def seeded_repo(repo):
    """Repository with pre-seeded test data."""
    # Create 2 sessions
    s1 = await repo.create_session("sess-1", 100_000_000.0, "manual")
    s2 = await repo.create_session("sess-2", 200_000_000.0, "ai-agent")

    # Add trades to session 1
    for i in range(5):
        is_win = i % 2 == 0
        await repo.save_trade({
            "session_id": "sess-1",
            "entry_time": datetime(2025, 1, 1, 9, 0) + timedelta(hours=i),
            "exit_time": datetime(2025, 1, 1, 9, 30) + timedelta(hours=i),
            "direction": "LONG" if i % 2 == 0 else "SHORT",
            "volume": 1,
            "entry_price": 1300.0 + i,
            "exit_price": 1301.0 + i if is_win else 1299.0 + i,
            "commission": 7250.0,
            "tax": 1300.0,
            "gross_pnl": 100_000.0 if is_win else -100_000.0,
            "net_pnl": 91_450.0 if is_win else -108_550.0,
            "status": "closed",
        })

    # Add equity snapshots to session 1
    for i in range(10):
        await repo.save_equity_snapshot({
            "session_id": "sess-1",
            "timestamp": datetime(2025, 1, 1, 9, 0) + timedelta(minutes=i * 10),
            "equity": 100_000_000.0 + (i * 50_000),
            "pnl_realized": i * 50_000.0,
            "pnl_unrealized": 0.0,
            "regime": "bull" if i % 2 == 0 else "bear",
            "session_name": "CONT1",
        })

    return repo


# ── Test Class 1: Database Manager ──────────────────────────

class TestDatabaseManager:
    @pytest.mark.asyncio
    async def test_init_creates_tables(self, db):
        """Tables should be created on init."""
        async with db.engine.connect() as conn:
            # SQLite: check sqlite_master for tables
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            )
            tables = [row[0] for row in result.fetchall()]
            assert "trading_sessions" in tables
            assert "trades" in tables
            assert "equity_snapshots" in tables

    @pytest.mark.asyncio
    async def test_session_factory(self, db):
        """Session factory should produce valid async sessions."""
        async with db.session() as s:
            result = await s.execute(text("SELECT 1"))
            assert result.scalar() == 1

    @pytest.mark.asyncio
    async def test_close_and_reopen(self):
        """Can close and re-init the database."""
        manager = DatabaseManager(url=SQLITE_URL)
        await manager.init()
        assert manager._engine is not None
        await manager.close()
        assert manager._engine is None

    @pytest.mark.asyncio
    async def test_not_initialized_raises(self):
        """Accessing session/engine before init raises RuntimeError."""
        manager = DatabaseManager(url=SQLITE_URL)
        with pytest.raises(RuntimeError, match="not initialized"):
            manager.session()
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = manager.engine


# ── Test Class 2: TradingSession Model ──────────────────────

class TestTradingSessionModel:
    @pytest.mark.asyncio
    async def test_create_session(self, repo):
        model = await repo.create_session("test-sess", 100_000_000.0, "manual")
        assert model.id == "test-sess"
        assert model.initial_balance == 100_000_000.0
        assert model.status == "active"
        assert model.strategy == "manual"

    @pytest.mark.asyncio
    async def test_to_dict(self, repo):
        model = await repo.create_session("dict-test", 50_000_000.0)
        d = model.to_dict()
        assert d["id"] == "dict-test"
        assert d["initial_balance"] == 50_000_000.0
        assert "started_at" in d
        assert d["status"] == "active"

    @pytest.mark.asyncio
    async def test_complete_session(self, repo):
        await repo.create_session("comp-sess", 100_000_000.0)
        await repo.complete_session("comp-sess")
        model = await repo.get_session("comp-sess")
        assert model.status == "completed"
        assert model.ended_at is not None

    @pytest.mark.asyncio
    async def test_delete_session(self, repo):
        await repo.create_session("del-sess", 100_000_000.0)
        result = await repo.delete_session("del-sess")
        assert result is True
        assert await repo.get_session("del-sess") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, repo):
        result = await repo.delete_session("nope")
        assert result is False


# ── Test Class 3: Trade Model ───────────────────────────────

class TestTradeModel:
    @pytest.mark.asyncio
    async def test_save_trade(self, repo):
        await repo.create_session("trade-sess", 100_000_000.0)
        trade = await repo.save_trade({
            "session_id": "trade-sess",
            "entry_time": datetime(2025, 1, 1, 9, 0),
            "exit_time": datetime(2025, 1, 1, 9, 30),
            "direction": "LONG",
            "volume": 2,
            "entry_price": 1300.0,
            "exit_price": 1305.0,
            "commission": 14500.0,
            "tax": 2600.0,
            "gross_pnl": 1_000_000.0,
            "net_pnl": 982_900.0,
            "status": "closed",
        })
        assert trade.id is not None
        assert trade.direction == "LONG"
        assert trade.volume == 2
        assert trade.net_pnl == 982_900.0

    @pytest.mark.asyncio
    async def test_trade_to_dict(self, repo):
        await repo.create_session("td-sess", 100_000_000.0)
        trade = await repo.save_trade({
            "session_id": "td-sess",
            "entry_time": "2025-01-01T09:00:00",
            "direction": "SHORT",
            "volume": 1,
            "entry_price": 1300.0,
            "status": "open",
        })
        d = trade.to_dict()
        assert d["direction"] == "SHORT"
        assert d["status"] == "open"
        assert d["entry_price"] == 1300.0


# ── Test Class 4: Equity Snapshot Model ─────────────────────

class TestEquitySnapshotModel:
    @pytest.mark.asyncio
    async def test_save_snapshot(self, repo):
        await repo.create_session("snap-sess", 100_000_000.0)
        snap = await repo.save_equity_snapshot({
            "session_id": "snap-sess",
            "timestamp": datetime(2025, 1, 1, 9, 0),
            "equity": 100_500_000.0,
            "pnl_realized": 500_000.0,
            "pnl_unrealized": 0.0,
            "regime": "bull",
            "session_name": "CONT1",
        })
        assert snap.id is not None
        assert snap.equity == 100_500_000.0
        assert snap.regime == "bull"

    @pytest.mark.asyncio
    async def test_bulk_save(self, repo):
        await repo.create_session("bulk-sess", 100_000_000.0)
        snaps = [
            {
                "session_id": "bulk-sess",
                "timestamp": datetime(2025, 1, 1, 9, i),
                "equity": 100_000_000.0 + i * 10_000,
            }
            for i in range(20)
        ]
        await repo.save_equity_snapshots_bulk(snaps)
        curve = await repo.get_equity_curve("bulk-sess", limit=100)
        assert len(curve) == 20

    @pytest.mark.asyncio
    async def test_snapshot_to_dict(self, repo):
        await repo.create_session("sd-sess", 100_000_000.0)
        snap = await repo.save_equity_snapshot({
            "session_id": "sd-sess",
            "timestamp": datetime(2025, 1, 1, 9, 0),
            "equity": 100_000_000.0,
        })
        d = snap.to_dict()
        assert d["equity"] == 100_000_000.0
        assert "timestamp" in d


# ── Test Class 5: Repository Session Operations ─────────────

class TestRepoSessions:
    @pytest.mark.asyncio
    async def test_list_sessions(self, seeded_repo):
        sessions = await seeded_repo.list_sessions()
        assert len(sessions) == 2
        # Should be ordered by started_at desc
        assert sessions[0].id == "sess-2"
        assert sessions[1].id == "sess-1"

    @pytest.mark.asyncio
    async def test_list_sessions_with_status_filter(self, seeded_repo):
        await seeded_repo.complete_session("sess-1")
        active = await seeded_repo.list_sessions(status="active")
        assert len(active) == 1
        assert active[0].id == "sess-2"

    @pytest.mark.asyncio
    async def test_count_sessions(self, seeded_repo):
        total = await seeded_repo.count_sessions()
        assert total == 2

    @pytest.mark.asyncio
    async def test_update_session_metrics(self, seeded_repo):
        await seeded_repo.update_session_metrics(
            session_id="sess-1",
            final_pnl=-34_250.0,
            total_trades=5,
            win_rate=0.6,
            max_drawdown=0.002,
            sharpe_ratio=0.85,
            total_commission=36_250.0,
            total_tax=6_500.0,
        )
        model = await seeded_repo.get_session("sess-1")
        assert model.final_pnl == -34_250.0
        assert model.total_trades == 5
        assert model.win_rate == 0.6


# ── Test Class 6: Repository Trade Operations ───────────────

class TestRepoTrades:
    @pytest.mark.asyncio
    async def test_get_trades_paginated(self, seeded_repo):
        trades, total = await seeded_repo.get_trades("sess-1", page=1, page_size=3)
        assert total == 5
        assert len(trades) == 3

    @pytest.mark.asyncio
    async def test_get_trades_page_2(self, seeded_repo):
        trades, total = await seeded_repo.get_trades("sess-1", page=2, page_size=3)
        assert total == 5
        assert len(trades) == 2

    @pytest.mark.asyncio
    async def test_get_trade_stats(self, seeded_repo):
        stats = await seeded_repo.get_session_trade_stats("sess-1")
        assert stats["total_trades"] == 5
        assert stats["total_commission"] == 7250.0 * 5
        # 3 wins + 2 losses = 3*91450 + 2*(-108550) = 274350 - 217100 = 57250
        assert abs(stats["total_pnl"] - 57_250.0) < 1.0

    @pytest.mark.asyncio
    async def test_empty_session_trades(self, seeded_repo):
        trades, total = await seeded_repo.get_trades("sess-2")
        assert total == 0
        assert len(trades) == 0


# ── Test Class 7: Repository Equity Operations ──────────────

class TestRepoEquity:
    @pytest.mark.asyncio
    async def test_get_equity_curve(self, seeded_repo):
        curve = await seeded_repo.get_equity_curve("sess-1")
        assert len(curve) == 10
        # Should be in chronological order
        assert curve[0].timestamp < curve[-1].timestamp

    @pytest.mark.asyncio
    async def test_equity_curve_limit(self, seeded_repo):
        curve = await seeded_repo.get_equity_curve("sess-1", limit=5)
        assert len(curve) == 5

    @pytest.mark.asyncio
    async def test_empty_session_equity(self, seeded_repo):
        curve = await seeded_repo.get_equity_curve("sess-2")
        assert len(curve) == 0


# ── Test Class 8: AutoSaver ─────────────────────────────────

class TestAutoSaver:
    @pytest.mark.asyncio
    async def test_ensure_session_persisted(self, repo):
        engine = MagicMock()
        engine.initial_balance = 100_000_000.0
        engine.strategy = "manual"

        saver = AutoSaver(repo)
        await saver.ensure_session_persisted("auto-sess", engine)

        model = await repo.get_session("auto-sess")
        assert model is not None
        assert model.initial_balance == 100_000_000.0

    @pytest.mark.asyncio
    async def test_ensure_session_idempotent(self, repo):
        engine = MagicMock()
        engine.initial_balance = 100_000_000.0
        engine.strategy = "manual"

        saver = AutoSaver(repo)
        await saver.ensure_session_persisted("idem-sess", engine)
        await saver.ensure_session_persisted("idem-sess", engine)  # no error

        count = await repo.count_sessions()
        assert count == 1

    @pytest.mark.asyncio
    async def test_on_trade_closed(self, repo):
        await repo.create_session("trade-hook-sess", 100_000_000.0)
        saver = AutoSaver(repo)

        trade = {
            "entry_time": "2025-01-01T09:00:00",
            "exit_time": "2025-01-01T09:30:00",
            "type": "LONG",
            "volume": 1,
            "entry_price": 1300.0,
            "exit_price": 1305.0,
            "commission": 7250.0,
            "tax": 1300.0,
            "gross_pnl": 500_000.0,
            "net_pnl": 491_450.0,
        }
        await saver.on_trade_closed("trade-hook-sess", trade)

        trades, total = await repo.get_trades("trade-hook-sess")
        assert total == 1
        assert trades[0].net_pnl == 491_450.0

    @pytest.mark.asyncio
    async def test_save_new_trades_detection(self, repo):
        """AutoSaver detects new trades from engine.trade_history."""
        await repo.create_session("detect-sess", 100_000_000.0)
        saver = AutoSaver(repo)

        engine = MagicMock()
        engine.trade_history = [
            {
                "entry_time": "2025-01-01T09:00:00",
                "exit_time": "2025-01-01T09:30:00",
                "type": "LONG",
                "volume": 1,
                "entry_price": 1300.0,
                "exit_price": 1301.0,
                "commission": 7250.0,
                "tax": 1300.0,
                "gross_pnl": 100_000.0,
                "net_pnl": 91_450.0,
            }
        ]
        await saver._save_new_trades("detect-sess", engine)

        trades, total = await repo.get_trades("detect-sess")
        assert total == 1

        # Call again — should NOT duplicate
        await saver._save_new_trades("detect-sess", engine)
        trades, total = await repo.get_trades("detect-sess")
        assert total == 1


# ── Test Class 9: History API Endpoints ──────────────────────

class TestHistoryAPI:
    @pytest.mark.asyncio
    async def test_list_sessions_endpoint(self, seeded_repo):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        test_app = FastAPI()
        init_history_router(seeded_repo)
        test_app.include_router(history_router)

        client = TestClient(test_app)
        resp = client.get("/api/v1/history/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["sessions"]) == 2

    @pytest.mark.asyncio
    async def test_get_session_detail(self, seeded_repo):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        test_app = FastAPI()
        init_history_router(seeded_repo)
        test_app.include_router(history_router)

        client = TestClient(test_app)
        resp = client.get("/api/v1/history/sessions/sess-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "sess-1"
        assert "trade_stats" in data
        assert data["trade_stats"]["total_trades"] == 5

    @pytest.mark.asyncio
    async def test_session_not_found(self, seeded_repo):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        test_app = FastAPI()
        init_history_router(seeded_repo)
        test_app.include_router(history_router)

        client = TestClient(test_app)
        resp = client.get("/api/v1/history/sessions/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_session_trades_endpoint(self, seeded_repo):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        test_app = FastAPI()
        init_history_router(seeded_repo)
        test_app.include_router(history_router)

        client = TestClient(test_app)
        resp = client.get("/api/v1/history/sessions/sess-1/trades?page=1&page_size=3")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["trades"]) == 3

    @pytest.mark.asyncio
    async def test_session_equity_curve_endpoint(self, seeded_repo):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        test_app = FastAPI()
        init_history_router(seeded_repo)
        test_app.include_router(history_router)

        client = TestClient(test_app)
        resp = client.get("/api/v1/history/sessions/sess-1/equity-curve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["points"] == 10
        assert len(data["snapshots"]) == 10


# ── Test Class 10: Session Comparison ────────────────────────

class TestSessionComparison:
    @pytest.mark.asyncio
    async def test_compare_two_sessions(self, seeded_repo):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        test_app = FastAPI()
        init_history_router(seeded_repo)
        test_app.include_router(history_router)

        client = TestClient(test_app)
        resp = client.post(
            "/api/v1/history/sessions/compare",
            json=["sess-1", "sess-2"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sessions"]) == 2
        assert data["missing"] == []

    @pytest.mark.asyncio
    async def test_compare_with_missing(self, seeded_repo):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        test_app = FastAPI()
        init_history_router(seeded_repo)
        test_app.include_router(history_router)

        client = TestClient(test_app)
        resp = client.post(
            "/api/v1/history/sessions/compare",
            json=["sess-1", "nonexistent"],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sessions"]) == 1
        assert "nonexistent" in data["missing"]

    @pytest.mark.asyncio
    async def test_compare_too_few(self, seeded_repo):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        test_app = FastAPI()
        init_history_router(seeded_repo)
        test_app.include_router(history_router)

        client = TestClient(test_app)
        resp = client.post(
            "/api/v1/history/sessions/compare",
            json=["sess-1"],
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_compare_initial_balances(self, seeded_repo):
        """Comparison should show different initial balances."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        test_app = FastAPI()
        init_history_router(seeded_repo)
        test_app.include_router(history_router)

        client = TestClient(test_app)
        resp = client.post(
            "/api/v1/history/sessions/compare",
            json=["sess-1", "sess-2"],
        )
        data = resp.json()
        balances = {s["id"]: s["initial_balance"] for s in data["sessions"]}
        assert balances["sess-1"] == 100_000_000.0
        assert balances["sess-2"] == 200_000_000.0
