from decimal import Decimal

from app.execution.dto import PlannedOrderData, RiskContext, RiskDecision
from app.models.enums import OrderDirection


class RiskManager:
    def evaluate(self, order: PlannedOrderData, context: RiskContext) -> RiskDecision:
        reasons: list[str] = []
        trade_amount = order.limit_price * order.lot_size * order.lots

        if context.kill_switch:
            reasons.append("global kill switch is active")
        if (
            context.trade_mode is not context.required_trade_mode
            or order.trade_mode is not context.required_trade_mode
        ):
            reasons.append(f"trade mode is not {context.required_trade_mode.value}")
        if not context.account_id or context.account_id != context.expected_account_id:
            reasons.append("account mismatch")
        if not context.in_watchlist:
            reasons.append("instrument is not in watchlist")
        if not context.direction_allowed:
            reasons.append("order direction is disabled")
        if not context.api_trade_available or not context.order_type_available:
            reasons.append("instrument trading status rejects order")
        if (context.now - context.price_time).total_seconds() > context.max_price_age_seconds:
            reasons.append("market price is stale")
        slippage = abs(order.limit_price / context.market_price - 1)
        tick_tolerance = Decimal("0.01") / context.market_price
        if slippage > context.max_slippage_percent + tick_tolerance:
            reasons.append("limit price exceeds slippage limit")
        if trade_amount > context.max_trade_amount:
            reasons.append("trade amount exceeds limit")
        if context.daily_trades >= context.max_daily_trades:
            reasons.append("daily trade limit reached")
        if context.cooldown_active:
            reasons.append("instrument cooldown is active")
        if context.idempotency_key_exists:
            reasons.append("idempotency key already exists")
        if context.duplicate_active_order:
            reasons.append("duplicate active order exists")
        if order.direction is OrderDirection.BUY:
            if trade_amount > context.cash_available:
                reasons.append("insufficient cash")
            projected_value = context.current_position_value + trade_amount
            if context.portfolio_value <= 0 or (
                projected_value / context.portfolio_value > context.max_position_weight
            ):
                reasons.append("projected position exceeds weight limit")
        elif order.lots > context.current_position_lots:
            reasons.append("sell would create a short position")

        return RiskDecision(not reasons, tuple(reasons))
