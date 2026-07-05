# Auto Invest Manager

Безопасный каркас рекомендательно-торговой системы для T-Invest API. Текущая
итерация реализует этапы 1–2: инфраструктуру backend, базовую схему данных,
healthcheck и абстракцию получения данных T-Invest с детерминированным mock provider.
Исполнение заявок пока отсутствует.

## Требования

- Docker 24+ с Docker Compose;
- либо Python 3.12 и доступные PostgreSQL 16 / Redis 7.

## Запуск через Docker

```powershell
Copy-Item .env.example .env
# Обязательно замените POSTGRES_PASSWORD и пароль в DATABASE_URL на одинаковое значение.
# Задайте ADMIN_API_KEY случайной строкой длиной не менее 32 символов.
docker compose up --build
```

Миграции выполняются отдельным одноразовым сервисом `migrate` до старта API.
OpenAPI доступен по адресу <http://localhost:8000/docs>.

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
```

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

Seed безопасных профилей выполняется при старте backend. Вручную:

```powershell
python -m app.commands.seed
```

## Проверки

```powershell
ruff check .
pytest
```

## Безопасность

`ENABLE_REAL_TRADING=false` и `GLOBAL_KILL_SWITCH=true` являются безопасными
значениями по умолчанию. На этапе 1 код отправки заявок отсутствует физически.

## Границы этапа 1

Созданы базовые модели для настроек, счетов, инструментов, watchlist, risk/strategy
profiles, снимков портфеля, рыночных данных и audit log. Таблицы торгового контура
(signals, планы, заявки и virtual trades) будут добавляться вместе с соответствующей
бизнес-логикой, чтобы миграции отражали реальные инварианты, а не преждевременные
предположения.

Следующий этап: signal engine v1 и сохранение рассчитанных сигналов.
