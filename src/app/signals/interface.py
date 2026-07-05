from collections.abc import Sequence
from typing import Protocol

from app.broker.dto import CandleData
from app.signals.dto import SignalResult


class SignalEngine(Protocol):
    def calculate(self, candles: Sequence[CandleData], threshold: float) -> SignalResult: ...


class PredictionProvider(Protocol):
    def predict(self, candles: Sequence[CandleData]) -> float: ...
