export type TradeMode =
  | "OFF"
  | "SIGNAL_ONLY"
  | "DRY_RUN"
  | "SANDBOX"
  | "REAL_MANUAL_CONFIRM"
  | "REAL_AUTO_SAFE";

export interface SystemSettings {
  id: string;
  trade_mode: TradeMode;
  kill_switch: boolean;
  updated_at: string;
  real_trading_enabled_by_env: boolean;
}

export interface Instrument {
  id: string;
  instrument_uid: string;
  figi: string | null;
  ticker: string;
  class_code: string;
  name: string;
  instrument_type: string;
  currency: string;
  lot: number;
  is_active: boolean;
}

export interface WatchlistItem {
  id: string;
  buy_enabled: boolean;
  sell_enabled: boolean;
  max_weight: string | null;
  priority: number;
  min_signal_score: string;
  manual_target_weight: string | null;
  instrument: Instrument;
  updated_at: string;
}

export interface RiskProfile {
  id: string;
  name: string;
  mode: "conservative" | "balanced" | "aggressive" | "custom";
  is_active: boolean;
  max_position_weight: string;
  max_sector_weight: string | null;
  min_cash_weight: string;
  max_daily_trades: number;
  max_trade_amount: string;
  max_portfolio_drawdown: string;
  max_daily_drawdown: string;
  allow_short_selling: boolean;
  allow_margin_trading: boolean;
  allow_futures: boolean;
  default_order_type: "LIMIT" | "MARKET";
  max_slippage_percent: string;
  trade_cooldown_seconds: number;
  rebalance_threshold_percent: string;
  updated_at: string;
}

export interface StrategyProfile {
  id: string;
  name: string;
  enabled: boolean;
  trade_mode: TradeMode;
  auto_allocation_enabled: boolean;
  rebalance_mode: "on_deposit" | "daily" | "weekly" | "threshold" | "manual";
  signal_threshold: string;
  minimum_expected_return: string;
  prefer_cash_when_no_signal: boolean;
  use_protective_asset: boolean;
  max_wait_days: number;
  base_timeframe: "1h" | "1d";
  updated_at: string;
}

export interface Signal {
  id: string;
  instrument: Instrument;
  timeframe: string;
  final_score: string;
  recommendation: "BUY" | "HOLD" | "SELL" | "WAIT";
  price: string;
  reason: string;
  calculated_at: string;
}

export interface Allocation {
  id: string;
  instrument: Instrument;
  target_weight: string;
  current_weight: string;
  signal_score: string;
  target_amount: string;
  delta_amount: string;
  action: "BUY" | "SELL" | "HOLD";
  recommended_lots: number;
  reason: string;
}

export interface RebalancePlan {
  id: string;
  source_account_id: string;
  status: string;
  portfolio_value: string;
  cash_available: string;
  target_cash_weight: string;
  reason: string;
  created_at: string;
  allocations: Allocation[];
}

export interface PlannedOrder {
  id: string;
  instrument: Instrument;
  account_id: string;
  direction: "BUY" | "SELL";
  lots: number;
  order_type: "LIMIT" | "MARKET";
  limit_price: string;
  reason: string;
  status: string;
  trade_mode: TradeMode;
  idempotency_key: string;
  created_at: string;
}

export interface AuditLog {
  id: string;
  event_type: string;
  severity: string;
  actor: string;
  message: string;
  context: Record<string, unknown>;
  created_at: string;
}
