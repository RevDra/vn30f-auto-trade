"""Margin management and price limit validation for VN30F."""

from app.constants import (
    CONTRACT_MULTIPLIER,
    INITIAL_MARGIN_RATE,
    MAINTENANCE_MARGIN_RATE,
    PRICE_LIMIT_PERCENT,
    MAX_CONTRACTS_RETAIL,
)


class InsufficientMarginError(Exception):
    """Raised when account equity cannot cover required margin."""
    pass


class PriceLimitError(Exception):
    """Raised when order price exceeds ±7% circuit breaker."""
    pass


class PositionLimitError(Exception):
    """Raised when position exceeds max contracts allowed."""
    pass


class MarginManager:
    """Handles margin calculations, margin calls, and position/price limits."""

    def __init__(
        self,
        initial_margin_rate: float = INITIAL_MARGIN_RATE,
        maintenance_margin_rate: float = MAINTENANCE_MARGIN_RATE,
        price_limit_pct: float = PRICE_LIMIT_PERCENT,
        max_contracts: int = MAX_CONTRACTS_RETAIL,
    ):
        self.initial_margin_rate = initial_margin_rate
        self.maintenance_margin_rate = maintenance_margin_rate
        self.price_limit_pct = price_limit_pct
        self.max_contracts = max_contracts

    def required_margin(self, price: float, volume: int) -> float:
        """Initial margin required to open a position.

        = price × multiplier × volume × initial_margin_rate
        """
        return price * CONTRACT_MULTIPLIER * volume * self.initial_margin_rate

    def maintenance_margin(self, price: float, volume: int) -> float:
        """Maintenance margin level (triggers margin call if equity drops below)."""
        return price * CONTRACT_MULTIPLIER * volume * self.maintenance_margin_rate

    def check_margin_call(
        self, equity: float, price: float, volume: int
    ) -> str:
        """Check margin status.

        Returns:
            'ok' — equity above initial margin
            'margin_call' — equity between maintenance and initial
            'force_close' — equity below maintenance margin
        """
        if volume == 0:
            return "ok"
        initial = self.required_margin(price, volume)
        maintenance = self.maintenance_margin(price, volume)
        if equity >= initial:
            return "ok"
        elif equity >= maintenance:
            return "margin_call"
        else:
            return "force_close"

    def validate_price_limit(self, new_price: float, ref_price: float) -> bool:
        """Check if new_price is within ±7% of reference price."""
        if ref_price <= 0:
            return True
        lower = ref_price * (1 - self.price_limit_pct)
        upper = ref_price * (1 + self.price_limit_pct)
        return lower <= new_price <= upper

    def can_open_position(
        self,
        equity: float,
        price: float,
        new_volume: int,
        existing_volume: int = 0,
    ) -> bool:
        """Check if account can open additional contracts."""
        total_volume = existing_volume + new_volume
        if total_volume > self.max_contracts:
            return False
        required = self.required_margin(price, total_volume)
        return equity >= required

    def validate_order(
        self,
        equity: float,
        price: float,
        volume: int,
        existing_volume: int = 0,
        ref_price: float = 0.0,
    ) -> None:
        """Full pre-trade validation. Raises on failure."""
        total = existing_volume + volume
        if total > self.max_contracts:
            raise PositionLimitError(
                f"Total volume {total} exceeds max {self.max_contracts}"
            )
        if ref_price > 0 and not self.validate_price_limit(price, ref_price):
            raise PriceLimitError(
                f"Price {price} outside ±{self.price_limit_pct*100}% of ref {ref_price}"
            )
        required = self.required_margin(price, total)
        if equity < required:
            raise InsufficientMarginError(
                f"Equity {equity:,.0f} < required margin {required:,.0f}"
            )
