"""Phase 4 tests — Agent Integration (10 test classes, ~40 tests).

1. AgentConfig model
2. AgentManager registration + isolation
3. AgentManager order handling
4. PredictionSubscriber sync processing
5. PredictionSubscriber filtering
6. LeaderboardCalculator ranking
7. TournamentManager lifecycle
8. TournamentManager tick processing
9. Agent API endpoints
10. Tournament API endpoints
"""

import pytest
from datetime import datetime

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.session import SessionManager
from app.agents.agent_manager import AgentManager, AgentConfig
from app.agents.subscriber import PredictionSubscriber
from app.agents.leaderboard import LeaderboardCalculator, SortMetric
from app.agents.tournament import TournamentManager, TournamentConfig, TournamentStatus


@pytest.fixture
def session_mgr():
    return SessionManager()


@pytest.fixture
def agent_mgr(session_mgr):
    return AgentManager(session_mgr)


@pytest.fixture
def tournament(session_mgr):
    tmgr = TournamentManager(session_mgr)
    tmgr.create_tournament(TournamentConfig(name="test-cup", initial_balance=100_000_000.0))
    return tmgr


def _make_config(agent_id="agent-1", name="Bot Alpha", **kwargs):
    return AgentConfig(agent_id=agent_id, name=name, **kwargs)


def _seed_price(engine, price=1300.0):
    """Set a current price on the engine so orders work."""
    engine.process_tick("2025-01-01T09:15:00", price, "bull")


# ── Test Class 1: AgentConfig ───────────────────────────────

class TestAgentConfig:
    def test_defaults(self):
        cfg = AgentConfig(agent_id="a1", name="Bot")
        assert cfg.confidence_threshold == 0.6
        assert cfg.max_volume == 10
        assert cfg.enabled is True
        assert cfg.strategy == "ai"

    def test_to_dict(self):
        cfg = _make_config(confidence_threshold=0.8)
        d = cfg.to_dict()
        assert d["agent_id"] == "agent-1"
        assert d["confidence_threshold"] == 0.8
        assert "enabled" in d

    def test_custom_values(self):
        cfg = AgentConfig(
            agent_id="x", name="X", strategy="rl",
            initial_balance=200_000_000, max_volume=50,
        )
        assert cfg.strategy == "rl"
        assert cfg.initial_balance == 200_000_000


# ── Test Class 2: AgentManager Registration ─────────────────

class TestAgentManagerRegistration:
    def test_register_agent(self, agent_mgr):
        cfg = _make_config()
        engine = agent_mgr.register_agent(cfg)
        assert engine.session_id == "agent_agent-1"
        assert agent_mgr.is_registered("agent-1")

    def test_register_duplicate_raises(self, agent_mgr):
        agent_mgr.register_agent(_make_config("a1", "Bot"))
        with pytest.raises(ValueError, match="already registered"):
            agent_mgr.register_agent(_make_config("a1", "Bot2"))

    def test_unregister_agent(self, agent_mgr):
        agent_mgr.register_agent(_make_config())
        assert agent_mgr.unregister_agent("agent-1") is True
        assert not agent_mgr.is_registered("agent-1")

    def test_unregister_nonexistent(self, agent_mgr):
        assert agent_mgr.unregister_agent("nope") is False

    def test_list_agents(self, agent_mgr):
        agent_mgr.register_agent(_make_config("a1", "Alpha"))
        agent_mgr.register_agent(_make_config("a2", "Beta"))
        agents = agent_mgr.list_agents()
        assert len(agents) == 2
        names = {a["name"] for a in agents}
        assert names == {"Alpha", "Beta"}

    def test_agent_isolation(self, agent_mgr):
        """Each agent gets its own balance."""
        agent_mgr.register_agent(_make_config("a1", "A", initial_balance=100_000_000))
        agent_mgr.register_agent(_make_config("a2", "B", initial_balance=200_000_000))
        e1 = agent_mgr.get_agent_engine("a1")
        e2 = agent_mgr.get_agent_engine("a2")
        assert e1.balance == 100_000_000
        assert e2.balance == 200_000_000


# ── Test Class 3: AgentManager Order Handling ────────────────

class TestAgentManagerOrders:
    def test_place_order(self, agent_mgr):
        agent_mgr.register_agent(_make_config())
        engine = agent_mgr.get_agent_engine("agent-1")
        _seed_price(engine)
        result = agent_mgr.place_agent_order("agent-1", "LONG", 2)
        assert result["action"] == "OPEN"
        assert result["type"] == "LONG"

    def test_volume_capped_by_max(self, agent_mgr):
        agent_mgr.register_agent(_make_config(max_volume=3))
        engine = agent_mgr.get_agent_engine("agent-1")
        _seed_price(engine)
        result = agent_mgr.place_agent_order("agent-1", "LONG", 100)
        assert result["volume"] == 3

    def test_order_unregistered_raises(self, agent_mgr):
        with pytest.raises(ValueError, match="not registered"):
            agent_mgr.place_agent_order("ghost", "LONG", 1)

    def test_order_disabled_agent_raises(self, agent_mgr):
        cfg = _make_config(enabled=False)
        agent_mgr.register_agent(cfg)
        with pytest.raises(ValueError, match="disabled"):
            agent_mgr.place_agent_order("agent-1", "LONG", 1)


