import logging
from typing import Any

from app.database import requests
from app.services.t_invest import MarketDataTokenCandidate, enrich_with_latest_prices
from app.services.t_invest_token import (
    discard_rejected_user_token,
    resolve_market_data_tokens,
)


logger = logging.getLogger("t_invest")


async def refresh_and_store_instrument(
    instrument: dict[str, Any],
    *,
    token: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Fetch a T-Invest price when possible and persist the enriched row."""
    if user_id is None:
        enriched_rows = await enrich_with_latest_prices([instrument], token=token)
    else:
        token_candidates = await resolve_market_data_tokens(user_id)

        async def discard_rejected_token(
            candidate: MarketDataTokenCandidate,
        ) -> None:
            await discard_rejected_user_token(user_id, candidate)

        enriched_rows = await enrich_with_latest_prices(
            [instrument],
            token_candidates=token_candidates,
            on_unauthenticated=discard_rejected_token,
        )

    enriched = enriched_rows[0]
    uid_was_resolved = bool(enriched.get("uid")) and not instrument.get("uid")
    has_t_invest_price = enriched.get("price_source") == "t_invest"

    if not enriched.get("secid") or not (uid_was_resolved or has_t_invest_price):
        return enriched

    try:
        await requests.upsert_instrument_catalog([enriched])
    except Exception as exc:
        # The user can still receive the live response even if caching it
        # failed. A later catalog refresh can repair the stored row.
        logger.warning(
            "Не удалось сохранить актуальные данные T-Invest для %s: %s",
            enriched.get("secid"),
            exc,
        )
    return enriched
