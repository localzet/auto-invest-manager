from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.models.enums import SignalRecommendation


@dataclass(frozen=True, slots=True)
class SignalResult:
    trend_score: Decimal
    moving_average_score: Decimal
    volatility_score: Decimal
    volume_score: Decimal
    drawdown_score: Decimal
    final_score: Decimal
    recommendation: SignalRecommendation
    price: Decimal
    reason: str
    model_version: str
    calculated_at: datetime
