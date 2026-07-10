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


class RebalancePlanStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"


class AllocationAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderDirection(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class PlannedOrderStatus(StrEnum):
    PLANNED = "PLANNED"
    RISK_REJECTED = "RISK_REJECTED"
    SIMULATED = "SIMULATED"
    SUBMITTED = "SUBMITTED"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AutomationTrigger(StrEnum):
    MANUAL = "MANUAL"
    SCHEDULED = "SCHEDULED"
    ACCOUNT_CHANGE = "ACCOUNT_CHANGE"
    DEPOSIT_DETECTED = "DEPOSIT_DETECTED"
    RECOVERY = "RECOVERY"


class AutomationRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AutomationStep(StrEnum):
    SAFETY_CHECK = "SAFETY_CHECK"
    ACCOUNT_SYNC = "ACCOUNT_SYNC"
    PORTFOLIO_SYNC = "PORTFOLIO_SYNC"
    MARKET_DATA_SYNC = "MARKET_DATA_SYNC"
    SIGNAL_ANALYSIS = "SIGNAL_ANALYSIS"
    PORTFOLIO_OPTIMIZATION = "PORTFOLIO_OPTIMIZATION"
    REBALANCE_PLANNING = "REBALANCE_PLANNING"
    EXECUTION_PLANNING = "EXECUTION_PLANNING"
    MODE_EXECUTION = "MODE_EXECUTION"
    FINAL_RECONCILIATION = "FINAL_RECONCILIATION"
    COMPLETED = "COMPLETED"
