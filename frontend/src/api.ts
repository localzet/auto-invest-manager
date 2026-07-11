import type {
  AuditLog,
  AutomationRun,
  AutomationStatus,
  AccountEventRecord,
  BrokerStreamEventRecord,
  PlannedOrder,
  RebalancePlan,
  ReconciliationRecord,
  RiskProfile,
  Signal,
  StrategyProfile,
  StreamsStatus,
  SystemSettings,
  WatchlistItem,
} from "./types";

const API_PREFIX = "/api/v1/admin";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export class AdminApi {
  constructor(private readonly apiKey: string) {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_PREFIX}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-Admin-API-Key": this.apiKey,
        ...init?.headers,
      },
    });
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as {
        detail?: string;
        reasons?: string[];
      } | null;
      const detail = payload?.reasons?.join("; ") ?? payload?.detail ?? response.statusText;
      throw new ApiError(detail, response.status);
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return response.json() as Promise<T>;
  }

  settings = () => this.request<SystemSettings>("/settings");
  updateSettings = (payload: Partial<SystemSettings>) =>
    this.request<SystemSettings>("/settings", { method: "PATCH", body: JSON.stringify(payload) });
  watchlist = () => this.request<WatchlistItem[]>("/watchlist");
  addWatchlist = (payload: object) =>
    this.request<WatchlistItem>("/watchlist", { method: "POST", body: JSON.stringify(payload) });
  updateWatchlist = (id: string, payload: object) =>
    this.request<WatchlistItem>(`/watchlist/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  removeWatchlist = (id: string) =>
    this.request<void>(`/watchlist/${id}`, { method: "DELETE" });
  risk = () => this.request<RiskProfile>("/risk-profile");
  updateRisk = (payload: Partial<RiskProfile>) =>
    this.request<RiskProfile>("/risk-profile", { method: "PATCH", body: JSON.stringify(payload) });
  strategy = () => this.request<StrategyProfile>("/strategy-profile");
  updateStrategy = (payload: Partial<StrategyProfile>) =>
    this.request<StrategyProfile>("/strategy-profile", {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  signals = () => this.request<Signal[]>("/signals");
  runAnalysis = () => this.request<{ signals: Signal[] }>("/analysis/run", { method: "POST" });
  plans = () => this.request<RebalancePlan[]>("/rebalance-plans");
  runPlanning = () => this.request<RebalancePlan>("/rebalance-plans/run", { method: "POST" });
  createOrders = (planId: string) =>
    this.request<PlannedOrder[]>(`/rebalance-plans/${planId}/execution-plan`, { method: "POST" });
  orders = () => this.request<PlannedOrder[]>("/planned-orders");
  approveOrder = (id: string) =>
    this.request<PlannedOrder>(`/planned-orders/${id}/approve`, { method: "POST" });
  rejectOrder = (id: string) =>
    this.request<PlannedOrder>(`/planned-orders/${id}/reject`, { method: "POST" });
  auditLogs = () => this.request<AuditLog[]>("/audit-logs");
  automationRuns = () => this.request<AutomationRun[]>("/automation/runs");
  automationStatus = () => this.request<AutomationStatus>("/automation/status");
  runAutomation = (idempotencyKey: string) =>
    this.request<AutomationRun>("/automation/run", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
    });
  streamsStatus = () => this.request<StreamsStatus>("/streams/status");
  streamEvents = () => this.request<BrokerStreamEventRecord[]>("/streams/events");
  accountEvents = () => this.request<AccountEventRecord[]>("/account-events");
  reconciliations = () => this.request<ReconciliationRecord[]>("/reconciliations");
  retryStreamEvent = (id: string) =>
    this.request<BrokerStreamEventRecord>(`/streams/events/${id}/retry`, { method: "POST" });
  reconcileAccount = (accountId: string) =>
    this.request<{ status: string }>(`/accounts/${encodeURIComponent(accountId)}/reconcile`, {
      method: "POST",
    });
}
