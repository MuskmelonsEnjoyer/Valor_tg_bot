"""Synchronize the Valor OFZ catalog from the main instruments table.

Run inside the bot container:

    python -m app.database.valor_ofz_sync --dry-run
    python -m app.database.valor_ofz_sync

The command is intentionally non-destructive: it inserts new OFZ rows and
updates existing ones, but never removes records from ``valor_asset_risks``.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime
from typing import Any

from app.core.settings import Settings
from app.database import models
from app.database.session import (
    configure_database,
    get_session_factory,
    on_shutdown,
)
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert


RISK_COLUMNS = (
    "inflation_risk",
    "geopolitical_risk",
    "domestic_political_risk",
    "debt_risk",
    "currency_risk",
    "minority_shareholder_risk",
)
AUTO_SOURCE = "Отбор бондов (ОФЗ авто)"
FIXED_COUPON_CNY_OFZ = frozenset(
    {
        "RU000A10DQA8",
        "RU000A10DQB6",
        "RU000A10FAK6",
    }
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _instrument_name(instrument: models.Instruments) -> str:
    data = instrument.extra_data or {}
    return (
        _normalized_text(data.get("bond_name"))
        or _normalized_text(data.get("name"))
        or instrument.secid
    )


def _looks_like_ofz(instrument: models.Instruments) -> bool:
    """Accept OFZ issues while excluding other securities from the TQOB board."""
    if instrument.instrument_type != "bond" or not instrument.isin:
        return False

    data = instrument.extra_data or {}
    boardid = _normalized_text(data.get("boardid")).upper()
    secid = _normalized_text(instrument.secid).upper()
    name = _instrument_name(instrument).upper()
    has_ofz_identity = secid.startswith("SU") or "ОФЗ" in name

    # MOEX marks government bonds with TQOB. T-Invest-only rows may not have
    # boardid, so the standard SU identifier plus an OFZ name is also accepted.
    return has_ofz_identity and (
        boardid == "TQOB" or (secid.startswith("SU") and "ОФЗ" in name)
    )


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _normalized_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _is_active(instrument: models.Instruments, *, today: date) -> bool:
    data = instrument.extra_data or {}
    maturity = _as_date(data.get("matdate") or data.get("maturity_date"))
    return maturity is None or maturity >= today


def _enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _normalized_text(value).lower() in {"1", "true", "yes", "on"}


def _coupon_type(
    instrument: models.Instruments, *, fallback: str | None = None
) -> str:
    """Classify the OFZ family using API flags and standard MOEX issue codes."""
    data = instrument.extra_data or {}
    isin = _normalized_text(instrument.isin).upper()
    secid = _normalized_text(instrument.secid).upper().split("@", 1)[0]
    name = _instrument_name(instrument).upper().replace(" ", "")

    if (
        _enabled(data.get("amortization_flag"))
        or secid.startswith("SU46")
        or "ОФЗ-АД" in name
    ):
        return "Аморт"
    if (
        _enabled(data.get("indexed_nominal_flag"))
        or secid.startswith("SU52")
        or "ОФЗ-ИН" in name
    ):
        return "Индекс"
    if (
        _enabled(data.get("floating_coupon_flag"))
        or secid.startswith(("SU24", "SU29"))
        or "ОФЗ-ПК" in name
    ):
        return "Перемен"
    if secid.startswith(("SU25", "SU26")) or "ОФЗ-ПД" in name:
        return "Фикс"
    if isin in FIXED_COUPON_CNY_OFZ:
        return "Фикс"
    return fallback or "Не определён"


def _risk_profile(record: models.ValorAssetRisk) -> tuple[int | None, ...]:
    return tuple(getattr(record, column) for column in RISK_COLUMNS)


def _build_row(
    instrument: models.Instruments,
    profile: tuple[int | None, ...],
    *,
    existing_coupon_type: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "asset_type": "bond",
        "identifier": _normalized_text(instrument.isin).upper(),
        "issuer": _instrument_name(instrument),
        "sector": None,
        "company_type": None,
        "bond_kind": "ОФЗ",
        "currency": _normalized_text(instrument.currency).upper() or "RUB",
        "coupon_type": _coupon_type(
            instrument, fallback=existing_coupon_type
        ),
        "source_sheet": AUTO_SOURCE,
    }
    row.update(dict(zip(RISK_COLUMNS, profile, strict=True)))
    return row


async def sync_valor_ofz(*, dry_run: bool = False) -> dict[str, Any]:
    """Upsert active OFZ instruments using the existing expert OFZ profile."""
    today = date.today()
    async with get_session_factory()() as session, session.begin():
        instruments = (
            await session.scalars(
                select(models.Instruments).where(
                    models.Instruments.instrument_type == "bond",
                    models.Instruments.isin.is_not(None),
                )
            )
        ).all()

        existing_ofz = (
            await session.scalars(
                select(models.ValorAssetRisk).where(
                    models.ValorAssetRisk.asset_type == "bond",
                    models.ValorAssetRisk.bond_kind == "ОФЗ",
                )
            )
        ).all()
        if not existing_ofz:
            raise RuntimeError(
                "В valor_asset_risks нет ОФЗ с экспертным рейтингом, "
                "который можно использовать как шаблон."
            )

        profiles = {_risk_profile(record) for record in existing_ofz}
        if len(profiles) != 1:
            raise RuntimeError(
                "У существующих ОФЗ разные рейтинги. Синхронизация остановлена, "
                "чтобы не выбрать профиль автоматически."
            )
        profile = profiles.pop()

        all_ofz = [item for item in instruments if _looks_like_ofz(item)]
        active_ofz = [item for item in all_ofz if _is_active(item, today=today)]
        active_identifiers = {
            _normalized_text(item.isin).upper() for item in active_ofz
        }
        existing_candidates = (
            (
                await session.scalars(
                    select(models.ValorAssetRisk).where(
                        models.ValorAssetRisk.asset_type == "bond",
                        models.ValorAssetRisk.identifier.in_(active_identifiers),
                    )
                )
            ).all()
            if active_identifiers
            else []
        )
        existing_by_isin = {
            record.identifier.upper(): record for record in existing_candidates
        }
        rows = [
            _build_row(
                instrument,
                profile,
                existing_coupon_type=(
                    existing_by_isin[instrument.isin.upper()].coupon_type
                    if instrument.isin.upper() in existing_by_isin
                    else None
                ),
            )
            for instrument in active_ofz
        ]

        existing_identifiers = set(existing_by_isin)
        created = sum(row["identifier"] not in existing_identifiers for row in rows)
        updated = len(rows) - created

        if rows and not dry_run:
            statement = pg_insert(models.ValorAssetRisk).values(rows)
            excluded = statement.excluded
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=["asset_type", "identifier"],
                    set_={
                        "issuer": excluded.issuer,
                        "sector": excluded.sector,
                        "company_type": excluded.company_type,
                        "bond_kind": excluded.bond_kind,
                        "currency": excluded.currency,
                        "coupon_type": excluded.coupon_type,
                        **{
                            column: getattr(excluded, column)
                            for column in RISK_COLUMNS
                        },
                        "source_sheet": excluded.source_sheet,
                        "updated_at": func.now(),
                    },
                )
            )

    return {
        "scanned_bonds": len(instruments),
        "found_ofz": len(all_ofz),
        "skipped_matured": len(all_ofz) - len(active_ofz),
        "active_ofz": len(active_ofz),
        "created": created,
        "updated": updated,
        "profile": profile,
        "sample": [
            (row["identifier"], row["issuer"], row["coupon_type"])
            for row in rows[:10]
        ],
        "dry_run": dry_run,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Обновить подборку Valor всеми активными ОФЗ из instruments."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать найденные данные без записи в valor_asset_risks.",
    )
    return parser


async def _main() -> int:
    args = _parser().parse_args()
    settings = Settings.from_env(require_telegram_token=False)
    configure_database(settings.database_url)
    try:
        result = await sync_valor_ofz(dry_run=args.dry_run)
    finally:
        await on_shutdown()

    mode = "ПРЕДПРОСМОТР" if result["dry_run"] else "ОБНОВЛЕНИЕ"
    print(f"[{mode}] Просканировано облигаций: {result['scanned_bonds']}")
    print(
        f"Найдено ОФЗ: {result['found_ofz']}; "
        f"активных: {result['active_ofz']}; "
        f"погашенных пропущено: {result['skipped_matured']}"
    )
    action = "Будет добавлено" if result["dry_run"] else "Добавлено"
    update_action = "будет обновлено" if result["dry_run"] else "обновлено"
    print(f"{action}: {result['created']}; {update_action}: {result['updated']}")
    print("Профиль риска ОФЗ:")
    for column, value in zip(RISK_COLUMNS, result["profile"], strict=True):
        print(f"  {column}: {value}")
    if result["sample"]:
        print("Пример строк:")
        for isin, name, coupon_type in result["sample"]:
            print(f"  {isin} | {name} | {coupon_type}")
    if not result["active_ofz"]:
        print("ОФЗ в instruments не найдены; база не изменена.")
        return 2
    if result["dry_run"]:
        print("Запись не выполнялась. Запустите без --dry-run для применения.")
    else:
        print("Синхронизация завершена. Старые строки не удалялись.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
