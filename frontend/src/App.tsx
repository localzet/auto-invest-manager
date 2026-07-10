import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { AdminApi } from "./api";
import type {
  AuditLog,
  PlannedOrder,
  RebalancePlan,
  RiskProfile,
  Signal,
  StrategyProfile,
  SystemSettings,
  TradeMode,
  WatchlistItem,
} from "./types";

type Page = "dashboard" | "watchlist" | "risk" | "strategy" | "rebalance" | "audit" | "safety";

const NAVIGATION: Array<{ id: Page; label: string; icon: string }> = [
  { id: "dashboard", label: "Обзор", icon: "◫" },
  { id: "watchlist", label: "Watchlist", icon: "◎" },
  { id: "risk", label: "Риск-профиль", icon: "◇" },
  { id: "strategy", label: "Стратегия", icon: "⌁" },
  { id: "rebalance", label: "Ребалансировка", icon: "⇄" },
  { id: "audit", label: "Журнал", icon: "≡" },
  { id: "safety", label: "Безопасность", icon: "⊘" },
];

const TRADE_MODES: TradeMode[] = [
  "OFF",
  "SIGNAL_ONLY",
  "DRY_RUN",
  "SANDBOX",
  "REAL_MANUAL_CONFIRM",
  "REAL_AUTO_SAFE",
];

function formatMoney(value: string | number, currency = "RUB") {
  return new Intl.NumberFormat("ru-RU", { style: "currency", currency, maximumFractionDigits: 2 }).format(
    Number(value),
  );
}

function formatPercent(value: string | number) {
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "short" }).format(
    new Date(value),
  );
}

function Status({ value }: { value: string }) {
  const tone = ["BUY", "APPROVED", "SIMULATED", "SUBMITTED"].includes(value)
    ? "positive"
    : ["SELL", "REJECTED", "RISK_REJECTED", "OFF"].includes(value)
      ? "negative"
      : "neutral";
  return <span className={`status status--${tone}`}>{value.replaceAll("_", " ")}</span>;
}

function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

function Notice({ error, success }: { error?: string; success?: string }) {
  if (!error && !success) return null;
  return <div className={`notice ${error ? "notice--error" : "notice--success"}`}>{error ?? success}</div>;
}

function Login({ onConnect }: { onConnect: (key: string) => void }) {
  const [key, setKey] = useState("");
  return (
    <main className="login-shell">
      <section className="login-card">
        <div className="brand-mark">AI</div>
        <p className="eyebrow">CONTROL PLANE</p>
        <h1>Auto Invest Manager</h1>
        <p className="muted">Введите административный ключ. Он хранится только в текущем браузере.</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (key.trim()) onConnect(key.trim());
          }}
        >
          <label>
            Admin API key
            <input
              type="password"
              value={key}
              onChange={(event) => setKey(event.target.value)}
              minLength={32}
              autoFocus
              autoComplete="current-password"
              placeholder="Не менее 32 символов"
            />
          </label>
          <button className="button button--primary" type="submit" disabled={key.trim().length < 32}>
            Подключиться
          </button>
        </form>
      </section>
    </main>
  );
}

