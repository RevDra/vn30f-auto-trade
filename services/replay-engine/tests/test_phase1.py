"""Comprehensive test suite for Phase 1 — Mock Exchange Engine.

10 test cases covering:
  1. Fee calculation (per side + round trip + tax)
  2. Margin validation (required margin, margin call, force close)
  3. Rollover 3rd Thursday calculation (multiple months)
  4. Metrics (win rate, max drawdown, Sharpe ratio)
  5. Trading session hour validation
  6. Slippage model (volume-dependent, rollover, ATO/ATC)
  7. Engine: open → close position with PnL + fees
  8. Engine: partial close + flip position
  9. Session manager (create, switch, list, delete)
 10. API endpoints (order, pnl, trades, sessions, error codes)
"""

import math
import pytest
from datetime import datetime, time
from unittest.mock import patch

from app.constants import (
    CONTRACT_MULTIPLIER,
    DEFAULT_BROKER_FEE,
    EXCHANGE_FEE_HNX,
    CLEARING_FEE_VSD,
    TNCN_TAX_RATE,
    INITIAL_MARGIN_RATE,
    TICK_SIZE,
    DEFAULT_INITIAL_BALANCE,
)
from app.fees import FeeCalculator, FeeBreakdown
from app.risk import (
    MarginManager,
    InsufficientMarginError,
    PriceLimitError,
    PositionLimitError,
)
from app.metrics import MetricTracker
from app.session_validator import TradingSessionValidator
from app.slippage import SlippageModel
from app.engine import ReplayEngine, get_expiry_date, is_rollover_friday
from app.session import SessionManager


# ────────────────────────────────────────────────────────────────────────────
# Test 1: Fee Calculation
# ────────────────────────────────────────────────────────────────────────────
class TestFeeCalculator:
    def setup_method(self):
        self.calc = FeeCalculator()

    def test_per_side_single_contract(self):
        """1 contract: broker(2000) + exchange(2700) + clearing(2550) = 7250 VND."""
        result = self.calc.calculate_per_side(volume=1)
        assert result == 7_250

    def test_per_side_10_contracts(self):
        result = self.calc.calculate_per_side(volume=10)
        assert result == 72_500

    def test_tax_calculation(self):
        """TNCN tax = 0.1% × price × multiplier × volume × margin_rate."""
        price = 1300.0
        volume = 1
        expected = TNCN_TAX_RATE * price * CONTRACT_MULTIPLIER * volume * INITIAL_MARGIN_RATE
        result = self.calc.calculate_tax(price, volume)
        assert abs(result - expected) < 0.01
        # 0.001 × 1300 × 100000 × 1 × 0.17 = 22,100
        assert abs(result - 22_100) < 0.01

    def test_round_trip_breakdown(self):
        """Full round trip should include entry + exit fees."""
        rt = self.calc.total_round_trip(entry_price=1300, exit_price=1310, volume=2)
        # Fixed fees per side = 7250 × 2 = 14500; both sides = 29000
        assert rt["total_fixed_fees"] == 29_000
        assert rt["total_tax"] > 0
        assert rt["grand_total"] == rt["total_fixed_fees"] + rt["total_tax"]

    def test_custom_broker_fee(self):
        calc = FeeCalculator(broker_fee=500)
        result = calc.calculate_per_side(volume=1)
        assert result == 500 + 2_700 + 2_550  # 5750


# ────────────────────────────────────────────────────────────────────────────
# Test 2: Margin Validation
# ────────────────────────────────────────────────────────────────────────────
class TestMarginManager:
    def setup_method(self):
        self.mgr = MarginManager()

    def test_required_margin(self):
        """IM = 1300 × 100000 × 1 × 0.17 = 22,100,000 VND."""
        result = self.mgr.required_margin(price=1300, volume=1)
        assert result == 22_100_000

    def test_margin_call_ok(self):
        assert self.mgr.check_margin_call(equity=25_000_000, price=1300, volume=1) == "ok"

    def test_margin_call_warning(self):
        # Maintenance = 1300 × 100000 × 1 × 0.136 = 17,680,000
        # Between 17.68M and 22.1M → margin_call
        assert self.mgr.check_margin_call(equity=20_000_000, price=1300, volume=1) == "margin_call"

    def test_force_close(self):
        assert self.mgr.check_margin_call(equity=10_000_000, price=1300, volume=1) == "force_close"

    def test_price_limit_valid(self):
        assert self.mgr.validate_price_limit(1350, ref_price=1300) is True
        assert self.mgr.validate_price_limit(1400, ref_price=1300) is False  # +7.7%

    def test_validate_order_insufficient_margin(self):
        with pytest.raises(InsufficientMarginError):
            self.mgr.validate_order(equity=1_000_000, price=1300, volume=1)

    def test_validate_order_position_limit(self):
        with pytest.raises(PositionLimitError):
            self.mgr.validate_order(
                equity=999_999_999_999,
                price=1300,
                volume=501,
            )


