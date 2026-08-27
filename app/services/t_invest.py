import asyncio
import logging
import os
from decimal import Decimal

from t_tech.invest import AsyncClient, InstrumentIdType, InstrumentStatus
from t_tech.invest.exceptions import AioRequestError
from t_tech.invest.utils import money_to_decimal, quotation_to_decimal

logger = logging.getLogger("t_invest")

_PRICE_BATCH_SIZE = 300
_market_data_token: str | None = None
_RETRYABLE_T_INVEST_CODES = {"UNAVAILABLE", "DEADLINE_EXCEEDED"}


def configure_t_invest_tls(use_bundled_russian_ca: bool) -> None:
    """Configure the CA bundle supported by the official T-Invest SDK."""
    os.environ["SSL_TBANK_VERIFY"] = (
        "true" if use_bundled_russian_ca else "false"
    )


def configure_market_data_token(token: str | None) -> None:
    global _market_data_token
    _market_data_token = token


def get_market_data_token() -> str | None:
    """Return the configured system token used for public market data."""
    return _market_data_token


def _text(value) -> str | None:
    if value is None:
        return None
    name = getattr(value, "name", None)
    return str(name if name is not None else value)


def _money(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return money_to_decimal(value)
    except (AttributeError, TypeError, ValueError):
        return None


def _pack_instrument(item, instrument_type: str) -> dict | None:
    uid = str(getattr(item, "uid", "") or "").strip()
    ticker = str(getattr(item, "ticker", "") or "").strip().upper()
    if not uid or not ticker:
        return None

    isin = str(getattr(item, "isin", "") or "").strip().upper() or None
    figi = str(getattr(item, "figi", "") or "").strip() or None
    class_code = str(getattr(item, "class_code", "") or "").strip().upper()
    currency = str(getattr(item, "currency", "") or "RUB").strip().upper()
    nominal = _money(getattr(item, "nominal", None))

    data = {
        "uid": uid,
        "figi": figi,
        "ticker": ticker,
        "isin": isin,
        "name": str(getattr(item, "name", "") or ticker),
        # The bot currently exposes two search groups: bonds and
        # shares/funds. Neoassets are futures in T-Invest, but belong to the
        # latter group from the user's point of view.
        "instrument_type": (
            "share" if instrument_type in {"etf", "neoasset"} else instrument_type
        ),
        "asset_type": instrument_type,
        "currency": currency,
        "class_code": class_code or None,
        "exchange": str(getattr(item, "exchange", "") or "") or None,
        "real_exchange": _text(getattr(item, "real_exchange", None)),
        "lot": getattr(item, "lot", None),
        "api_trade_available": bool(
            getattr(item, "api_trade_available_flag", False)
        ),
        "buy_available": bool(getattr(item, "buy_available_flag", False)),
        "sell_available": bool(getattr(item, "sell_available_flag", False)),
        "sources": ["t_invest"],
    }
    if instrument_type == "bond":
        data["bond_name"] = data["name"]
        if nominal is not None:
            data["face_value"] = float(nominal)
    elif instrument_type == "neoasset":
        data["basic_asset"] = str(getattr(item, "basic_asset", "") or "") or None
        data["futures_type"] = str(getattr(item, "futures_type", "") or "") or None

    # A ticker is not globally unique across trading classes. The merge layer
    # keeps the familiar MOEX SECID when ISINs match and uses this value for
    # broker-only instruments.
    data["secid"] = f"{ticker}@{class_code}" if class_code else f"{ticker}@{uid[:8]}"
    return data


async def _load_last_prices(
    client: AsyncClient, instruments: list[dict]
) -> set[str]:
    by_uid = {item["uid"]: item for item in instruments}
    uids = list(by_uid)
    updated_uids: set[str] = set()

    for offset in range(0, len(uids), _PRICE_BATCH_SIZE):
        response = await client.market_data.get_last_prices(
            instrument_id=uids[offset : offset + _PRICE_BATCH_SIZE]
        )
        for price_item in response.last_prices:
            uid = str(getattr(price_item, "instrument_uid", "") or "")
            data = by_uid.get(uid)
            if data is None:
                continue

            price = quotation_to_decimal(price_item.price)
            if not price.is_finite() or price <= 0:
                continue

            if data["asset_type"] == "bond":
                nominal = data.get("face_value")
                data["price_percent"] = float(price)
                if nominal is None:
                    continue
                price = price * Decimal(str(nominal)) / Decimal("100")

            timestamp = getattr(price_item, "time", None)
            data["last"] = float(price)
            data["last_price"] = float(price)
            data["price_source"] = "t_invest"
            data["price_field"] = "LAST_PRICE"
            data["price_date"] = (
                timestamp.isoformat() if hasattr(timestamp, "isoformat") else None
            )
            data["price_delay_minutes"] = 0
            updated_uids.add(uid)
    return updated_uids


async def _resolve_missing_uids(
    client: AsyncClient,
    instruments: list[dict],
    *,
    force: bool = False,
) -> None:
    """Resolve rows to the preferred trade-enabled T-Invest UID by ISIN."""
    for data in instruments:
        if data.get("uid") and not force:
            continue
        isin = str(data.get("isin") or "").strip().upper()
        if not isin:
            continue

        try:
            response = await client.instruments.find_instrument(query=isin)
        except AioRequestError as exc:
            if exc.code.name in {
                "UNAUTHENTICATED",
                "PERMISSION_DENIED",
                *_RETRYABLE_T_INVEST_CODES,
            }:
                raise
            logger.info(
                "T-Invest instrument was not resolved for ISIN %s: %s",
                isin,
                exc.code.name,
            )
            continue

        exact_matches = [
            item
            for item in response.instruments
            if str(getattr(item, "isin", "") or "").strip().upper() == isin
        ]
        exact_matches.sort(
            key=lambda item: (
                bool(getattr(item, "api_trade_available_flag", False)),
                str(getattr(item, "class_code", "") or "").upper()
                in {"TQBR", "TQCB", "TQTF", "SPBXM"},
            ),
            reverse=True,
        )
        instrument = exact_matches[0] if exact_matches else None
        if instrument is None:
            continue
        uid = str(getattr(instrument, "uid", "") or "").strip()
        if not uid:
            continue
        data["uid"] = uid
        data["figi"] = str(getattr(instrument, "figi", "") or "") or None
        data["ticker"] = (
            str(getattr(instrument, "ticker", "") or "").strip().upper()
            or data.get("ticker")
            or data.get("secid")
        )


async def get_broker_instruments(token: str) -> list[dict]:
    """Return broker instruments enriched with latest T-Invest trade prices."""
    async with AsyncClient(token) as client:
        responses = [
            (
                "share",
                (
                    await client.instruments.shares(
                        instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
                    )
                ).instruments,
            ),
            (
                "bond",
                (
                    await client.instruments.bonds(
                        instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
                    )
                ).instruments,
            ),
            (
                "etf",
                (
                    await client.instruments.etfs(
                        instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
                    )
                ).instruments,
            ),
            (
                "neoasset",
                [
                    item
                    for item in (
                        await client.instruments.futures(
                            instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
                        )
                    ).instruments
                    if str(getattr(item, "ticker", "") or "")
                    .upper()
                    .endswith("PERPA")
                ],
            ),
        ]

        result = []
        for instrument_type, items in responses:
            for item in items:
                packed = _pack_instrument(item, instrument_type)
                if packed is not None:
                    result.append(packed)

        await _load_last_prices(client, result)
        return result


async def get_all_instruments_list(token: str) -> list[dict]:
    """Compatibility wrapper for callers that need the T-Invest catalog."""
    return await get_broker_instruments(token)


async def find_broker_neoassets(query: str, token: str) -> list[dict]:
    """Find neoassets on demand using a user's stored read-only token."""
    normalized_query = query.strip().upper()
    if not normalized_query:
        return []

    async with AsyncClient(token) as client:
        response = await client.instruments.find_instrument(query=query.strip())
        candidates = [
            item
            for item in response.instruments
            if str(getattr(item, "ticker", "") or "")
            .upper()
            .endswith("PERPA")
        ]
        # Prefer an exact ticker and keep an upper bound for broad queries.
        candidates.sort(
            key=lambda item: str(getattr(item, "ticker", "") or "").upper()
            != normalized_query
        )

        result = []
        for item in candidates[:20]:
            detail = await client.instruments.future_by(
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_UID,
                id=str(getattr(item, "uid", "") or ""),
            )
            packed = _pack_instrument(detail.instrument, "neoasset")
            if packed is not None:
                result.append(packed)

        await _load_last_prices(client, result)
        return result


async def enrich_with_latest_prices(
    instruments: list[dict], token: str | None = None
) -> list[dict]:
    """Overlay live T-Invest last trades, preserving stored MOEX fallbacks."""
    result = [dict(item) for item in instruments]
    token_candidates = list(
        dict.fromkeys(
            candidate
            for candidate in (token, _market_data_token)
            if candidate
        )
    )
    if not token_candidates:
        return result

    for item in result:
        item.setdefault("asset_type", item.get("instrument_type", "share"))

    for token_index, effective_token in enumerate(token_candidates):
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                async with AsyncClient(effective_token) as client:
                    await _resolve_missing_uids(client, result)
                    candidates = [item for item in result if item.get("uid")]
                    if candidates:
                        updated_uids = await _load_last_prices(client, candidates)
                        stale_candidates = [
                            item
                            for item in candidates
                            if item.get("uid") not in updated_uids and item.get("isin")
                        ]
                        if stale_candidates:
                            # A single ISIN can have multiple trading classes.
                            # Replace an old/non-trading UID and retry once.
                            await _resolve_missing_uids(
                                client,
                                stale_candidates,
                                force=True,
                            )
                            await _load_last_prices(client, stale_candidates)
                return result
            except AioRequestError as exc:
                last_error = exc
                if exc.code.name in _RETRYABLE_T_INVEST_CODES and attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                break
            except Exception as exc:
                last_error = exc
                break

        has_fallback = token_index + 1 < len(token_candidates)
        logger.error(
            "Не удалось обновить цены T-Invest%s; используются %s",
            " с пользовательским токеном" if token else "",
            "резервный токен" if has_fallback else "сохраненные цены",
            exc_info=last_error,
        )
    return result


async def find_current_price(figi: str, token: str) -> float | None:
    async with AsyncClient(token) as client:
        try:
            instrument_response = await client.instruments.get_instrument_by(
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, id=figi
            )
            instrument = instrument_response.instrument
            price_response = await client.market_data.get_last_prices(
                instrument_id=[instrument.uid]
            )

            if not price_response.last_prices:
                logger.info("Цена для FIGI %s не найдена", figi)
                return None

            current_price = quotation_to_decimal(price_response.last_prices[0].price)
            if instrument.instrument_type == "bond":
                bond_response = await client.instruments.bond_by(
                    id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_UID,
                    id=instrument.uid,
                )
                nominal = money_to_decimal(bond_response.instrument.nominal)
                current_price = current_price * nominal / Decimal("100")
            return float(current_price)

        except Exception as exc:
            logger.exception("Ошибка при запросе цены FIGI %s: %s", figi, exc)
            return None