function Dashboard({ api }: { api: AdminApi }) {
  const [settings, setSettings] = useState<SystemSettings>();
  const [signals, setSignals] = useState<Signal[]>([]);
  const [plans, setPlans] = useState<RebalancePlan[]>([]);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    try {
      const [nextSettings, nextSignals, nextPlans] = await Promise.all([
        api.settings(),
        api.signals(),
        api.plans(),
      ]);
      setSettings(nextSettings);
      setSignals(nextSignals);
      setPlans(nextPlans);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить данные");
    }
  }, [api]);

  useEffect(() => void load(), [load]);
  const latestPlan = plans[0];

  return (
    <PageLayout title="Обзор системы" subtitle="Состояние портфеля, сигналы и последние решения">
      <Notice error={error} />
      <div className="metrics">
        <Metric label="Режим торговли" value={settings?.trade_mode ?? "—"} detail={settings?.kill_switch ? "Kill switch включён" : "Исполнение разрешено профилем"} />
        <Metric label="Стоимость портфеля" value={latestPlan ? formatMoney(latestPlan.portfolio_value) : "—"} detail="По последнему плану" />
        <Metric label="Доступный кэш" value={latestPlan ? formatMoney(latestPlan.cash_available) : "—"} detail={latestPlan ? `${formatPercent(latestPlan.target_cash_weight)} целевой резерв` : "Нет планов"} />
        <Metric label="Сигналы" value={String(signals.length)} detail={`${signals.filter((item) => item.recommendation === "BUY").length} к покупке`} />
      </div>
      <div className="split-grid">
        <section className="panel">
          <div className="panel-heading">
            <div><p className="eyebrow">SIGNAL ENGINE</p><h2>Последние сигналы</h2></div>
            <button
              className="button"
              disabled={running}
              onClick={async () => {
                setRunning(true);
                try {
                  const result = await api.runAnalysis();
                  setSignals(result.signals);
                  setError("");
                } catch (caught) {
                  setError(caught instanceof Error ? caught.message : "Ошибка анализа");
                } finally {
                  setRunning(false);
                }
              }}
            >
              {running ? "Расчёт…" : "Запустить анализ"}
            </button>
          </div>
          {signals.length ? (
            <div className="table-wrap"><table><thead><tr><th>Инструмент</th><th>Решение</th><th>Оценка</th><th>Цена</th></tr></thead><tbody>
              {signals.slice(0, 8).map((signal) => <tr key={signal.id}><td><strong>{signal.instrument.ticker}</strong><small>{signal.instrument.name}</small></td><td><Status value={signal.recommendation} /></td><td>{formatPercent(signal.final_score)}</td><td>{formatMoney(signal.price, signal.instrument.currency.toUpperCase())}</td></tr>)}
            </tbody></table></div>
          ) : <Empty>Сигналов пока нет. Добавьте инструменты и запустите анализ.</Empty>}
        </section>
        <section className="panel">
          <div className="panel-heading"><div><p className="eyebrow">DECISIONS</p><h2>Последние планы</h2></div></div>
          {plans.length ? <div className="decision-list">{plans.slice(0, 5).map((plan) => (
            <article key={plan.id} className="decision"><div><Status value={plan.status} /><h3>{plan.allocations.length} распределений</h3><p>{plan.reason}</p></div><time>{formatDate(plan.created_at)}</time></article>
          ))}</div> : <Empty>Планы ребалансировки ещё не создавались.</Empty>}
        </section>
      </div>
    </PageLayout>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <article className="metric"><p>{label}</p><strong>{value}</strong><small>{detail}</small></article>;
}