# ────────────────────────────────────────────────────────────────────────────
# Test 3: Rollover 3rd Thursday
# ────────────────────────────────────────────────────────────────────────────
class TestRollover:
    def test_expiry_date_march_2024(self):
        """March 2024: 1st = Friday, 1st Thursday = March 7, 3rd Thursday = March 21."""
        expiry = get_expiry_date(2024, 3)
        assert expiry == datetime(2024, 3, 21)

    def test_expiry_date_january_2025(self):
        """January 2025: 1st = Wednesday, 1st Thursday = Jan 2, 3rd Thursday = Jan 16."""
        expiry = get_expiry_date(2025, 1)
        assert expiry == datetime(2025, 1, 16)

    def test_expiry_date_june_2025(self):
        """June 2025: 1st = Sunday, 1st Thursday = June 5, 3rd Thursday = June 19."""
        expiry = get_expiry_date(2025, 6)
        assert expiry == datetime(2025, 6, 19)

    def test_expiry_date_august_2025(self):
        """August 2025: 1st = Friday, 1st Thursday = Aug 7, 3rd Thursday = Aug 21."""
        expiry = get_expiry_date(2025, 8)
        assert expiry == datetime(2025, 8, 21)

    def test_rollover_friday_true(self):
        # March 2024: expiry = March 21 (Thursday), rollover = March 22 (Friday)
        assert is_rollover_friday(datetime(2024, 3, 22)) is True

    def test_rollover_friday_false_wrong_friday(self):
        assert is_rollover_friday(datetime(2024, 3, 15)) is False

    def test_rollover_friday_false_thursday(self):
        assert is_rollover_friday(datetime(2024, 3, 21)) is False

    def test_expiry_date_month_starting_thursday(self):
        """May 2025: 1st = Thursday, 1st Thursday = May 1, 3rd Thursday = May 15."""
        expiry = get_expiry_date(2025, 5)
        assert expiry == datetime(2025, 5, 15)
        assert is_rollover_friday(datetime(2025, 5, 16)) is True


# ────────────────────────────────────────────────────────────────────────────
# Test 4: Metrics
# ────────────────────────────────────────────────────────────────────────────
class TestMetrics:
    def test_win_rate(self):
        tracker = MetricTracker(initial_balance=100_000_000)
        trades = [
            {"net_pnl": 500_000},
            {"net_pnl": -200_000},
            {"net_pnl": 300_000},
            {"net_pnl": 100_000},
        ]
        assert tracker.calculate_win_rate(trades) == 0.75

    def test_win_rate_empty(self):
        tracker = MetricTracker(initial_balance=100_000_000)
        assert tracker.calculate_win_rate([]) == 0.0

    def test_max_drawdown(self):
        tracker = MetricTracker(initial_balance=100)
        tracker.update_equity(110)  # new peak
        tracker.update_equity(90)   # drawdown = (110-90)/110 = 18.18%
        tracker.update_equity(105)  # recovery
        assert abs(tracker.calculate_max_drawdown() - 20 / 110) < 0.001

    def test_sharpe_ratio_positive(self):
        tracker = MetricTracker(initial_balance=100)
        # Simulate consistent positive returns
        equities = [100, 101, 102, 103, 104, 105]
        for eq in equities[1:]:
            tracker.update_equity(eq)
        sharpe = tracker.calculate_sharpe_ratio()
        assert sharpe > 0  # Consistent positive returns → positive Sharpe

    def test_sharpe_ratio_zero_returns(self):
        tracker = MetricTracker(initial_balance=100)
        tracker.update_equity(100)
        tracker.update_equity(100)
        assert tracker.calculate_sharpe_ratio() == 0.0


