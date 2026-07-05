from collections.abc import Sequence
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from hashlib import sha256
from uuid import UUID

from app.execution.dto import ExecutionAllocation, PlannedOrderData
from app.execution.errors import ExecutionPlanningError
from app.models.enums import OrderDirection, OrderType, TradeMode


class ExecutionPlanner:
    def plan(
        self,
        plan_id: UUID,
        allocations: Sequence[ExecutionAllocation],
        order_type: OrderType,
        max_slippage_percent: Decimal,
        trade_mode: TradeMode,
    ) -> tuple[PlannedOrderData, ...]:
        if order_type is not OrderType.LIMIT:
            raise ExecutionPlanningError("Market orders are disabled")
        if not 0 <= max_slippage_percent <= 1:
            raise ExecutionPlanningError("max_slippage_percent must be in [0, 1]")

        orders = []
        for allocation in allocations:
            if allocation.lots <= 0 or allocation.lot_size <= 0 or allocation.market_price <= 0:
                raise ExecutionPlanningError("Lots, lot size and market price must be positive")
            multiplier = (
                Decimal(1) + max_slippage_percent
                if allocation.direction is OrderDirection.BUY
                else Decimal(1) - max_slippage_percent
            )
            rounding = ROUND_CEILING if allocation.direction is OrderDirection.BUY else ROUND_FLOOR
            limit_price = (allocation.market_price * multiplier).quantize(
                Decimal("0.01"), rounding=rounding
            )
            raw_key = f"{plan_id}:{allocation.instrument_uid}:{allocation.direction.value}"
            orders.append(
                PlannedOrderData(
                    instrument_uid=allocation.instrument_uid,
                    ticker=allocation.ticker,
                    direction=allocation.direction,
                    lots=allocation.lots,
                    lot_size=allocation.lot_size,
                    order_type=order_type,
                    limit_price=limit_price,
                    reason=allocation.reason,
                    trade_mode=trade_mode,
                    idempotency_key=sha256(raw_key.encode()).hexdigest(),
                )
            )
        return tuple(orders)