function Watchlist({ api }: { api: AdminApi }) {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [ticker, setTicker] = useState("");
  const [classCode, setClassCode] = useState("TQBR");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.watchlist().then(setItems).catch((e: Error) => setError(e.message)), [api]);
  useEffect(() => void load(), [load]);

  async function add(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api.addWatchlist({ ticker: ticker.toUpperCase(), class_code: classCode.toUpperCase() });
      setTicker("");
      await load();
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Ошибка добавления");
    } finally {
      setBusy(false);
    }
  }

  async function patch(item: WatchlistItem, payload: object) {
    try {
      const updated = await api.updateWatchlist(item.id, payload);
      setItems((current) => current.map((value) => value.id === item.id ? updated : value));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Ошибка обновления");
    }
  }

  return <PageLayout title="Watchlist" subtitle="Инструменты, допуски и индивидуальные лимиты">
    <Notice error={error} />
    <section className="panel compact-panel"><form className="inline-form" onSubmit={add}>
      <label>Тикер<input value={ticker} onChange={(e) => setTicker(e.target.value)} placeholder="SBER" required /></label>
      <label>Режим торгов<input value={classCode} onChange={(e) => setClassCode(e.target.value)} placeholder="TQBR" required /></label>
      <button className="button button--primary" disabled={busy}>{busy ? "Добавление…" : "Добавить"}</button>
    </form></section>
    <section className="panel">
      {items.length ? <div className="table-wrap"><table><thead><tr><th>Инструмент</th><th>Покупка</th><th>Продажа</th><th>Мин. сигнал</th><th>Макс. вес</th><th></th></tr></thead><tbody>
        {items.map((item) => <tr key={item.id}><td><strong>{item.instrument.ticker}</strong><small>{item.instrument.name} · лот {item.instrument.lot}</small></td>
          <td><Toggle checked={item.buy_enabled} onChange={(checked) => void patch(item, { buy_enabled: checked })} /></td>
          <td><Toggle checked={item.sell_enabled} onChange={(checked) => void patch(item, { sell_enabled: checked })} /></td>
          <td>{formatPercent(item.min_signal_score)}</td><td>{item.max_weight ? formatPercent(item.max_weight) : "Профиль"}</td>
          <td><button className="button button--danger button--small" onClick={async () => { if (!confirm(`Удалить ${item.instrument.ticker}?`)) return; await api.removeWatchlist(item.id); await load(); }}>Удалить</button></td></tr>)}
      </tbody></table></div> : <Empty>Watchlist пуст. Добавьте первый тикер.</Empty>}
    </section>
  </PageLayout>;
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return <button type="button" className={`toggle ${checked ? "toggle--on" : ""}`} aria-pressed={checked} onClick={() => onChange(!checked)}><span /></button>;
}

