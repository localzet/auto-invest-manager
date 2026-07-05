from enum import StrEnum


class TradeMode(StrEnum):
    OFF = "OFF"
    SIGNAL_ONLY = "SIGNAL_ONLY"
    DRY_RUN = "DRY_RUN"
    SANDBOX = "SANDBOX"
    REAL_MANUAL_CONFIRM = "REAL_MANUAL_CONFIRM"
    REAL_AUTO_SAFE = "REAL_AUTO_SAFE"


class RiskMode(StrEnum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    CUSTOM = "custom"


class RebalanceMode(StrEnum):
    ON_DEPOSIT = "on_deposit"
    DAILY = "daily"
    WEEKLY = "weekly"
    THRESHOLD = "threshold"
    MANUAL = "manual"


class OrderType(StrEnum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class SignalRecommendation(StrEnum):
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    WAIT = "WAIT"
