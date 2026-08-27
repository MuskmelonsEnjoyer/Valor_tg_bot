from app.database import requests
from app.services.t_invest import get_market_data_token


async def resolve_market_data_token(user_id: int | None) -> str | None:
    """Prefer the user's token and fall back to the configured system token."""
    if user_id is not None:
        user_token = await requests.get_user_token(user_id)
        if user_token and user_token.strip():
            return user_token.strip()

    system_token = get_market_data_token()
    return system_token.strip() if system_token and system_token.strip() else None
