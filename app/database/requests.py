from decimal import Decimal, InvalidOperation
from collections.abc import Iterable
from typing import Any

from app.database import models
from app.database.session import get_session_factory
from app.services.api_moex import parsing_instruments
from app.services.catalog_service import load_unified_catalog
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_user(session: AsyncSession, user_id: int) -> None:
    stmt = pg_insert(models.AppUser).values(user_id=user_id)
    await session.execute(stmt.on_conflict_do_nothing(index_elements=["user_id"]))


async def save_user_token(user_id: int, token: str) -> None:
    async with get_session_factory()() as session, session.begin():
        await ensure_user(session, user_id)
        stmt = pg_insert(models.UserToken).values(
            user_id=user_id, user_t_invest_token=token
        )
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_={"user_t_invest_token": stmt.excluded.user_t_invest_token},
        )
        await session.execute(upsert_stmt)


async def get_user_token(user_id: int) -> str | None:
    async with get_session_factory()() as session:
        stmt = select(models.UserToken.user_t_invest_token).where(
            models.UserToken.user_id == user_id
        )
        return await session.scalar(stmt)


async def delete_user_token(user_id: int) -> bool:
    async with get_session_factory()() as session, session.begin():
        stmt = delete(models.UserToken).where(models.UserToken.user_id == user_id)
        result = await session.execute(stmt)
        return result.rowcount > 0


async def _find_instrument(
    session: AsyncSession, identifier: str
) -> models.Instruments | None:
    ticker = models.Instruments.extra_data["ticker"].astext
    figi = models.Instruments.extra_data["figi"].astext
    uid = models.Instruments.extra_data["uid"].astext
    exact_order = case(
        (models.Instruments.secid == identifier, 0),
        (models.Instruments.isin == identifier, 1),
        (uid.ilike(identifier), 2),
        (figi.ilike(identifier), 3),
        else_=4,
    )
    stmt = (
        select(models.Instruments)
        .where(
            or_(
                models.Instruments.secid == identifier,
                models.Instruments.isin == identifier,
                ticker == identifier,
                figi.ilike(identifier),
                uid.ilike(identifier),
            )
        )
        .order_by(exact_order)
        .limit(1)
    )
    return await session.scalar(stmt)


async def find_inst_data(identifier: str) -> dict[str, Any] | None:
    async with get_session_factory()() as session:
        instrument = await _find_instrument(session, identifier.strip().upper())
        if instrument is None:
            return None

        data = dict(instrument.extra_data or {})
        data.update(
            {
                "secid": instrument.secid,
                "isin": instrument.isin,
                "instrument_type": instrument.instrument_type,
                "currency": instrument.currency,
            }
        )
        return data


async def search_instruments(
    query: str,
    instrument_type: str,
    limit: int = 8,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], bool]:
    normalized_query = query.strip()
    if not normalized_query:
        return [], False

    limit = max(1, min(limit, 20))
    offset = max(0, offset)
    pattern = f"%{normalized_query}%"
    name = models.Instruments.extra_data["name"].astext
    bond_name = models.Instruments.extra_data["bond_name"].astext
    ticker = models.Instruments.extra_data["ticker"].astext
    figi = models.Instruments.extra_data["figi"].astext
    uid = models.Instruments.extra_data["uid"].astext
    match_order = case(
        (models.Instruments.secid.ilike(normalized_query), 0),
        (models.Instruments.isin.ilike(normalized_query), 0),
        (ticker.ilike(normalized_query), 0),
        (figi.ilike(normalized_query), 0),
        (uid.ilike(normalized_query), 0),
        (name.ilike(normalized_query), 1),
        (bond_name.ilike(normalized_query), 1),
        else_=2,
    )
    matches = or_(
        models.Instruments.secid.ilike(pattern),
        models.Instruments.isin.ilike(pattern),
        ticker.ilike(pattern),
        figi.ilike(pattern),
        uid.ilike(pattern),
        name.ilike(pattern),
        bond_name.ilike(pattern),
    )

    async with get_session_factory()() as session:
        stmt = (
            select(models.Instruments)
            .where(
                models.Instruments.instrument_type == instrument_type,
                matches,
            )
            .order_by(match_order, models.Instruments.secid)
            .offset(offset)
            .limit(limit + 1)
        )
        records = (await session.scalars(stmt)).all()

    has_next = len(records) > limit
    results = []
    for record in records[:limit]:
        data = dict(record.extra_data or {})
        data.update(
            {
                "secid": record.secid,
                "isin": record.isin,
                "instrument_type": record.instrument_type,
                "currency": record.currency,
            }
        )
        results.append(data)
    return results, has_next


