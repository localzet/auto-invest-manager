from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.admin.errors import ResourceConflictError
from app.admin.schemas import RiskProfileUpdate
from app.admin.service import AdminService
from app.broker.mock import MockBrokerProvider
from app.core.config import Settings


async def test_risk_update_rejects_combined_weight_above_portfolio() -> None:
    repository = SimpleNamespace(
        get_active_risk_profile=AsyncMock(
            return_value=SimpleNamespace(
                max_position_weight=Decimal("0.20"),
                min_cash_weight=Decimal("0.10"),
            )
        ),
        apply_changes=Mock(),
        add_audit=Mock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
    )
    service = AdminService(
        repository,
        MockBrokerProvider(),
        Settings(_env_file=None),
    )

    with pytest.raises(ResourceConflictError, match="cannot exceed 1"):
        await service.update_risk_profile(
            RiskProfileUpdate(
                max_position_weight=Decimal("0.80"),
                min_cash_weight=Decimal("0.30"),
            )
        )

    repository.commit.assert_not_awaited()
