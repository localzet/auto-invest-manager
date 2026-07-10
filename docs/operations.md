# Operations Runbook

## Безопасный запуск

1. Скопируйте `.env.example` в `.env`.
2. Замените `POSTGRES_PASSWORD` и синхронно обновите пароль в `DATABASE_URL`.
3. Создайте случайный `ADMIN_API_KEY` длиной не менее 32 символов.
4. Оставьте `ENABLE_REAL_TRADING=false` и `GLOBAL_KILL_SWITCH=true`.
5. Проверьте конфигурацию: `docker compose config --quiet`.
6. Запустите сервисы: `docker compose up --build -d`.
7. Проверьте `/health/live`, затем `/health/ready` и журнал сервиса `migrate`.

Admin UI доступен на порту `FRONTEND_PORT` (по умолчанию 3000), API — на
`APP_PORT` (по умолчанию 8000).

## Торговые режимы

- `OFF` — торговый контур выключен;
- `SIGNAL_ONLY` — только расчёт сигналов;
- `DRY_RUN` — виртуальные сделки без брокера;
- `SANDBOX` — заявки только в T-Invest sandbox;
- `REAL_MANUAL_CONFIRM` — ручное изменение статуса без отправки брокеру;
- `REAL_AUTO_SAFE` — зарезервирован, production transport отсутствует.

Переключение режима не отключает kill switch и не сбрасывает дневные risk-счётчики.

## Telegram

Уведомления выключены по умолчанию. Для включения задайте:

```dotenv
TELEGRAM_NOTIFICATIONS_ENABLED=true
TELEGRAM_BOT_TOKEN=<bot-token>
TELEGRAM_CHAT_ID=<chat-id>
TELEGRAM_TIMEOUT_SECONDS=5
```

При включённом флаге отсутствие token или chat ID останавливает запуск на проверке
конфигурации. Уведомления отправляются после фиксации сигнала, плана или решения по
ручной заявке. Ошибка Telegram записывается в application log, но не откатывает
успешно сохранённую бизнес-операцию.

## Инциденты

### Немедленная остановка исполнения

1. Включите kill switch в Admin UI → Safety.
2. Установите `GLOBAL_KILL_SWITCH=true` в окружении перед следующим рестартом.
3. Не меняйте `ENABLE_REAL_TRADING=false`.
4. Сохраните логи backend и записи `/api/v1/admin/audit-logs` до исправлений.

### API не готов

1. Проверьте `docker compose ps`.
2. Проверьте `docker compose logs migrate backend postgres redis`.
3. Убедитесь, что пароль PostgreSQL совпадает в `POSTGRES_PASSWORD` и
   `DATABASE_URL`.
4. Запустите `docker compose config --quiet` и `alembic upgrade head --sql`.

### Telegram не доставляет сообщения

1. Проверьте, что уведомления включены и обе переменные заданы.
2. Проверьте доступ контейнера backend к `api.telegram.org`.
3. Проверьте application log на `Notification delivery failed`.
4. Не повторяйте торговую операцию только ради уведомления: она уже могла быть
   успешно сохранена.

## Backup и восстановление

Перед обновлением схемы создайте согласованный backup PostgreSQL. Redis содержит
вспомогательное состояние и не является источником истины. Восстановление сначала
проверяйте в отдельной базе, затем выполняйте healthcheck и read-only запросы Admin
API до разрешения любых режимов исполнения.
