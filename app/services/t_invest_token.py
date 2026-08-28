import asyncio
import logging

from app.database import requests
from app.services.t_invest import (
    MarketDataTokenCandidate,
    find_broker_neoassets,
    get_market_data_token,
)
from t_tech.invest.exceptions import AioRequestError, AioUnauthenticatedError


logger = logging.getLogger("t_invest")
_RETRYABLE_T_INVEST_CODES = {"UNAVAILABLE", "DEADLINE_EXCEEDED"}


async def resolve_market_data_tokens(
    user_id: int | None,
) -> tuple[MarketDataTokenCandidate, ...]:
    """Return public market-data tokens in user-then-system order."""
    candidates: list[MarketDataTokenCandidate] = []
    seen_tokens: set[str] = set()

    if user_id is not None:
        user_token = await requests.get_user_token(user_id)
        normalized_user_token = user_token.strip() if user_token else ""
        if normalized_user_token:
            candidates.append(
                MarketDataTokenCandidate(normalized_user_token, "user")
            )
            seen_tokens.add(normalized_user_token)

    system_token = get_market_data_token()
    normalized_system_token = system_token.strip() if system_token else ""
    if normalized_system_token and normalized_system_token not in seen_tokens:
        candidates.append(
            MarketDataTokenCandidate(normalized_system_token, "system")
        )

    return tuple(candidates)


async def resolve_market_data_token(user_id: int | None) -> str | None:
    """Prefer the user's token and fall back to the configured system token."""
    candidates = await resolve_market_data_tokens(user_id)
    return candidates[0].token if candidates else None


async def resolve_private_user_token(user_id: int) -> str | None:
    """Return only the user's DB token for private account operations."""
    user_token = await requests.get_user_token(user_id)
    return user_token.strip() if user_token and user_token.strip() else None


async def discard_rejected_user_token(
    user_id: int,
    candidate: MarketDataTokenCandidate,
) -> bool:
    """Delete a rejected user token if the same value is still stored."""
    if candidate.source != "user":
        return False

    stored_token = await requests.get_user_token(user_id)
    if not stored_token or stored_token.strip() != candidate.token:
        return False

    deleted = await requests.delete_user_token(user_id)
    if deleted:
        logger.warning(
            "[User %s] Отклоненный token T-Invest удален из БД",
            user_id,
        )
    return deleted


async def discard_rejected_private_user_token(
    user_id: int,
    token: str,
) -> bool:
    """Delete a rejected private token while preserving race safety."""
    return await discard_rejected_user_token(
        user_id,
        MarketDataTokenCandidate(token, "user"),
    )


async def find_broker_neoassets_for_user(
    query: str,
    user_id: int | None,
) -> list[dict]:
    """Search public broker data with DB user-token and system fallback."""
    candidates = await resolve_market_data_tokens(user_id)
    for index, candidate in enumerate(candidates):
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return await find_broker_neoassets(query, candidate.token)
            except AioUnauthenticatedError as exc:
                last_error = exc
                if user_id is not None:
                    await discard_rejected_user_token(user_id, candidate)
                break
            except AioRequestError as exc:
                last_error = exc
                if exc.code.name in _RETRYABLE_T_INVEST_CODES and attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                break
            except Exception as exc:
                last_error = exc
                break

        has_fallback = index + 1 < len(candidates)
        if isinstance(last_error, AioUnauthenticatedError):
            logger.warning(
                "%s token T-Invest отклонен при поиске неоактива; %s",
                candidate.source.capitalize(),
                "пробуем следующий token"
                if has_fallback
                else "поиск через T-Invest пропущен",
            )
        else:
            logger.error(
                "Поиск неоактива через %s token T-Invest завершился ошибкой; %s",
                candidate.source,
                "пробуем следующий token"
                if has_fallback
                else "поиск через T-Invest пропущен",
                exc_info=last_error,
            )

    return []