async def get_instrument_info(secid: str) -> dict[str, Any] | None:
    async with get_session_factory()() as session:
        instrument = await session.scalar(
            select(models.Instruments).where(models.Instruments.secid == secid)
        )
        if instrument is None:
            return None
        data = dict(instrument.extra_data or {})
        data.update(
            {
                "secid": instrument.secid,
                "isin": instrument.isin,
                "instrument_type": instrument.instrument_type,
                "currency": instrument.currency,
            }
        )
        return data


async def find_name_by_figi(figi: str) -> str | None:
    async with get_session_factory()() as session:
        stmt = select(models.Instruments.extra_data).where(
            models.Instruments.extra_data["figi"].astext == figi
        )
        data = await session.scalar(stmt)
        if not data:
            return None
        return data.get("name") or data.get("bond_name")


async def upload_user_portfolio(
    user_id: int,
    secid: str,
    avg_price: Decimal | float,
    quantity: int,
) -> bool:
    identifier = secid.strip().upper()
    async with get_session_factory()() as session, session.begin():
        await ensure_user(session, user_id)
        instrument = await _find_instrument(session, identifier)
        if instrument is None or instrument.isin is None:
            return False

        stmt = pg_insert(models.UserPortfolio).values(
            user_id=user_id,
            isin=instrument.isin,
            paper_data=instrument.extra_data,
            avg_price=Decimal(str(avg_price)),
            quantity=quantity,
        )
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "isin"],
            set_={
                "paper_data": stmt.excluded.paper_data,
                "avg_price": stmt.excluded.avg_price,
                "quantity": stmt.excluded.quantity,
            },
        )
        await session.execute(upsert_stmt)
        return True


async def sync_user_portfolio(
    user_id: int, positions: list[dict[str, Any]]
) -> tuple[int, list[str]]:
    records_by_isin: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []

    async with get_session_factory()() as session, session.begin():
        await ensure_user(session, user_id)
        for position in positions:
            if not isinstance(position, dict):
                skipped.append("unknown")
                continue

            identifier = str(position.get("secid") or "").strip().upper()
            instrument = await _find_instrument(session, identifier)
            if not identifier or instrument is None or instrument.isin is None:
                skipped.append(identifier or "unknown")
                continue

            try:
                quantity = Decimal(str(position.get("quantity", 0)))
                avg_price = Decimal(str(position.get("avg_price", 0)))
            except (InvalidOperation, ValueError):
                skipped.append(identifier)
                continue

            if (
                not quantity.is_finite()
                or quantity != quantity.to_integral_value()
                or quantity <= 0
                or not avg_price.is_finite()
                or avg_price < 0
            ):
                skipped.append(identifier)
                continue

            record = records_by_isin.get(instrument.isin)
            if record is None:
                records_by_isin[instrument.isin] = {
                    "user_id": user_id,
                    "isin": instrument.isin,
                    "paper_data": instrument.extra_data,
                    "avg_price": avg_price,
                    "quantity": int(quantity),
                }
                continue

            previous_quantity = Decimal(record["quantity"])
            total_quantity = previous_quantity + quantity
            record["avg_price"] = (
                record["avg_price"] * previous_quantity + avg_price * quantity
            ) / total_quantity
            record["quantity"] = int(total_quantity)

        records = list(records_by_isin.values())
        if not positions:
            # An empty upstream response is not enough evidence to erase data.
            return 0, skipped

        if skipped:
            # Keep existing positions when the upstream response is partial.
            if records:
                insert_stmt = pg_insert(models.UserPortfolio).values(records)
                upsert_stmt = insert_stmt.on_conflict_do_update(
                    index_elements=["user_id", "isin"],
                    set_={
                        "paper_data": insert_stmt.excluded.paper_data,
                        "avg_price": insert_stmt.excluded.avg_price,
                        "quantity": insert_stmt.excluded.quantity,
                    },
                )
                await session.execute(upsert_stmt)
            return len(records), skipped

        await session.execute(
            delete(models.UserPortfolio).where(models.UserPortfolio.user_id == user_id)
        )
        if records:
            await session.execute(
                pg_insert(models.UserPortfolio).values(records)
            )

    return len(records), skipped


async def drop_isin_portfolio(user_id: int, secid: str) -> bool:
    identifier = secid.strip().upper()
    async with get_session_factory()() as session, session.begin():
        instrument = await _find_instrument(session, identifier)
        stored_identifiers = {identifier}
        if instrument is not None:
            stored_identifiers.add(instrument.secid)
            if instrument.isin:
                stored_identifiers.add(instrument.isin)

        stmt = delete(models.UserPortfolio).where(
            models.UserPortfolio.user_id == user_id,
            models.UserPortfolio.isin.in_(stored_identifiers),
        )
        result = await session.execute(stmt)
        return result.rowcount > 0


