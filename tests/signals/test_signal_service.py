from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.broker.mock import MockBrokerProvider
from app.signals.service import SignalAnalysisService


async def test_analysis_persists_signal_and_audit_atomically() -> None:
    instrument = SimpleNamespace(
        id="instrument-id",
        instrument_uid="mock-sber-uid",
        ticker="SBER",
    )
    item = SimpleNamespace(
        instrument_id="instrument-id",
        instrument=instrument,
        min_signal_score=Decimal("0.60"),
    )
    saved = SimpleNamespace(model_version="baseline-v1")
    notifier = SimpleNamespace(send=AsyncMock())
    repository = SimpleNamespace(
        get_strategy=AsyncMock(
            return_value=SimpleNamespace(
                base_timeframe="1d",
                signal_threshold=Decimal("0.65"),
            )
        ),
        get_watchlist=AsyncMock(return_value=[item]),
        save=AsyncMock(return_value=saved),
        add_audit=Mock(),
        commit=AsyncMock(),
    )
    service = SignalAnalysisService(
        repository,
        MockBrokerProvider(),
        notifier=notifier,
        clock=lambda: datetime(2026, 1, 5, 12, tzinfo=UTC),
    )

    result = await service.run()

    assert result == [saved]
    repository.save.assert_awaited_once()
    repository.add_audit.assert_called_once_with(1, "baseline-v1")
    repository.commit.assert_awaited_once()
    notifier.send.assert_awaited_once()
    assert notifier.send.await_args.args[0].title == "Анализ рынка завершён"