# ── Test Class 4: PredictionSubscriber Sync Processing ───────

class TestPredictionSubscriberSync:
    def test_process_long_prediction(self, agent_mgr):
        agent_mgr.register_agent(_make_config(confidence_threshold=0.5))
        engine = agent_mgr.get_agent_engine("agent-1")
        _seed_price(engine)

        sub = PredictionSubscriber(agent_mgr)
        result = sub.process_prediction_sync({
            "agent_id": "agent-1",
            "action": "LONG",
            "confidence": 0.8,
            "volume": 1,
        })
        assert result["status"] == "ok"
        assert sub.stats["orders_placed"] == 1

    def test_process_close_prediction(self, agent_mgr):
        agent_mgr.register_agent(_make_config(confidence_threshold=0.5))
        engine = agent_mgr.get_agent_engine("agent-1")
        _seed_price(engine)
        engine.place_order("LONG", 1)

        sub = PredictionSubscriber(agent_mgr)
        result = sub.process_prediction_sync({
            "agent_id": "agent-1",
            "action": "CLOSE",
            "confidence": 0.9,
        })
        assert result["status"] == "ok"

    def test_stats_tracking(self, agent_mgr):
        agent_mgr.register_agent(_make_config(confidence_threshold=0.5))
        engine = agent_mgr.get_agent_engine("agent-1")
        _seed_price(engine)

        sub = PredictionSubscriber(agent_mgr)
        sub.process_prediction_sync({"agent_id": "agent-1", "action": "LONG", "confidence": 0.8, "volume": 1})
        sub.process_prediction_sync({"agent_id": "agent-1", "action": "LONG", "confidence": 0.3, "volume": 1})

        stats = sub.stats
        assert stats["messages_received"] == 2
        assert stats["orders_placed"] == 1
        assert stats["orders_rejected"] == 1


# ── Test Class 5: PredictionSubscriber Filtering ─────────────

class TestPredictionFiltering:
    def test_low_confidence_rejected(self, agent_mgr):
        agent_mgr.register_agent(_make_config(confidence_threshold=0.7))
        sub = PredictionSubscriber(agent_mgr)
        result = sub.process_prediction_sync({
            "agent_id": "agent-1", "action": "LONG", "confidence": 0.5,
        })
        assert result["status"] == "rejected"
        assert result["reason"] == "low confidence"

    def test_unregistered_agent_rejected(self, agent_mgr):
        sub = PredictionSubscriber(agent_mgr)
        result = sub.process_prediction_sync({
            "agent_id": "unknown", "action": "LONG", "confidence": 0.9,
        })
        assert result["status"] == "rejected"
        assert result["reason"] == "unregistered agent"

    def test_disabled_agent_rejected(self, agent_mgr):
        agent_mgr.register_agent(_make_config(enabled=False))
        sub = PredictionSubscriber(agent_mgr)
        result = sub.process_prediction_sync({
            "agent_id": "agent-1", "action": "LONG", "confidence": 0.9,
        })
        assert result["status"] == "rejected"
        assert result["reason"] == "agent disabled"

    def test_missing_fields_rejected(self, agent_mgr):
        sub = PredictionSubscriber(agent_mgr)
        result = sub.process_prediction_sync({"action": "LONG"})
        assert result["status"] == "rejected"

    def test_invalid_action_rejected(self, agent_mgr):
        agent_mgr.register_agent(_make_config(confidence_threshold=0.5))
        sub = PredictionSubscriber(agent_mgr)
        result = sub.process_prediction_sync({
            "agent_id": "agent-1", "action": "BUY", "confidence": 0.9,
        })
        assert result["status"] == "rejected"


# ── Test Class 6: LeaderboardCalculator ──────────────────────