async def drop_user_portfolio(user_id: int) -> bool:
    async with get_session_factory()() as session, session.begin():
        stmt = delete(models.UserPortfolio).where(
            models.UserPortfolio.user_id == user_id
        )
        result = await session.execute(stmt)
        return result.rowcount > 0


async def delete_user(user_id: int) -> bool:
    async with get_session_factory()() as session, session.begin():
        result = await session.execute(
            delete(models.AppUser).where(models.AppUser.user_id == user_id)
        )
        return result.rowcount > 0


async def get_user_portfolio(user_id: int) -> list[dict[str, Any]]:
    async with get_session_factory()() as session:
        stmt = (
            select(models.UserPortfolio, models.Instruments)
            .join(
                models.Instruments,
                models.Instruments.isin == models.UserPortfolio.isin,
            )
            .where(models.UserPortfolio.user_id == user_id)
            .order_by(models.UserPortfolio.id)
        )
        records = (await session.execute(stmt)).all()

        portfolio = []
        for record, instrument in records:
            paper = dict(record.paper_data or {})
            # The portfolio row is a snapshot; instrument data is refreshed
            # in the catalog while the bot is running.
            paper.update(instrument.extra_data or {})
            paper.update(
                {
                    "secid": instrument.secid,
                    "isin": record.isin,
                    "instrument_type": instrument.instrument_type,
                    "currency": instrument.currency,
                    "avg_price": record.avg_price,
                    "quantity": record.quantity,
                }
            )
            portfolio.append(paper)

        return portfolio


def _valor_asset_to_dict(record: models.ValorAssetRisk) -> dict[str, Any]:
    return {
        "id": record.id,
        "asset_type": record.asset_type,
        "identifier": record.identifier,
        "issuer": record.issuer,
        "sector": record.sector,
        "company_type": record.company_type,
        "bond_kind": record.bond_kind,
        "currency": record.currency,
        "coupon_type": record.coupon_type,
        "inflation_risk": record.inflation_risk,
        "geopolitical_risk": record.geopolitical_risk,
        "domestic_political_risk": record.domestic_political_risk,
        "debt_risk": record.debt_risk,
        "currency_risk": record.currency_risk,
        "minority_shareholder_risk": record.minority_shareholder_risk,
        "source_sheet": record.source_sheet,
    }


async def list_valor_assets(
    *,
    asset_type: str | None = None,
    query: str | None = None,
    limit: int = 8,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], bool]:
    """List or search the curated Valor catalog with stable pagination."""
    normalized_type = asset_type.strip().lower() if asset_type else None
    if normalized_type not in {None, "share", "bond"}:
        return [], False

    limit = max(1, min(limit, 20))
    offset = max(0, offset)
    normalized_query = (query or "").strip()
    stmt = select(models.ValorAssetRisk)
    if normalized_type:
        stmt = stmt.where(models.ValorAssetRisk.asset_type == normalized_type)

    if normalized_query:
        pattern = f"%{normalized_query}%"
        stmt = stmt.where(
            or_(
                models.ValorAssetRisk.identifier.ilike(pattern),
                models.ValorAssetRisk.issuer.ilike(pattern),
                models.ValorAssetRisk.sector.ilike(pattern),
                models.ValorAssetRisk.company_type.ilike(pattern),
                models.ValorAssetRisk.bond_kind.ilike(pattern),
                models.ValorAssetRisk.coupon_type.ilike(pattern),
            )
        )
        match_order = case(
            (models.ValorAssetRisk.identifier.ilike(normalized_query), 0),
            (models.ValorAssetRisk.issuer.ilike(normalized_query), 1),
            else_=2,
        )
        stmt = stmt.order_by(match_order)

    stmt = stmt.order_by(
        models.ValorAssetRisk.asset_type,
        models.ValorAssetRisk.identifier,
    ).offset(offset).limit(limit + 1)
    async with get_session_factory()() as session:
        records = (await session.scalars(stmt)).all()

    has_next = len(records) > limit
    return [_valor_asset_to_dict(record) for record in records[:limit]], has_next


async def get_valor_asset(asset_id: int) -> dict[str, Any] | None:
    async with get_session_factory()() as session:
        record = await session.get(models.ValorAssetRisk, asset_id)
    return _valor_asset_to_dict(record) if record is not None else None