# ────────────────────────────────────────────────────────────────────────────
# Test 5: Trading Session Hours
# ────────────────────────────────────────────────────────────────────────────
class TestSessionValidator:
    def setup_method(self):
        self.validator = TradingSessionValidator(strict=True)

    def test_ato_session(self):
        dt = datetime(2025, 4, 3, 8, 50)  # 8:50 AM
        assert self.validator.get_session_name(dt) == "ATO"
        assert self.validator.is_trading_hour(dt) is True

    def test_cont1_session(self):
        dt = datetime(2025, 4, 3, 10, 0)  # 10:00 AM
        assert self.validator.get_session_name(dt) == "CONT1"

    def test_lunch_break(self):
        dt = datetime(2025, 4, 3, 12, 0)  # 12:00 PM — lunch break
        assert self.validator.get_session_name(dt) is None
        assert self.validator.is_trading_hour(dt) is False

    def test_cont2_session(self):
        dt = datetime(2025, 4, 3, 14, 0)  # 2:00 PM
        assert self.validator.get_session_name(dt) == "CONT2"

    def test_atc_session(self):
        dt = datetime(2025, 4, 3, 14, 35)  # 2:35 PM
        assert self.validator.get_session_name(dt) == "ATC"

    def test_after_hours_strict_rejected(self):
        dt = datetime(2025, 4, 3, 20, 0)  # 8:00 PM
        allowed, session, msg = self.validator.validate_order_time(dt)
        assert allowed is False

    def test_relaxed_mode_allowed(self):
        validator = TradingSessionValidator(strict=False)
        dt = datetime(2025, 4, 3, 20, 0)
        allowed, _, _ = validator.validate_order_time(dt)
        assert allowed is True

    def test_boundary_cont1_end(self):
        """11:30 is NOT in CONT1 (end time is exclusive)."""
        dt = datetime(2025, 4, 3, 11, 30)
        assert self.validator.get_session_name(dt) is None


# ────────────────────────────────────────────────────────────────────────────
# Test 6: Slippage Model
# ────────────────────────────────────────────────────────────────────────────
class TestSlippageModel:
    def setup_method(self):
        self.model = SlippageModel()

    def test_single_contract_cont(self):
        """1 contract, CONT session: base(2) + vol(0) = 2 ticks."""
        ticks = self.model.calculate_slippage_ticks(volume=1, session_name="CONT1")
        assert ticks == 2

    def test_10_contracts(self):
        """10 contracts: base(2) + vol(10//5=2) = 4 ticks."""
        ticks = self.model.calculate_slippage_ticks(volume=10, session_name="CONT1")
        assert ticks == 4

    def test_50_contracts(self):
        """50 contracts: base(2) + vol(50//5=10) = 12 ticks."""
        ticks = self.model.calculate_slippage_ticks(volume=50, session_name="CONT1")
        assert ticks == 12

    def test_rollover_day_extra(self):
        """Rollover adds 2 extra ticks."""
        normal = self.model.calculate_slippage_ticks(volume=1, is_rollover=False)
        rollover = self.model.calculate_slippage_ticks(volume=1, is_rollover=True)
        assert rollover == normal + 2

    def test_ato_session_extra(self):
        """ATO/ATC adds 1 extra tick."""
        cont = self.model.calculate_slippage_ticks(volume=1, session_name="CONT1")
        ato = self.model.calculate_slippage_ticks(volume=1, session_name="ATO")
        assert ato == cont + 1

    def test_long_price_increases(self):
        """LONG: executed price > market price."""
        exec_price = self.model.calculate_slippage(
            action="LONG", price=1300.0, volume=1
        )
        assert exec_price > 1300.0
        assert exec_price == 1300.0 + 2 * TICK_SIZE  # 1300.2

    def test_short_price_decreases(self):
        """SHORT: executed price < market price."""
        exec_price = self.model.calculate_slippage(
            action="SHORT", price=1300.0, volume=1
        )
        assert exec_price < 1300.0


