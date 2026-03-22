import pytest
from datetime import datetime
from main import ReplayEngine

def test_execute_order_slippage():
    engine = ReplayEngine()
    current_price = 1000.0

    # LONG order should have a higher execution price (slippage of 0.2 - 0.3)
    long_exec = engine.execute_order("LONG", 1, current_price)
    assert 1000.2 <= long_exec <= 1000.3

    # SHORT order should have a lower execution price
    short_exec = engine.execute_order("SHORT", 1, current_price)
    assert 999.7 <= short_exec <= 999.8

def test_execute_order_invalid_action():
    engine = ReplayEngine()
    with pytest.raises(ValueError):
        engine.execute_order("INVALID", 1, 1000.0)

def test_rollover_friday_check():
    engine = ReplayEngine()

    # Friday, 3rd week (after 3rd Thursday)
    assert engine.is_rollover_friday(datetime(2024, 3, 22)) == True
    assert engine.is_rollover_friday(datetime(2024, 3, 15)) == False # Friday, 2nd week
    assert engine.is_rollover_friday(datetime(2024, 3, 21)) == False # Thursday

def test_inject_rollover_gap():
    engine = ReplayEngine()
    price = 1000.0

    # Not rollover Friday
    assert engine.inject_rollover_gap(datetime(2024, 3, 15), price) == price

    # Rollover Friday
    rollover_date = datetime(2024, 3, 22)
    new_price = engine.inject_rollover_gap(rollover_date, price)
    diff = abs(new_price - price)
    assert 10.0 <= diff <= 15.0

    # Check consistency on the same day
    new_price_2 = engine.inject_rollover_gap(rollover_date, price)
    assert new_price == new_price_2

    # Check reset on next day
    next_day = datetime(2024, 3, 23)
    assert engine.inject_rollover_gap(next_day, price) == price
    assert engine.current_rollover_date is None
    assert engine.current_rollover_gap == 0.0

def test_place_order_partial_close():
    engine = ReplayEngine()
    engine.current_price = 1000.0

    # Open 3 LONG contracts
    engine.place_order("LONG", 3)
    assert engine.active_position["volume"] == 3

    # Close 1 LONG contract (by SHORTing 1)
    engine.place_order("SHORT", 1)
    assert engine.active_position["volume"] == 2
    assert engine.active_position["type"] == "LONG"

def test_place_order_flip():
    engine = ReplayEngine()
    engine.current_price = 1000.0

    # Open 1 LONG contract
    engine.place_order("LONG", 1)
    assert engine.active_position["volume"] == 1

    # SHORT 3 contracts -> Closes 1 LONG, Opens 2 SHORT
    engine.place_order("SHORT", 3)
    assert engine.active_position["volume"] == 2
    assert engine.active_position["type"] == "SHORT"

def test_place_order_and_pnl():
    engine = ReplayEngine()
    engine.current_price = 1000.0

    # Open LONG 1 contract
    engine.place_order("LONG", 1)
    assert engine.active_position is not None
    assert engine.active_position["type"] == "LONG"
    assert engine.active_position["volume"] == 1
    # Entry price will be > 1000.0 due to slippage
    entry_price = engine.active_position["entry_price"]
    assert entry_price > 1000.0

    # Market moves up
    engine.current_price = 1010.0
    unrealized = engine.get_unrealized_pnl()
    assert unrealized == (1010.0 - entry_price) * 1

    # Close LONG position by selling SHORT
    engine.place_order("SHORT", 1)
    assert engine.active_position is None # Position closed
    assert engine.total_pnl > 0 # Should have made profit
    assert len(engine.trade_history) == 1
