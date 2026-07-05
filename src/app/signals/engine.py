from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from statistics import fmean

from app.broker.dto import CandleData
from app.models.enums import SignalRecommendation
from app.signals.dto import SignalResult
from app.signals.errors import SignalCalculationError

SCORE_QUANTUM = Decimal("0.000001")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _score(value: float) -> Decimal:
    return Decimal(str(_clamp(value))).quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)


class BaselineSignalEngine:
    model_version = "baseline-v1"
    minimum_candles = 20

    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock

    def calculate(self, candles: Sequence[CandleData], threshold: float) -> SignalResult:
        if not 0.5 < threshold <= 1:
            raise SignalCalculationError("Signal threshold must be in (0.5, 1]")
        ordered = sorted((candle for candle in candles if candle.is_complete), key=lambda c: c.time)
        if len(ordered) < self.minimum_candles:
            raise SignalCalculationError(
                f"At least {self.minimum_candles} complete candles are required"
            )

        closes = [float(candle.close) for candle in ordered]
        volumes = [candle.volume for candle in ordered]
        if any(price <= 0 for price in closes):
            raise SignalCalculationError("Candle close prices must be positive")
        if any(volume < 0 for volume in volumes):
            raise SignalCalculationError("Candle volumes cannot be negative")

        returns = [
            current / previous - 1 for previous, current in zip(closes, closes[1:], strict=False)
        ]
        total_return = closes[-1] / closes[0] - 1
        trend = _clamp(0.5 + total_return / 0.20)

        short_average = fmean(closes[-5:])
        long_average = fmean(closes[-20:])
        moving_average = _clamp(0.5 + ((short_average / long_average) - 1) / 0.10)

        mean_absolute_return = fmean(abs(value) for value in returns)
        volatility = _clamp(1 - mean_absolute_return / 0.05)

        recent_volume = fmean(volumes[-5:])
        baseline_volume = fmean(volumes[-20:])
        volume = _clamp(0.5 + (recent_volume / baseline_volume - 1)) if baseline_volume else 0.5

        peak = max(closes)
        current_drawdown = (peak - closes[-1]) / peak
        drawdown = _clamp(1 - current_drawdown / 0.20)

        directional = trend * 0.40 + moving_average * 0.40 + volume * 0.20
        if directional >= 0.5:
            confidence = (volatility + drawdown) / 2
        else:
            confidence = (volatility + (1 - drawdown)) / 2
        final = _clamp(0.5 + (directional - 0.5) * confidence)
        recommendation = self._recommend(final, threshold)
        scores = {
            "trend": _score(trend),
            "moving_average": _score(moving_average),
            "volatility": _score(volatility),
            "volume": _score(volume),
            "drawdown": _score(drawdown),
        }
        return SignalResult(
            trend_score=scores["trend"],
            moving_average_score=scores["moving_average"],
            volatility_score=scores["volatility"],
            volume_score=scores["volume"],
            drawdown_score=scores["drawdown"],
            final_score=_score(final),
            recommendation=recommendation,
            price=ordered[-1].close,
            reason=self._reason(scores, recommendation),
            model_version=self.model_version,
            calculated_at=self._clock(),
        )

    @staticmethod
    def _recommend(score: float, threshold: float) -> SignalRecommendation:
        if score >= threshold:
            return SignalRecommendation.BUY
        if score <= 1 - threshold:
            return SignalRecommendation.SELL
        if 0.45 <= score <= 0.55:
            return SignalRecommendation.HOLD
        return SignalRecommendation.WAIT

    @staticmethod
    def _reason(scores: dict[str, Decimal], recommendation: SignalRecommendation) -> str:
        strongest = max(scores, key=scores.__getitem__)
        weakest = min(scores, key=scores.__getitem__)
        return (
            f"{recommendation.value}: strongest={strongest}({scores[strongest]}), "
            f"weakest={weakest}({scores[weakest]})"
        )
