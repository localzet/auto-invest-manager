# Auto Invest Manager

Безопасный каркас рекомендательно-торговой системы для T-Invest API. Текущая
итерация реализует только этап 1: инфраструктуру backend, базовую схему данных и
healthcheck. Интеграция с брокером и исполнение заявок пока отсутствуют.

## Требования

- Docker 24+ с Docker Compose;
- либо Python 3.12 и доступные PostgreSQL 16 / Redis 7.

## Запуск через Docker

```powershell
Copy-Item .env.example .env
# Обязательно замените POSTGRES_PASSWORD и пароль в DATABASE_URL на одинаковое значение.
docker compose up --build
```

Миграции выполняются отдельным одноразовым сервисом `migrate` до старта API.
OpenAPI доступен по адресу <http://localhost:8000/docs>.

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

Следующий этап: интерфейс провайдера брокерских данных, `TInvestClient` и полностью
детерминированный mock provider.