async def get_valor_risk_profiles(
    keys: Iterable[tuple[str, str]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Return expert risk profiles keyed by ``(asset_type, ticker_or_isin)``."""
    normalized_keys = {
        (asset_type.strip().lower(), identifier.strip().upper())
        for asset_type, identifier in keys
        if asset_type and identifier
    }
    if not normalized_keys:
        return {}

    asset_types = {asset_type for asset_type, _ in normalized_keys}
    identifiers = {identifier for _, identifier in normalized_keys}
    async with get_session_factory()() as session:
        stmt = select(models.ValorAssetRisk).where(
            models.ValorAssetRisk.asset_type.in_(asset_types),
            models.ValorAssetRisk.identifier.in_(identifiers),
        )
        records = (await session.scalars(stmt)).all()

    result: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        key = (record.asset_type, record.identifier)
        if key not in normalized_keys:
            continue
        result[key] = _valor_asset_to_dict(record)
    return result


async def upload_bonds_data() -> None:
    _, bonds = await parsing_instruments()
    insert_data = [
        {"isin": data["isin"], "extra_data": data}
        for data in bonds.values()
        if data.get("isin")
    ]
    if not insert_data:
        return

    async with get_session_factory()() as session, session.begin():
        stmt = pg_insert(models.Bonds).values(insert_data)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["isin"],
            set_={"extra_data": stmt.excluded.extra_data},
        )
        await session.execute(upsert_stmt)


async def upsert_instrument_catalog(catalog: list[dict[str, Any]]) -> int:
    """Persist normalized catalog rows and make them immediately searchable."""
    insert_data = [
        {
            "secid": data["secid"],
            "isin": data.get("isin"),
            "instrument_type": data.get("instrument_type", "share"),
            "currency": data.get("currency") or "RUB",
            "extra_data": data,
        }
        for data in catalog
    ]

    if not insert_data:
        return 0

    async with get_session_factory()() as session, session.begin():
        isins = [row["isin"] for row in insert_data if row["isin"]]
        if isins:
            existing_pairs = (
                await session.execute(
                    select(
                        models.Instruments.isin,
                        models.Instruments.secid,
                        models.Instruments.extra_data,
                    ).where(models.Instruments.isin.in_(isins))
                )
            ).all()
            existing_by_isin = {
                isin: (secid, extra_data or {})
                for isin, secid, extra_data in existing_pairs
            }
            for row in insert_data:
                existing = existing_by_isin.get(row["isin"])
                if existing:
                    existing_secid, existing_data = existing
                    row["secid"] = existing_secid
                    row["extra_data"]["secid"] = existing_secid
                    # A MOEX-only fallback refresh must not erase identifiers
                    # already resolved through T-Invest. They are required for
                    # fast live-price requests from paper cards.
                    for key in (
                        "uid",
                        "figi",
                        "ticker",
                        "class_code",
                        "exchange",
                        "real_exchange",
                        "api_trade_available",
                    ):
                        if not row["extra_data"].get(key) and existing_data.get(key):
                            row["extra_data"][key] = existing_data[key]

        stmt = pg_insert(models.Instruments).values(insert_data)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["secid"],
            set_={
                "isin": stmt.excluded.isin,
                "type": stmt.excluded["type"],
                "currency": stmt.excluded.currency,
                "extra_data": stmt.excluded.extra_data,
                "updated_at": func.now(),
            },
        )
        await session.execute(upsert_stmt)

    return len(insert_data)


async def upload_bonds_shares(t_invest_token: str | None = None) -> int:
    catalog = await load_unified_catalog(t_invest_token)
    return await upsert_instrument_catalog(catalog)


async def instrument_catalog_has_data() -> bool:
    """Return whether a previously downloaded catalog can serve searches."""
    async with get_session_factory()() as session:
        secid = await session.scalar(select(models.Instruments.secid).limit(1))
        return secid is not None


async def get_bonds_info(isin: str) -> dict[str, Any] | None:
    async with get_session_factory()() as session:
        instrument = await _find_instrument(session, isin.strip().upper())
        if instrument is None or instrument.instrument_type != "bond":
            return None
        data = dict(instrument.extra_data or {})
        data.update(
            {
                "secid": instrument.secid,
                "isin": instrument.isin,
                "instrument_type": instrument.instrument_type,
                "currency": instrument.currency,
            }
        )
        return data


async def get_share_etf_info(isin_secid: str) -> dict[str, Any] | None:
    async with get_session_factory()() as session:
        instrument = await _find_instrument(session, isin_secid.strip().upper())
        if instrument is None or instrument.instrument_type != "share":
            return None
        data = dict(instrument.extra_data or {})
        data.update(
            {
                "secid": instrument.secid,
                "isin": instrument.isin,
                "instrument_type": instrument.instrument_type,
                "currency": instrument.currency,
            }
        )
        return data
