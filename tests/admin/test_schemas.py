from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.admin.schemas import WatchlistItemCreate


def test_watchlist_rejects_target_above_limit() -> None:
    with pytest.raises(ValidationError, match="manual_target_weight cannot exceed max_weight"):
        WatchlistItemCreate(
            ticker="SBER",
            class_code="TQBR",
            max_weight=Decimal("0.10"),
            manual_target_weight=Decimal("0.20"),
        )
