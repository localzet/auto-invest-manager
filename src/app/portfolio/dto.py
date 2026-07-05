from dataclasses import dataclass
from decimal import Decimal

from app.models.enums import AllocationAction


@dataclass(frozen=True, slots=True)
class AssetInput:
    instrument_uid: str
    signal_score: Decimal
    current_value: Decimal
    current_lots: int
    price: Decimal
    lot_size: int
    buy_enabled: bool = True
    sell_enabled: bool = True
    max_weight: Decimal | None = None
    manual_target_weight: Decimal | None = None
    priority: int = 0
    cooldown_active: bool = False


@dataclass(frozen=True, slots=True)
class OptimizationConstraints:
    max_position_weight: Decimal
    min_cash_weight: Decimal
    rebalance_threshold: Decimal


@dataclass(frozen=True, slots=True)
class TargetWeight:
    asset: AssetInput
    weight: Decimal


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    targets: tuple[TargetWeight, ...]
    cash_weight: Decimal


@dataclass(frozen=True, slots=True)
class PlannedAllocation:
    asset: AssetInput
    target_weight: Decimal
    current_weight: Decimal
    target_amount: Decimal
    delta_amount: Decimal
    action: AllocationAction
    lots: int
    reason: str


@dataclass(frozen=True, slots=True)
class RebalanceResult:
    allocations: tuple[PlannedAllocation, ...]
    target_cash_weight: Decimal
    unallocated_cash: Decimal
