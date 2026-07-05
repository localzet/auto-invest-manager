from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.dependencies import get_admin_service
from app.core.config import Settings, get_settings
from app.main import create_app
from app.models.enums import TradeMode

ADMIN_KEY = "test-admin-key-with-sufficient-entropy"


class FakeAdminService:
    real_trading_enabled_by_env = False

    async def get_system_settings(self) -> SimpleNamespace:
        return SimpleNamespace(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            trade_mode=TradeMode.OFF,
            kill_switch=True,
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def create_admin_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, admin_api_key=ADMIN_KEY
    )
    app.dependency_overrides[get_admin_service] = FakeAdminService
    return TestClient(app)


def test_admin_api_rejects_missing_key() -> None:
    response = create_admin_client().get("/api/v1/admin/settings")

    assert response.status_code == 401


def test_admin_api_returns_settings_without_exposing_secrets() -> None:
    response = create_admin_client().get(
        "/api/v1/admin/settings", headers={"X-Admin-API-Key": ADMIN_KEY}
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": "00000000-0000-0000-0000-000000000001",
        "trade_mode": "OFF",
        "kill_switch": True,
        "updated_at": "2026-01-01T00:00:00Z",
        "real_trading_enabled_by_env": False,
    }