class TestLeaderboard:
    def _setup_agents(self, agent_mgr):
        """Register 3 agents with different performance."""
        for i, (name, bal) in enumerate([("Alpha", 100e6), ("Beta", 100e6), ("Gamma", 100e6)]):
            cfg = _make_config(f"agent-{i}", name, initial_balance=bal, confidence_threshold=0.1)
            agent_mgr.register_agent(cfg)
            engine = agent_mgr.get_agent_engine(f"agent-{i}")
            _seed_price(engine)

        # Alpha: 1 winning trade (+5 points)
        e0 = agent_mgr.get_agent_engine("agent-0")
        e0.place_order("LONG", 1)
        e0.process_tick("2025-01-01T09:30:00", 1305.0, "bull")
        e0.close_position()

        # Beta: 1 losing trade (-3 points)
        e1 = agent_mgr.get_agent_engine("agent-1")
        e1.place_order("SHORT", 1)
        e1.process_tick("2025-01-01T09:30:00", 1303.0, "bull")
        e1.close_position()

        # Gamma: no trades
        return agent_mgr

    def test_default_ranking_by_pnl(self, agent_mgr):
        self._setup_agents(agent_mgr)
        lb = LeaderboardCalculator(agent_mgr)
        entries = lb.get_leaderboard()
        assert len(entries) == 3
        assert entries[0]["name"] == "Alpha"  # highest PnL
        assert entries[0]["rank"] == 1

    def test_ranking_by_trades(self, agent_mgr):
        self._setup_agents(agent_mgr)
        lb = LeaderboardCalculator(agent_mgr)
        entries = lb.get_leaderboard(sort_by=SortMetric.TRADES)
        # Alpha and Beta both have 1 trade, Gamma has 0
        assert entries[-1]["name"] == "Gamma"

    def test_top_n(self, agent_mgr):
        self._setup_agents(agent_mgr)
        lb = LeaderboardCalculator(agent_mgr)
        entries = lb.get_leaderboard(top_n=1)
        assert len(entries) == 1
        assert entries[0]["rank"] == 1

    def test_agent_stats(self, agent_mgr):
        self._setup_agents(agent_mgr)
        lb = LeaderboardCalculator(agent_mgr)
        stats = lb.get_agent_stats("agent-0")
        assert stats is not None
        assert stats["trade_count"] == 1
        assert stats["name"] == "Alpha"

    def test_agent_stats_nonexistent(self, agent_mgr):
        lb = LeaderboardCalculator(agent_mgr)
        assert lb.get_agent_stats("ghost") is None


# ── Test Class 7: TournamentManager Lifecycle ────────────────

class TestTournamentLifecycle:
    def test_create_tournament(self, session_mgr):
        tmgr = TournamentManager(session_mgr)
        tmgr.create_tournament(TournamentConfig(name="test-cup"))
        assert tmgr.status == TournamentStatus.PENDING

    def test_full_lifecycle(self, tournament):
        # Add agents
        tournament.add_agent(_make_config("a1", "Alpha"))
        tournament.add_agent(_make_config("a2", "Beta"))

        # Start
        tournament.start()
        assert tournament.status == TournamentStatus.RUNNING

        # Pause/Resume
        tournament.pause()
        assert tournament.status == TournamentStatus.PAUSED
        tournament.resume()
        assert tournament.status == TournamentStatus.RUNNING

        # Stop
        tournament.stop()
        assert tournament.status == TournamentStatus.COMPLETED

    def test_start_without_agents_raises(self, tournament):
        with pytest.raises(ValueError, match="No agents"):
            tournament.start()

    def test_double_start_raises(self, tournament):
        tournament.add_agent(_make_config("a1", "A"))
        tournament.start()
        with pytest.raises(ValueError, match="already running"):
            tournament.start()

    def test_max_agents_enforced(self, session_mgr):
        tmgr = TournamentManager(session_mgr)
        tmgr.create_tournament(TournamentConfig(name="tiny", max_agents=2))
        tmgr.add_agent(_make_config("a1", "A"))
        tmgr.add_agent(_make_config("a2", "B"))
        with pytest.raises(ValueError, match="full"):
            tmgr.add_agent(_make_config("a3", "C"))

    def test_cancel(self, tournament):
        tournament.add_agent(_make_config("a1", "A"))
        tournament.start()
        tournament.cancel()
        assert tournament.status == TournamentStatus.CANCELLED


# ── Test Class 8: Tournament Tick Processing ─────────────────

