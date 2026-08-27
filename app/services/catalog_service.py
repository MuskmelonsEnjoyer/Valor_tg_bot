import asyncio
import logging
from typing import Any

logger = logging.getLogger("instrument_refresh")
# A full broker refresh loads four instrument groups and then requests prices
# in batches. In normal conditions this can take close to a minute.
_T_INVEST_CATALOG_TIMEOUT_SECONDS = 120
_T_INVEST_CATALOG_RETRY_DELAY_SECONDS = 1


def _broker_rank(data: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(data.get("price_source") == "t_invest"),
        int(bool(data.get("api_trade_available"))),
        int(bool(data.get("buy_available") or data.get("sell_available"))),
    )


def _moex_rows(
    shares: dict[str, dict], bonds: dict[str, dict]
) -> list[dict[str, Any]]:
    rows = []
    for instrument_type, catalog in (("share", shares), ("bond", bonds)):
        for secid, raw_data in catalog.items():
            data = dict(raw_data)
            data.update(
                {
                    "secid": secid,
                    "instrument_type": instrument_type,
                    "asset_type": instrument_type,
                    "sources": ["moex"],
                }
            )
            rows.append(data)
    return rows


def merge_instrument_catalogs(
    shares: dict[str, dict],
    bonds: dict[str, dict],
    broker_instruments: list[dict],
) -> list[dict[str, Any]]:
    """Merge instruments by ISIN, preferring T-Invest metadata and prices."""
    merged = _moex_rows(shares, bonds)
    by_isin = {
        str(item["isin"]).upper(): index
        for index, item in enumerate(merged)
        if item.get("isin")
    }
    by_ticker_type = {
        (str(item["secid"]).upper(), item["instrument_type"]): index
        for index, item in enumerate(merged)
    }

    # T-Invest can return one security in several trading classes. Keep the
    # class with an available latest price/trading flag for the unified asset.
    preferred_broker: dict[str, dict] = {}
    for item in broker_instruments:
        isin = str(item.get("isin") or "").upper()
        identity = isin or str(item.get("uid") or item.get("secid") or "")
        current = preferred_broker.get(identity)
        if current is None or _broker_rank(item) > _broker_rank(current):
            preferred_broker[identity] = item

    used_secids = {str(item["secid"]).upper() for item in merged}
    for broker_data in preferred_broker.values():
        broker_data = dict(broker_data)
        isin = str(broker_data.get("isin") or "").upper()
        ticker = str(broker_data.get("ticker") or "").upper()
        instrument_type = str(broker_data.get("instrument_type") or "share")
        index = by_isin.get(isin) if isin else None
        if index is None:
            ticker_match = by_ticker_type.get((ticker, instrument_type))
            if ticker_match is not None:
                matched_isin = str(merged[ticker_match].get("isin") or "").upper()
                # Same ticker on different exchanges can represent different
                # assets. Use ticker only when at least one side lacks ISIN.
                if not isin or not matched_isin:
                    index = ticker_match

        if index is not None:
            moex_data = merged[index]
            moex_secid = moex_data["secid"]
            sources = list(dict.fromkeys([*moex_data.get("sources", []), "t_invest"]))
            moex_data.update(broker_data)
            moex_data["secid"] = moex_secid
            moex_data["sources"] = sources
            continue

        secid = str(broker_data.get("secid") or ticker).upper()
        if secid in used_secids:
            uid_suffix = str(broker_data.get("uid") or "")[:8].upper()
            secid = f"{secid}@{uid_suffix}"
        broker_data["secid"] = secid
        used_secids.add(secid)
        merged.append(broker_data)
        if isin:
            by_isin[isin] = len(merged) - 1
        by_ticker_type[(ticker, instrument_type)] = len(merged) - 1

    return merged


async def load_unified_catalog(t_invest_token: str | None) -> list[dict[str, Any]]:
    """Load both upstreams; one healthy source is enough for a refresh."""
    from app.services.api_moex import parsing_instruments
    from app.services.t_invest import get_broker_instruments
    from t_tech.invest.exceptions import AioRequestError

    async def load_broker_with_retry() -> list[dict]:
        for attempt in range(3):
            try:
                return await get_broker_instruments(t_invest_token)
            except AioRequestError as exc:
                if exc.code.name not in {"UNAVAILABLE", "DEADLINE_EXCEEDED"}:
                    raise
                if attempt == 2:
                    raise
                logger.warning(
                    "T-Invest catalog connection failed (%s), retrying",
                    exc.code.name,
                )
                await asyncio.sleep(_T_INVEST_CATALOG_RETRY_DELAY_SECONDS)
        return []

    moex_task = parsing_instruments()
    if t_invest_token:
        # gRPC retries TLS handshakes internally. Bound the wait so a broken
        # T-Invest certificate chain cannot delay an otherwise healthy MOEX
        # refresh indefinitely.
        broker_task = asyncio.wait_for(
            load_broker_with_retry(),
            timeout=_T_INVEST_CATALOG_TIMEOUT_SECONDS,
        )
        moex_result, broker_result = await asyncio.gather(
            moex_task, broker_task, return_exceptions=True
        )
    else:
        moex_result = await moex_task
        broker_result = []

    if isinstance(moex_result, Exception):
        logger.exception(
            "MOEX catalog load failed; continuing with T-Invest",
            exc_info=moex_result,
        )
        shares, bonds = {}, {}
    else:
        shares, bonds = moex_result

    if isinstance(broker_result, Exception):
        logger.exception(
            "T-Invest catalog load failed; continuing with MOEX",
            exc_info=broker_result,
        )
        broker_instruments = []
    else:
        broker_instruments = broker_result

    if not shares and not bonds and not broker_instruments:
        raise RuntimeError("Neither MOEX nor T-Invest returned instruments")

    return merge_instrument_catalogs(shares, bonds, broker_instruments)
