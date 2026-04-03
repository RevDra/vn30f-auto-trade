"""Volume-dependent slippage model for VN30F."""

from app.constants import (
    TICK_SIZE,
    SLIPPAGE_BASE_TICKS,
    SLIPPAGE_VOLUME_STEP,
    SLIPPAGE_ROLLOVER_EXTRA_TICKS,
    SLIPPAGE_ATO_ATC_EXTRA_TICKS,
)


class SlippageModel:
    """Deterministic, volume-dependent slippage model.

    Formula:
      slippage_ticks = base(2) + volume_impact(vol // step)
                       + rollover_extra(2 if rollover day)
                       + session_extra(1 if ATO/ATC)
    """

    def __init__(
        self,
        base_ticks: int = SLIPPAGE_BASE_TICKS,
        volume_step: int = SLIPPAGE_VOLUME_STEP,
        rollover_extra: int = SLIPPAGE_ROLLOVER_EXTRA_TICKS,
        session_extra: int = SLIPPAGE_ATO_ATC_EXTRA_TICKS,
        tick_size: float = TICK_SIZE,
    ):
        self.base_ticks = base_ticks
        self.volume_step = volume_step
        self.rollover_extra = rollover_extra
        self.session_extra = session_extra
        self.tick_size = tick_size

    def calculate_slippage_ticks(
        self,
        volume: int,
        session_name: str = "CONT1",
        is_rollover: bool = False,
    ) -> int:
        """Calculate total slippage in ticks."""
        ticks = self.base_ticks
        ticks += volume // self.volume_step
        if is_rollover:
            ticks += self.rollover_extra
        if session_name in ("ATO", "ATC"):
            ticks += self.session_extra
        return ticks

    def calculate_slippage(
        self,
        action: str,
        price: float,
        volume: int,
        session_name: str = "CONT1",
        is_rollover: bool = False,
    ) -> float:
        """Calculate executed price after slippage.

        LONG: price + slippage (buy higher)
        SHORT: price - slippage (sell lower)
        """
        ticks = self.calculate_slippage_ticks(volume, session_name, is_rollover)
        slippage_amount = ticks * self.tick_size

        if action == "LONG":
            return round(price + slippage_amount, 2)
        elif action == "SHORT":
            return round(price - slippage_amount, 2)
        else:
            raise ValueError(f"Invalid action: {action}")