class TestTournamentTicks:
    def test_ticks_reach_all_agents(self, tournament):
        tournament.add_agent(_make_config("a1", "Alpha"))
        tournament.add_agent(_make_config("a2", "Beta"))
        tournament.start()

        tournament.process_tick("2025-01-01T09:00:00", 1300.0, "bull")
        tournament.process_tick("2025-01-01T09:01:00", 1301.0, "bull")

        e1 = tournament.agent_manager.get_agent_engine("a1")
        e2 = tournament.agent_manager.get_agent_engine("a2")
        assert e1.current_price == 1301.0
        assert e2.current_price == 1301.0

    def test_ticks_ignored_when_not_running(self, tournament):
        tournament.add_agent(_make_config("a1", "Alpha"))
        # Not started yet
        tournament.process_tick("2025-01-01T09:00:00", 1300.0)
        e = tournament.agent_manager.get_agent_engine("a1")
        assert e.current_price == 0.0  # Not processed

    def test_standings_update_after_trades(self, tournament):
        tournament.add_agent(_make_config("a1", "Alpha", confidence_threshold=0.1))
        tournament.add_agent(_make_config("a2", "Beta", confidence_threshold=0.1))
        tournament.start()

        tournament.process_tick("2025-01-01T09:00:00", 1300.0, "bull")

        # Alpha goes long
        tournament.agent_manager.place_agent_order("a1", "LONG", 1)
        tournament.process_tick("2025-01-01T09:15:00", 1310.0, "bull")

        standings = tournament.get_standings()
        assert standings["tick_count"] == 2
        assert standings["agent_count"] == 2
        # Alpha should lead since it has unrealized gains
        lb = standings["leaderboard"]
        assert lb[0]["agent_id"] == "a1"

    def test_get_state(self, tournament):
        tournament.add_agent(_make_config("a1", "Alpha"))
        state = tournament.get_state()
        assert state["config"]["name"] == "test-cup"
        assert state["status"] == "pending"
        assert len(state["agents"]) == 1


# ── Test Class 9: Agent API Endpoints ────────────────────────

class TestAgentAPI:
    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.agents.agent_api import init_agent_router, router

        test_app = FastAPI()
        smgr = SessionManager()
        smgr.create_session("default")
        init_agent_router(smgr)
        test_app.include_router(router)
        return TestClient(test_app)

    def test_register_agent(self, client):
        resp = client.post("/api/v1/agents/register", json={
            "agent_id": "bot-1", "name": "TestBot",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_list_agents(self, client):
        client.post("/api/v1/agents/register", json={"agent_id": "b1", "name": "B1"})
        resp = client.get("/api/v1/agents/")
        assert resp.status_code == 200
        assert len(resp.json()["agents"]) >= 1

    def test_get_agent(self, client):
        client.post("/api/v1/agents/register", json={"agent_id": "b2", "name": "B2"})
        resp = client.get("/api/v1/agents/b2")
        assert resp.status_code == 200
        assert resp.json()["name"] == "B2"

    def test_delete_agent(self, client):
        client.post("/api/v1/agents/register", json={"agent_id": "b3", "name": "B3"})
        resp = client.delete("/api/v1/agents/b3")
        assert resp.status_code == 200
        resp2 = client.get("/api/v1/agents/b3")
        assert resp2.status_code == 404

    def test_prediction_stats(self, client):
        resp = client.get("/api/v1/agents/predict/stats")
        assert resp.status_code == 200
        assert "messages_received" in resp.json()


# ── Test Class 10: Tournament API Endpoints ──────────────────

class TestTournamentAPI:
    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.agents.agent_api import init_agent_router, router

        test_app = FastAPI()
        smgr = SessionManager()
        smgr.create_session("default")
        init_agent_router(smgr)
        test_app.include_router(router)
        return TestClient(test_app)

    def test_create_tournament(self, client):
        resp = client.post("/api/v1/agents/tournament/create", json={
            "name": "API Cup",
        })
        assert resp.status_code == 200
        assert resp.json()["tournament"] == "API Cup"

    def test_tournament_lifecycle_via_api(self, client):
        client.post("/api/v1/agents/tournament/create", json={"name": "LC Cup"})
        client.post("/api/v1/agents/register", json={"agent_id": "t1", "name": "T1"})

        resp = client.post("/api/v1/agents/tournament/start")
        assert resp.status_code == 200

        resp = client.post("/api/v1/agents/tournament/pause")
        assert resp.status_code == 200

        resp = client.post("/api/v1/agents/tournament/resume")
        assert resp.status_code == 200

        resp = client.post("/api/v1/agents/tournament/stop")
        assert resp.status_code == 200

    def test_tournament_standings(self, client):
        client.post("/api/v1/agents/tournament/create", json={"name": "Stand Cup"})
        client.post("/api/v1/agents/register", json={"agent_id": "s1", "name": "S1"})
        resp = client.get("/api/v1/agents/tournament/standings")
        assert resp.status_code == 200
        assert "leaderboard" in resp.json()

    def test_tournament_state(self, client):
        client.post("/api/v1/agents/tournament/create", json={"name": "State Cup"})
        resp = client.get("/api/v1/agents/tournament/state")
        assert resp.status_code == 200
        assert resp.json()["config"]["name"] == "State Cup"

    def test_leaderboard_endpoint(self, client):
        client.post("/api/v1/agents/tournament/create", json={"name": "LB Cup"})
        client.post("/api/v1/agents/register", json={"agent_id": "l1", "name": "L1"})
        client.post("/api/v1/agents/register", json={"agent_id": "l2", "name": "L2"})
        resp = client.get("/api/v1/agents/leaderboard/rankings")
        assert resp.status_code == 200
        assert len(resp.json()["entries"]) == 2