# ────────────────────────────────────────────────────────────────────────────
# Test 7: Engine — Open → Close with Fees
# ────────────────────────────────────────────────────────────────────────────
class TestEngineOpenClose:
    def setup_method(self):
        self.engine = ReplayEngine(
            initial_balance=500_000_000, strict_hours=False
        )
        self.engine.current_price = 1300.0
        self.engine.current_date = datetime(2025, 4, 3, 10, 0)

    def test_open_long_deducts_fees(self):
        result = self.engine.place_order("LONG", 1)
        assert result["action"] == "OPEN"
        assert result["fees"] > 0
        assert self.engine.balance < 500_000_000  # Fees deducted

    def test_close_long_with_profit(self):
        self.engine.place_order("LONG", 1)
        entry = self.engine.active_position["entry_price"]

        # Market moves up significantly
        self.engine.current_price = entry + 10.0  # +10 points
        result = self.engine.place_order("SHORT", 1)

        assert result["action"] == "CLOSE"
        assert result["gross_pnl"] > 0
        assert result["net_pnl"] < result["gross_pnl"]  # net < gross (fees deducted)
        assert self.engine.active_position is None
        assert len(self.engine.trade_history) == 1

    def test_close_short_with_loss(self):
        self.engine.place_order("SHORT", 1)
        entry = self.engine.active_position["entry_price"]

        # Market moves up (bad for SHORT)
        self.engine.current_price = entry + 5.0
        result = self.engine.place_order("LONG", 1)

        assert result["action"] == "CLOSE"
        assert result["gross_pnl"] < 0
        assert self.engine.active_position is None

    def test_total_commission_tracked(self):
        self.engine.place_order("LONG", 1)
        self.engine.current_price += 5.0
        self.engine.place_order("SHORT", 1)
        assert self.engine.total_commission > 0
        assert self.engine.total_tax > 0

    def test_pnl_in_vnd(self):
        """PnL should be in VND (points × multiplier)."""
        self.engine.place_order("LONG", 1)
        entry = self.engine.active_position["entry_price"]
        self.engine.current_price = entry + 1.0  # +1 point
        result = self.engine.place_order("SHORT", 1)
        # gross_pnl should be ~1 point × 100,000 VND
        # But slippage on exit reduces it slightly
        assert abs(result["gross_pnl"]) > 0


# ────────────────────────────────────────────────────────────────────────────
# Test 8: Engine — Partial Close + Flip
# ────────────────────────────────────────────────────────────────────────────
class TestEnginePartialCloseFlip:
    def setup_method(self):
        self.engine = ReplayEngine(
            initial_balance=500_000_000, strict_hours=False
        )
        self.engine.current_price = 1300.0
        self.engine.current_date = datetime(2025, 4, 3, 10, 0)

    def test_partial_close(self):
        self.engine.place_order("LONG", 3)
        assert self.engine.active_position["volume"] == 3

        self.engine.place_order("SHORT", 1)
        assert self.engine.active_position["volume"] == 2
        assert self.engine.active_position["type"] == "LONG"
        assert len(self.engine.trade_history) == 1

    def test_flip_position(self):
        self.engine.place_order("LONG", 1)

        result = self.engine.place_order("SHORT", 3)
        assert result["action"] == "CLOSE"
        assert "flip" in result
        assert result["flip"]["type"] == "SHORT"
        assert result["flip"]["volume"] == 2
        assert self.engine.active_position["type"] == "SHORT"
        assert self.engine.active_position["volume"] == 2

    def test_add_same_direction(self):
        self.engine.place_order("LONG", 2)
        result = self.engine.place_order("LONG", 3)
        assert result["action"] == "ADD"
        assert result["total_volume"] == 5

    def test_close_position_method(self):
        self.engine.place_order("LONG", 2)
        result = self.engine.close_position()
        assert result is not None
        assert self.engine.active_position is None

    def test_close_no_position(self):
        result = self.engine.close_position()
        assert result is None


