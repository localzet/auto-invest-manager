import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.db.session import session_factory
from app.models.entities import RiskProfile, StrategyProfile, SystemSettings
from app.models.enums import OrderType, RebalanceMode, RiskMode, TradeMode


async def seed_defaults() -> None:
    async with session_factory() as session, session.begin():
        if await session.scalar(select(SystemSettings).limit(1)) is None:
            session.add(SystemSettings(trade_mode=TradeMode.OFF, kill_switch=True))

        if await session.scalar(select(RiskProfile).where(RiskProfile.name == "default")) is None:
            session.add(
                RiskProfile(
                    name="default",
                    mode=RiskMode.CONSERVATIVE,
                    is_active=True,
                    max_position_weight=Decimal("0.15"),
                    max_sector_weight=Decimal("0.30"),
                    min_cash_weight=Decimal("0.10"),
                    max_daily_trades=5,
                    max_trade_amount=Decimal("50000"),
                    max_portfolio_drawdown=Decimal("0.15"),
                    max_daily_drawdown=Decimal("0.03"),
                    allow_short_selling=False,
                    allow_margin_trading=False,
                    allow_futures=False,
                    default_order_type=OrderType.LIMIT,
                    max_slippage_percent=Decimal("0.005"),
                    trade_cooldown_seconds=3600,
                    rebalance_threshold_percent=Decimal("0.03"),
                )
            )

        if (
            await session.scalar(select(StrategyProfile).where(StrategyProfile.name == "default"))
            is None
        ):
            session.add(
                StrategyProfile(
                    name="default",
                    enabled=False,
                    trade_mode=TradeMode.SIGNAL_ONLY,
                    auto_allocation_enabled=False,
                    rebalance_mode=RebalanceMode.MANUAL,
                    signal_threshold=Decimal("0.65"),
                    minimum_expected_return=Decimal("0.02"),
                    prefer_cash_when_no_signal=True,
                    use_protective_asset=False,
                    max_wait_days=7,
                    base_timeframe="1d",
                )
            )


def main() -> None:
    asyncio.run(seed_defaults())


if __name__ == "__main__":
    main()
