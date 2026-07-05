from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

from app.admin.errors import ResourceNotFoundError
from app.broker.dto import CandleInterval
from app.broker.interface import BrokerProvider
from app.models.entities import Signal
from app.signals.engine import BaselineSignalEngine
from app.signals.errors import SignalCalculationError
from app.signals.interface import SignalEngine
from app.signals.repository import SignalRepository


class SignalAnalysisService:
    def __init__(
        self,
        repository: SignalRepository,
        broker: BrokerProvider,
        engine: SignalEngine | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._broker = broker
        self._engine = engine or BaselineSignalEngine(clock=clock)
        self._clock = clock

    async def run(self) -> Sequence[Signal]:
        strategy = await self._repository.get_strategy()
        if strategy is None:
            raise ResourceNotFoundError("Default strategy profile is not seeded")
        watchlist = await self._repository.get_watchlist()
        if not watchlist:
            return ()

        interval = CandleInterval(strategy.base_timeframe)
        to = self._clock()
        lookback = timedelta(days=60) if interval is CandleInterval.DAY else timedelta(days=7)
        signals: list[Signal] = []
        for item in watchlist:
            candles = await self._broker.get_candles(
                item.instrument.instrument_uid,
                to - lookback,
                to,
                interval,
            )
            complete_times = [candle.time for candle in candles if candle.is_complete]
            freshness_limit = (
                timedelta(days=2) if interval is CandleInterval.DAY else timedelta(hours=2)
            )
            if not complete_times or to - max(complete_times) > freshness_limit:
                raise SignalCalculationError(f"Market data for {item.instrument.ticker} is stale")
            threshold = float(max(strategy.signal_threshold, item.min_signal_score))
            result = self._engine.calculate(candles, threshold)
            signals.append(await self._repository.save(item, result, interval.value))

        self._repository.add_audit(len(signals), signals[0].model_version)
        await self._repository.commit()
        return signals

    async def latest(self, limit: int = 100) -> Sequence[Signal]:
        return await self._repository.latest(limit)
