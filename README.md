# Auto Invest Manager

Безопасная рекомендательно-торговая система для T-Invest API с FastAPI backend и
React admin UI. Реализованы получение рыночных данных, baseline-сигналы,
long-only оптимизация, dry-run, sandbox и ручное подтверждение заявок. Отправка
реальных заявок физически отсутствует.

## Требования

- Docker 24+ с Docker Compose;
- либо Python 3.12, Node.js 22 и доступные PostgreSQL 16 / Redis 7.

## Запуск через Docker

```powershell
Copy-Item .env.example .env
# Обязательно замените POSTGRES_PASSWORD и пароль в DATABASE_URL на одинаковое значение.
# Задайте ADMIN_API_KEY случайной строкой длиной не менее 32 символов.
docker compose up --build
```

Миграции выполняются отдельным одноразовым сервисом `migrate` до старта API.
OpenAPI доступен по адресу <http://localhost:8000/docs>.
Admin UI доступен по адресу <http://localhost:3000>. При первом входе он запросит
значение `ADMIN_API_KEY`; ключ хранится только в `sessionStorage` текущей вкладки.

По умолчанию используется `BROKER_PROVIDER=mock`, поэтому токен не нужен. Для API
установите `BROKER_PROVIDER=tinvest`, выберите `TINVEST_TARGET=prod|sandbox` и задайте
токен соответствующего контура. Токены читаются только из окружения.

## Локальная разработка

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload

# В отдельном терминале:
cd frontend
npm install
npm run dev
```

Vite UI доступен по адресу <http://localhost:5173> и проксирует `/api` в локальный
backend на порту 8000.

## Endpoints

- `GET /health/live` — процесс API работает;
- `GET /health/ready` — PostgreSQL и Redis доступны;
- `GET /docs` — Swagger UI;
- `GET /openapi.json` — OpenAPI schema.

Admin API расположен под `/api/v1/admin` и требует заголовок
`X-Admin-API-Key`. Без настроенного `ADMIN_API_KEY` административные endpoints
возвращают `503` — это безопасное поведение по умолчанию.

Доступные endpoints этапа 3:

- `GET /api/v1/admin/accounts`;
- `GET|PATCH /api/v1/admin/settings`;
- `POST /api/v1/admin/instruments/sync`;
- `GET|POST /api/v1/admin/watchlist`;
- `PATCH|DELETE /api/v1/admin/watchlist/{item_id}`;
- `GET|PATCH /api/v1/admin/risk-profile`;
- `GET|PATCH /api/v1/admin/strategy-profile`.
- `GET /api/v1/admin/audit-logs`;
- `GET /api/v1/admin/signals`;
- `POST /api/v1/admin/analysis/run`.
- `GET /api/v1/admin/rebalance-plans`;
- `POST /api/v1/admin/rebalance-plans/run`.
- `POST /api/v1/admin/rebalance-plans/{plan_id}/execution-plan`;
- `GET /api/v1/admin/planned-orders`;
- `POST /api/v1/admin/planned-orders/{order_id}/approve`;
- `POST /api/v1/admin/planned-orders/{order_id}/reject`;
- `POST /api/v1/admin/planned-orders/{order_id}/dry-run`;
- `POST /api/v1/admin/planned-orders/{order_id}/sandbox`;
- `GET /api/v1/admin/virtual-trades`.

Seed безопасных профилей выполняется при старте backend. Вручную:

```powershell
python -m app.commands.seed
```

## Проверки

```powershell
ruff check .
pytest
```

Эксплуатационный запуск, режимы безопасности и действия при инцидентах описаны в
[`docs/operations.md`](docs/operations.md).

## Безопасность

`ENABLE_REAL_TRADING=false` и `GLOBAL_KILL_SWITCH=true` являются безопасными
значениями по умолчанию. На этапе 1 код отправки заявок отсутствует физически.

## Admin UI

Интерфейс включает Dashboard, Watchlist, Risk Profile, Strategy Profile,
Rebalance Plans, Planned Orders, Audit Logs и Safety. Из UI можно запускать анализ
и планирование, формировать заявки и вручную одобрять/отклонять заявки режима
`REAL_MANUAL_CONFIRM`. Одобрение меняет только состояние заявки и не отправляет её
брокеру.

Signal Engine v1 использует 20 завершённых свечей и рассчитывает trend, moving
average, volatility, volume и drawdown scores. Итоговая рекомендация принимает
одно из значений `BUY`, `HOLD`, `SELL`, `WAIT`. Неполные, недостаточные или
устаревшие рыночные данные отклоняются.

Portfolio Optimizer работает только в long-only режиме, сохраняет обязательный
cash reserve и применяет ограничения позиции. Rebalance Planner учитывает целые
лоты, доступный кэш и порог ребалансировки. При нулевом кэше целевые рекомендации
сохраняются, но заявки на покупку не формируются.

Dry-run executor перед каждой виртуальной сделкой повторно проверяет kill switch,
режим, счёт, watchlist, торговый статус, свежесть цены, кэш, лимиты позиции и сделки,
дневной лимит, cooldown, идемпотентность и отсутствие дубликатов. Брокерские заявки
в этом контуре не создаются.

Sandbox executor доступен только при `BROKER_PROVIDER=tinvest`,
`TINVEST_TARGET=sandbox`, режиме `SANDBOX` и выключенном kill switch. Каждая заявка
имеет стабильный `order_id`, сохраняется вместе с broker response и не отправляется
повторно при повторном вызове.

В режиме `REAL_MANUAL_CONFIRM` заявки создаются только в статусе
`WAITING_CONFIRMATION`. Одобрение и отклонение сохраняются в audit log. Production
order transport отсутствует в `BrokerProvider`, поэтому одобрение не может привести
к реальной сделке. `ENABLE_REAL_TRADING=false` остаётся дополнительным env-барьером.

Telegram-уведомления опциональны и по умолчанию выключены. При включении они
отправляются после сохранения результатов анализа, плана ребалансировки и решения
по manual-confirmation заявке; недоступность Telegram не ломает бизнес-операцию.