function ProfilePage({ api, kind }: { api: AdminApi; kind: "risk" | "strategy" }) {
  const [profile, setProfile] = useState<RiskProfile | StrategyProfile>();
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [saving, setSaving] = useState(false);
  const load = useCallback(async () => {
    try { setProfile(kind === "risk" ? await api.risk() : await api.strategy()); setError(""); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Ошибка загрузки"); }
  }, [api, kind]);
  useEffect(() => void load(), [load]);

  if (!profile) return <PageLayout title={kind === "risk" ? "Риск-профиль" : "Стратегия"} subtitle="Загрузка…"><Notice error={error} /></PageLayout>;
  const isRisk = kind === "risk";
  const risk = profile as RiskProfile;
  const strategy = profile as StrategyProfile;
  const setField = (field: string, value: string | number | boolean) => setProfile({ ...profile, [field]: value });

  async function save(event: FormEvent) {
    event.preventDefault(); setSaving(true);
    try {
      const updated = isRisk ? await api.updateRisk(profile as RiskProfile) : await api.updateStrategy(profile as StrategyProfile);
      setProfile(updated); setSuccess("Настройки сохранены"); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Ошибка сохранения"); setSuccess(""); }
    finally { setSaving(false); }
  }

  return <PageLayout title={isRisk ? "Риск-профиль" : "Стратегия"} subtitle={isRisk ? "Ограничения исполнения и сохранения капитала" : "Правила сигналов и автораспределения"}>
    <Notice error={error} success={success} />
    <form className="panel form-grid" onSubmit={save}>
      {isRisk ? <>
        <SelectField label="Режим риска" value={risk.mode} options={["conservative", "balanced", "aggressive", "custom"]} onChange={(v) => setField("mode", v)} />
        <NumberField label="Максимальный вес позиции" value={risk.max_position_weight} step="0.01" onChange={(v) => setField("max_position_weight", v)} />
        <NumberField label="Минимальный вес кэша" value={risk.min_cash_weight} step="0.01" onChange={(v) => setField("min_cash_weight", v)} />
        <NumberField label="Максимум сделок в день" value={risk.max_daily_trades} step="1" onChange={(v) => setField("max_daily_trades", Number(v))} />
        <NumberField label="Максимальная сумма сделки" value={risk.max_trade_amount} step="100" onChange={(v) => setField("max_trade_amount", v)} />
        <NumberField label="Максимальное проскальзывание" value={risk.max_slippage_percent} step="0.001" onChange={(v) => setField("max_slippage_percent", v)} />
        <NumberField label="Cooldown, секунд" value={risk.trade_cooldown_seconds} step="1" onChange={(v) => setField("trade_cooldown_seconds", Number(v))} />
        <NumberField label="Порог ребалансировки" value={risk.rebalance_threshold_percent} step="0.01" onChange={(v) => setField("rebalance_threshold_percent", v)} />
        <BooleanField label="Разрешить шорты" checked={risk.allow_short_selling} onChange={(v) => setField("allow_short_selling", v)} dangerous />
        <BooleanField label="Разрешить маржинальную торговлю" checked={risk.allow_margin_trading} onChange={(v) => setField("allow_margin_trading", v)} dangerous />
        <BooleanField label="Разрешить фьючерсы" checked={risk.allow_futures} onChange={(v) => setField("allow_futures", v)} dangerous />
      </> : <>
        <BooleanField label="Стратегия включена" checked={strategy.enabled} onChange={(v) => setField("enabled", v)} />
        <SelectField label="Торговый режим" value={strategy.trade_mode} options={TRADE_MODES} onChange={(v) => setField("trade_mode", v)} />
        <BooleanField label="Автораспределение" checked={strategy.auto_allocation_enabled} onChange={(v) => setField("auto_allocation_enabled", v)} />
        <SelectField label="Режим ребалансировки" value={strategy.rebalance_mode} options={["on_deposit", "daily", "weekly", "threshold", "manual"]} onChange={(v) => setField("rebalance_mode", v)} />
        <NumberField label="Порог сигнала" value={strategy.signal_threshold} step="0.01" onChange={(v) => setField("signal_threshold", v)} />
        <NumberField label="Минимальная ожидаемая доходность" value={strategy.minimum_expected_return} step="0.01" onChange={(v) => setField("minimum_expected_return", v)} />
        <SelectField label="Таймфрейм" value={strategy.base_timeframe} options={["1h", "1d"]} onChange={(v) => setField("base_timeframe", v)} />
        <NumberField label="Максимум дней ожидания" value={strategy.max_wait_days} step="1" onChange={(v) => setField("max_wait_days", Number(v))} />
        <BooleanField label="Предпочитать кэш без сигнала" checked={strategy.prefer_cash_when_no_signal} onChange={(v) => setField("prefer_cash_when_no_signal", v)} />
      </>}
      <div className="form-actions"><button className="button button--primary" disabled={saving}>{saving ? "Сохранение…" : "Сохранить профиль"}</button></div>
    </form>
  </PageLayout>;
}

function NumberField({ label, value, step, onChange }: { label: string; value: string | number; step: string; onChange: (value: string) => void }) {
  return <label>{label}<input type="number" min="0" step={step} value={value} onChange={(e) => onChange(e.target.value)} required /></label>;
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: readonly string[]; onChange: (value: string) => void }) {
  return <label>{label}<select value={value} onChange={(e) => onChange(e.target.value)}>{options.map((option) => <option key={option}>{option}</option>)}</select></label>;
}

function BooleanField({ label, checked, onChange, dangerous = false }: { label: string; checked: boolean; onChange: (value: boolean) => void; dangerous?: boolean }) {
  return <div className={`boolean-field ${dangerous ? "boolean-field--danger" : ""}`}><span>{label}</span><Toggle checked={checked} onChange={onChange} /></div>;
}

function Rebalance({ api }: { api: AdminApi }) {
  const [plans, setPlans] = useState<RebalancePlan[]>([]);
  const [orders, setOrders] = useState<PlannedOrder[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const load = useCallback(async () => {
    try { const [nextPlans, nextOrders] = await Promise.all([api.plans(), api.orders()]); setPlans(nextPlans); setOrders(nextOrders); setError(""); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Ошибка загрузки"); }
  }, [api]);
  useEffect(() => void load(), [load]);

  async function action(name: string, callback: () => Promise<unknown>) {
    setBusy(name);
    try { await callback(); await load(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Операция не выполнена"); }
    finally { setBusy(""); }
  }

  return <PageLayout title="Ребалансировка" subtitle="Планы, заявки и ручное подтверждение">
    <Notice error={error} />
    <div className="toolbar"><button className="button button--primary" disabled={!!busy} onClick={() => void action("plan", api.runPlanning)}>{busy === "plan" ? "Расчёт…" : "Создать план"}</button><button className="button" onClick={() => void load()}>Обновить</button></div>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">ALLOCATION</p><h2>Планы</h2></div></div>
      {plans.length ? <div className="cards">{plans.map((plan) => <article className="plan-card" key={plan.id}><div className="plan-card__top"><Status value={plan.status} /><time>{formatDate(plan.created_at)}</time></div><h3>{formatMoney(plan.portfolio_value)}</h3><p>Кэш {formatMoney(plan.cash_available)} · {plan.allocations.length} действий</p><div className="allocation-bars">{plan.allocations.slice(0, 5).map((allocation) => <div key={allocation.id}><span>{allocation.instrument.ticker}</span><div><i style={{ width: `${Math.min(100, Number(allocation.target_weight) * 100)}%` }} /></div><small>{allocation.action} · {allocation.recommended_lots} лот.</small></div>)}</div><button className="button button--small" disabled={!!busy} onClick={() => void action(plan.id, () => api.createOrders(plan.id))}>Сформировать заявки</button></article>)}</div> : <Empty>Планов пока нет.</Empty>}
    </section>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">ORDER GATE</p><h2>Планируемые заявки</h2></div></div>
      {orders.length ? <div className="table-wrap"><table><thead><tr><th>Инструмент</th><th>Направление</th><th>Объём</th><th>Режим</th><th>Статус</th><th>Действия</th></tr></thead><tbody>{orders.map((order) => <tr key={order.id}><td><strong>{order.instrument.ticker}</strong><small>{formatMoney(order.limit_price, order.instrument.currency.toUpperCase())}</small></td><td><Status value={order.direction} /></td><td>{order.lots} лот.</td><td>{order.trade_mode}</td><td><Status value={order.status} /></td><td><div className="button-row">{order.status === "WAITING_CONFIRMATION" && <button className="button button--small button--primary" onClick={() => void action(order.id, () => api.approveOrder(order.id))}>Одобрить</button>}{["WAITING_CONFIRMATION", "APPROVED"].includes(order.status) && <button className="button button--small button--danger" onClick={() => void action(order.id, () => api.rejectOrder(order.id))}>Отклонить</button>}</div></td></tr>)}</tbody></table></div> : <Empty>Заявки ещё не сформированы.</Empty>}
    </section>
  </PageLayout>;
}

function Audit({ api }: { api: AdminApi }) {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [error, setError] = useState("");
  const load = useCallback(() => api.auditLogs().then(setLogs).catch((e: Error) => setError(e.message)), [api]);
  useEffect(() => void load(), [load]);
  return <PageLayout title="Журнал решений" subtitle="Хронология действий системы и администратора"><Notice error={error} /><section className="panel">
    {logs.length ? <div className="timeline">{logs.map((log) => <article key={log.id}><span className="timeline__dot" /><div><div className="timeline__meta"><Status value={log.severity.toUpperCase()} /><code>{log.event_type}</code><time>{formatDate(log.created_at)}</time></div><h3>{log.message}</h3><p>Инициатор: {log.actor}</p>{Object.keys(log.context).length > 0 && <pre>{JSON.stringify(log.context, null, 2)}</pre>}</div></article>)}</div> : <Empty>Журнал пока пуст.</Empty>}
  </section></PageLayout>;
}

function Safety({ api }: { api: AdminApi }) {
  const [settings, setSettings] = useState<SystemSettings>();
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const load = useCallback(() => api.settings().then(setSettings).catch((e: Error) => setError(e.message)), [api]);
  useEffect(() => void load(), [load]);

  async function update(payload: Partial<SystemSettings>) {
    try { setSettings(await api.updateSettings(payload)); setSuccess("Контур безопасности обновлён"); setError(""); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Ошибка обновления"); setSuccess(""); }
  }

  return <PageLayout title="Безопасность" subtitle="Независимые барьеры торгового контура"><Notice error={error} success={success} />
    {settings && <div className="safety-grid"><section className={`safety-card ${settings.kill_switch ? "safety-card--safe" : "safety-card--warn"}`}><p className="eyebrow">GLOBAL BARRIER</p><h2>Kill switch</h2><strong>{settings.kill_switch ? "ВКЛЮЧЁН" : "ВЫКЛЮЧЕН"}</strong><p>При включённом барьере Risk Manager отклоняет исполнение каждой заявки.</p><button className={`button ${settings.kill_switch ? "button--danger" : "button--primary"}`} onClick={() => void update({ kill_switch: !settings.kill_switch })}>{settings.kill_switch ? "Выключить kill switch" : "Включить kill switch"}</button></section>
      <section className="safety-card"><p className="eyebrow">RUNTIME ENV</p><h2>Реальная торговля</h2><strong>{settings.real_trading_enabled_by_env ? "РАЗРЕШЕНА ENV" : "ЗАБЛОКИРОВАНА ENV"}</strong><p>Флаг изменяется только через серверное окружение и не управляется из браузера.</p><Status value={settings.real_trading_enabled_by_env ? "ENABLED" : "DISABLED"} /></section>
      <section className="safety-card safety-card--wide"><p className="eyebrow">SYSTEM MODE</p><h2>Режим исполнения</h2><select value={settings.trade_mode} onChange={(e) => void update({ trade_mode: e.target.value as TradeMode })}>{TRADE_MODES.map((mode) => <option key={mode}>{mode}</option>)}</select><p>Production transport отсутствует. `REAL_MANUAL_CONFIRM` только переводит заявки в очередь подтверждения.</p></section></div>}
  </PageLayout>;
}

function PageLayout({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return <div className="page"><header className="page-header"><div><p className="eyebrow">AUTO INVEST MANAGER</p><h1>{title}</h1><p>{subtitle}</p></div><div className="live-indicator"><span /> API CONTROL</div></header>{children}</div>;
}

export function App() {
  const [apiKey, setApiKey] = useState(() => sessionStorage.getItem("aim-admin-key") ?? "");
  const [page, setPage] = useState<Page>("dashboard");
  const api = useMemo(() => new AdminApi(apiKey), [apiKey]);

  if (!apiKey) return <Login onConnect={(key) => { sessionStorage.setItem("aim-admin-key", key); setApiKey(key); }} />;

  const pages: Record<Page, ReactNode> = {
    dashboard: <Dashboard api={api} />,
    watchlist: <Watchlist api={api} />,
    risk: <ProfilePage api={api} kind="risk" />,
    strategy: <ProfilePage api={api} kind="strategy" />,
    rebalance: <Rebalance api={api} />,
    audit: <Audit api={api} />,
    safety: <Safety api={api} />,
  };

  return <div className="app-shell"><aside className="sidebar"><div className="brand"><div className="brand-mark">AI</div><div><strong>Auto Invest</strong><small>Manager</small></div></div><nav>{NAVIGATION.map((item) => <button key={item.id} className={page === item.id ? "active" : ""} onClick={() => setPage(item.id)}><span>{item.icon}</span>{item.label}</button>)}</nav><div className="sidebar-footer"><p>Ключ активен в этой вкладке</p><button onClick={() => { sessionStorage.removeItem("aim-admin-key"); setApiKey(""); }}>Завершить сессию</button></div></aside><main className="content">{pages[page]}</main></div>;
}
