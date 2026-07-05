from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings


async def require_admin_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    provided_key: Annotated[str | None, Header(alias="X-Admin-API-Key")] = None,
) -> None:
    configured_key = settings.admin_api_key
    if configured_key is None or not configured_key.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API key is not configured",
        )
    if provided_key is None or not compare_digest(provided_key, configured_key.get_secret_value()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin API key",
        )