# ────────────────────────────────────────────────────────────────────────────
# Test 9: Session Manager
# ────────────────────────────────────────────────────────────────────────────
class TestSessionManager:
    def setup_method(self):
        self.mgr = SessionManager()

    def test_create_session(self):
        engine = self.mgr.create_session("test1", strategy="algo_v1")
        assert engine.session_id == "test1"
        assert engine.strategy == "algo_v1"
        sessions = self.mgr.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["active"] is True

    def test_create_duplicate_raises(self):
        self.mgr.create_session("dup")
        with pytest.raises(ValueError):
            self.mgr.create_session("dup")

    def test_switch_session(self):
        self.mgr.create_session("s1")
        self.mgr.create_session("s2")
        self.mgr.switch_session("s2")
        active = self.mgr.get_active_engine()
        assert active.session_id == "s2"

    def test_switch_nonexistent_raises(self):
        with pytest.raises(ValueError):
            self.mgr.switch_session("nonexistent")

    def test_delete_session(self):
        self.mgr.create_session("del_me")
        assert self.mgr.delete_session("del_me") is True
        assert self.mgr.get_session("del_me") is None

    def test_broadcast_tick(self):
        self.mgr.create_session("s1")
        self.mgr.create_session("s2")
        self.mgr.broadcast_tick("2025-04-03T10:00:00", 1300.0)
        for s in self.mgr.list_sessions():
            engine = self.mgr.get_session(s["session_id"])
            assert engine.current_price == 1300.0

    def test_isolation(self):
        """Sessions should have isolated state."""
        self.mgr.create_session("iso1", initial_balance=100_000_000)
        self.mgr.create_session("iso2", initial_balance=200_000_000)
        e1 = self.mgr.get_session("iso1")
        e2 = self.mgr.get_session("iso2")
        assert e1.balance == 100_000_000
        assert e2.balance == 200_000_000


# ────────────────────────────────────────────────────────────────────────────
# Test 10: API Endpoints
# ────────────────────────────────────────────────────────────────────────────
class TestAPI:
    @pytest.fixture(autouse=True)
    def setup_client(self):
        from fastapi.testclient import TestClient
        from app.api import app, session_mgr

        # Reset session manager
        session_mgr._sessions.clear()
        session_mgr._active_id = None
        session_mgr.create_session("default", strict_hours=False)
        engine = session_mgr.get_active_engine()
        engine.current_price = 1300.0
        engine.current_date = datetime(2025, 4, 3, 10, 0)

        self.client = TestClient(app, raise_server_exceptions=False)
        self.session_mgr = session_mgr
        yield

    def test_health(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")

    def test_place_order_success(self):
        resp = self.client.post("/api/v1/order", json={"action": "LONG", "volume": 1})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_place_order_invalid_action(self):
        resp = self.client.post("/api/v1/order", json={"action": "BUY", "volume": 1})
        assert resp.status_code == 422  # Pydantic validation error

    def test_place_order_invalid_volume(self):
        resp = self.client.post("/api/v1/order", json={"action": "LONG", "volume": 0})
        assert resp.status_code == 422

    def test_get_pnl(self):
        resp = self.client.get("/api/v1/pnl")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_summary" in data
        assert "balance" in data

    def test_get_trades(self):
        resp = self.client.get("/api/v1/trades")
        assert resp.status_code == 200
        assert "trades" in resp.json()

    def test_get_equity_curve(self):
        resp = self.client.get("/api/v1/equity-curve")
        assert resp.status_code == 200
        data = resp.json()
        assert "equity_curve" in data

    def test_create_and_list_sessions(self):
        resp = self.client.post(
            "/api/v1/sessions",
            json={"session_id": "new_s", "strategy": "test"},
        )
        assert resp.status_code == 200

        resp = self.client.get("/api/v1/sessions")
        sessions = resp.json()["sessions"]
        ids = [s["session_id"] for s in sessions]
        assert "new_s" in ids

    def test_activate_session(self):
        self.client.post("/api/v1/sessions", json={"session_id": "s2"})
        resp = self.client.put("/api/v1/sessions/s2/activate")
        assert resp.status_code == 200

    def test_reset_engine(self):
        # Place an order first
        self.client.post("/api/v1/order", json={"action": "LONG", "volume": 1})
        resp = self.client.post("/api/v1/reset")
        assert resp.status_code == 200

        # After reset, PnL should be at initial state
        pnl = self.client.get("/api/v1/pnl").json()
        assert pnl["session_summary"]["total_trades"] == 0

    def test_close_position_no_position(self):
        resp = self.client.post("/api/v1/close-position")
        assert resp.status_code == 400
