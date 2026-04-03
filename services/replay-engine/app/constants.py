"""VN30F Exchange Constants — verified from VSD/HNX/SSI/VPS (2025-2026)."""

# Contract specifications
CONTRACT_MULTIPLIER = 100_000  # VND per index point
TICK_SIZE = 0.1  # index points
TICK_VALUE = TICK_SIZE * CONTRACT_MULTIPLIER  # = 10,000 VND

# Margin rates (VSD 20/03/2026)
INITIAL_MARGIN_RATE = 0.17  # 17%
MAINTENANCE_MARGIN_RATE = 0.136  # 80% of initial ≈ 13.6%

# Price limits (HNX)
PRICE_LIMIT_PERCENT = 0.07  # ±7% from reference price

# Position limits
MAX_CONTRACTS_RETAIL = 500

# Default fees per side per contract (VND)
DEFAULT_BROKER_FEE = 2_000  # VPS default tier
EXCHANGE_FEE_HNX = 2_700
CLEARING_FEE_VSD = 2_550
TNCN_TAX_RATE = 0.001  # 0.1% on transfer value

# Trading sessions (Vietnam timezone UTC+7)
TRADING_SESSIONS = {
    "ATO":   {"start": (8, 45), "end": (9, 0)},
    "CONT1": {"start": (9, 0),  "end": (11, 30)},
    "CONT2": {"start": (13, 0), "end": (14, 30)},
    "ATC":   {"start": (14, 30), "end": (14, 45)},
}

# Slippage model defaults
SLIPPAGE_BASE_TICKS = 2
SLIPPAGE_VOLUME_STEP = 5  # +1 tick per this many contracts
SLIPPAGE_ROLLOVER_EXTRA_TICKS = 2
SLIPPAGE_ATO_ATC_EXTRA_TICKS = 1

# Default initial balance
DEFAULT_INITIAL_BALANCE = 500_000_000  # 500M VND
