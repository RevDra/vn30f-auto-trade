"""Multi-layer fee calculator for VN30F derivatives."""

from dataclasses import dataclass, field
from app.constants import (
    CONTRACT_MULTIPLIER,
    DEFAULT_BROKER_FEE,
    EXCHANGE_FEE_HNX,
    CLEARING_FEE_VSD,
    TNCN_TAX_RATE,
    INITIAL_MARGIN_RATE,
)


@dataclass
class FeeBreakdown:
    broker_fee: float = 0.0
    exchange_fee: float = 0.0
    clearing_fee: float = 0.0
    tax: float = 0.0

    @property
    def total(self) -> float:
        return self.broker_fee + self.exchange_fee + self.clearing_fee + self.tax


class FeeCalculator:
    """Calculates trading fees per VN30F contract.

    Fee layers (per side per contract):
      - Broker:   configurable, default 2,000 VND
      - Exchange:  2,700 VND (HNX)
      - Clearing:  2,550 VND (VSD)
      - TNCN tax:  0.1% × (price × multiplier × margin_rate)
    """

    def __init__(
        self,
        broker_fee: float = DEFAULT_BROKER_FEE,
        exchange_fee: float = EXCHANGE_FEE_HNX,
        clearing_fee: float = CLEARING_FEE_VSD,
        tax_rate: float = TNCN_TAX_RATE,
    ):
        self.broker_fee = broker_fee
        self.exchange_fee = exchange_fee
        self.clearing_fee = clearing_fee
        self.tax_rate = tax_rate

    def calculate_per_side(self, volume: int) -> float:
        """Fixed fees per side (broker + exchange + clearing) × volume."""
        per_contract = self.broker_fee + self.exchange_fee + self.clearing_fee
        return per_contract * volume

    def calculate_tax(self, price: float, volume: int) -> float:
        """TNCN tax = tax_rate × price × multiplier × volume × margin_rate / 2.

        The /2 accounts for the fact that tax is on the margin transfer value,
        which is halved per direction convention.
        """
        transfer_value = price * CONTRACT_MULTIPLIER * volume * INITIAL_MARGIN_RATE
        return self.tax_rate * transfer_value

    def calculate_one_side(self, price: float, volume: int) -> FeeBreakdown:
        """Full breakdown for one side of a trade."""
        return FeeBreakdown(
            broker_fee=self.broker_fee * volume,
            exchange_fee=self.exchange_fee * volume,
            clearing_fee=self.clearing_fee * volume,
            tax=self.calculate_tax(price, volume),
        )

    def total_round_trip(
        self, entry_price: float, exit_price: float, volume: int
    ) -> dict:
        """Full round-trip cost breakdown."""
        entry_fees = self.calculate_one_side(entry_price, volume)
        exit_fees = self.calculate_one_side(exit_price, volume)
        return {
            "entry_fees": entry_fees,
            "exit_fees": exit_fees,
            "total_fixed_fees": entry_fees.broker_fee
            + entry_fees.exchange_fee
            + entry_fees.clearing_fee
            + exit_fees.broker_fee
            + exit_fees.exchange_fee
            + exit_fees.clearing_fee,
            "total_tax": entry_fees.tax + exit_fees.tax,
            "grand_total": entry_fees.total + exit_fees.total,
        }
