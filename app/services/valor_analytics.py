from collections import defaultdict
from html import escape
from math import isfinite
from typing import Any


RISK_FACTORS = (
    ("inflation_risk", "Инфляция"),
    ("geopolitical_risk", "Геополитика/страна"),
    ("domestic_political_risk", "Внутренняя политика"),
    ("debt_risk", "Долговая нагрузка"),
    ("currency_risk", "Девальвация рубля"),
    ("minority_shareholder_risk", "Отношение к минорам"),
)


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and number > 0 else None


def _risk_level(score: float) -> tuple[str, str]:
    if score < 1.5:
        return "🟢", "крайне низкий"
    if score < 2.5:
        return "🟢", "низкий"
    if score < 3.5:
        return "🟡", "умеренный"
    if score < 4.5:
        return "🟠", "повышенный"
    if score < 5.5:
        return "🔴", "высокий"
    return "🔴", "крайне высокий"


def format_valor_asset_profile(asset: dict[str, Any]) -> str:
    asset_type = asset.get("asset_type")
    type_name = "Акция" if asset_type == "share" else "Облигация"
    lines = [
        f'📌 <b>{escape(str(asset.get("issuer") or "Без названия"))}</b>',
        f'• <b>{"Тикер" if asset_type == "share" else "ISIN"}:</b> '
        f'<code>{escape(str(asset.get("identifier") or "Н/Д"))}</code>',
        f"• <b>Тип бумаги:</b> {type_name}",
    ]

    if asset_type == "share":
        if asset.get("sector"):
            lines.append(f'• <b>Сектор:</b> {escape(str(asset["sector"]))}')
        if asset.get("company_type"):
            lines.append(
                f'• <b>Тип компании:</b> {escape(str(asset["company_type"]))}'
            )
    else:
        if asset.get("bond_kind"):
            lines.append(f'• <b>Категория:</b> {escape(str(asset["bond_kind"]))}')
        if asset.get("currency"):
            lines.append(f'• <b>Валюта:</b> {escape(str(asset["currency"]))}')
        if asset.get("coupon_type"):
            lines.append(f'• <b>Тип купона:</b> {escape(str(asset["coupon_type"]))}')

    lines.extend(["", "<b>Риски Valor</b>", "Шкала: 1 — минимум, 6 — максимум."])
    for key, label in RISK_FACTORS:
        value = asset.get(key)
        if value is None:
            lines.append(f"⚪ {label}: нет данных")
            continue
        score = float(value)
        marker, level = _risk_level(score)
        lines.append(f"{marker} {label}: <b>{score:g}/6</b> ({level})")

    lines.extend(["", "<i>Экспертная оценка, не инвестиционная рекомендация.</i>"])
    return "\n".join(lines)


def calculate_portfolio_risks(
    positions: list[dict[str, Any]],
    profiles: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    """Calculate Excel-compatible weighted scores without mixing currencies."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped_without_value: list[str] = []

    for position in positions:
        market_value = _positive_number(position.get("market_value"))
        identifier = str(position.get("identifier") or "").strip().upper()
        asset_type = str(position.get("asset_type") or "").strip().lower()
        if market_value is None or not identifier or asset_type not in {"share", "bond"}:
            skipped_without_value.append(identifier or "неизвестная позиция")
            continue

        currency = str(position.get("currency") or "RUB").strip().upper()
        if currency == "SUR":
            currency = "RUB"
        grouped[currency].append(
            {
                **position,
                "asset_type": asset_type,
                "identifier": identifier,
                "market_value": market_value,
            }
        )

    group_reports = []
    for currency in sorted(grouped, key=lambda item: (item != "RUB", item)):
        currency_positions = grouped[currency]
        total_value = sum(item["market_value"] for item in currency_positions)
        matched = [
            item
            for item in currency_positions
            if (item["asset_type"], item["identifier"]) in profiles
        ]
        matched_value = sum(item["market_value"] for item in matched)
        factors = []

        for key, label in RISK_FACTORS:
            rated = []
            for item in matched:
                score = profiles[(item["asset_type"], item["identifier"])].get(key)
                if score is not None:
                    rated.append((item, float(score)))
            covered_value = sum(item["market_value"] for item, _ in rated)
            score = (
                sum(item["market_value"] * rating for item, rating in rated)
                / covered_value
                if covered_value
                else None
            )
            marker, level = _risk_level(score) if score is not None else ("⚪", "нет данных")
            factors.append(
                {
                    "key": key,
                    "label": label,
                    "score": score,
                    "percent_of_max": score / 6 * 100 if score is not None else None,
                    "coverage": covered_value / total_value if total_value else 0.0,
                    "marker": marker,
                    "level": level,
                }
            )

        group_reports.append(
            {
                "currency": currency,
                "total_value": total_value,
                "position_count": len(currency_positions),
                "matched_count": len(matched),
                "coverage": matched_value / total_value if total_value else 0.0,
                "estimated_count": sum(
                    bool(item.get("uses_average_price")) for item in currency_positions
                ),
                "unmatched": [
                    item["identifier"]
                    for item in currency_positions
                    if (item["asset_type"], item["identifier"]) not in profiles
                ],
                "factors": factors,
            }
        )

    return {
        "groups": group_reports,
        "skipped_without_value": skipped_without_value,
        "position_count": sum(len(items) for items in grouped.values()),
    }


def format_portfolio_risks(report: dict[str, Any]) -> str:
    groups = report.get("groups") or []
    if not groups:
        return (
            "📊 <b>Подборка Valor</b>\n\n"
            "Не удалось определить стоимость позиций для расчёта. "
            "Проверьте количество и цену активов в портфеле."
        )

    lines = [
        "📊 <b>Подборка Valor — риск-профиль портфеля</b>",
        "Оценка: 1 — минимальный риск, 6 — максимальный.",
    ]
    multiple_currencies = len(groups) > 1

    for group in groups:
        lines.append("")
        currency = escape(group["currency"])
        total = f'{group["total_value"]:,.2f}'.replace(",", " ")
        heading = f"<b>{currency}: {total}</b>" if multiple_currencies else f"<b>Портфель: {total} {currency}</b>"
        lines.append(heading)
        lines.append(
            "Покрытие подборкой: "
            f'<b>{group["coverage"]:.0%}</b> '
            f'({group["matched_count"]} из {group["position_count"]} позиций)'
        )

        for factor in group["factors"]:
            if factor["score"] is None:
                lines.append(f'⚪ {factor["label"]}: нет данных')
                continue
            coverage_note = (
                f' · покрытие {factor["coverage"]:.0%}'
                if factor["coverage"] < 0.995
                else ""
            )
            lines.append(
                f'{factor["marker"]} {factor["label"]}: '
                f'<b>{factor["score"]:.1f}/6</b> '
                f'({factor["percent_of_max"]:.0f}%, {factor["level"]})'
                f"{coverage_note}"
            )

        if group["unmatched"]:
            identifiers = ", ".join(escape(item) for item in group["unmatched"][:8])
            suffix = "…" if len(group["unmatched"]) > 8 else ""
            lines.append(f"Нет оценок Valor: {identifiers}{suffix}")
        if group["estimated_count"]:
            lines.append(
                f'Средняя цена покупки использована для {group["estimated_count"]} '
                "поз. без текущей цены."
            )

    skipped = report.get("skipped_without_value") or []
    if skipped:
        identifiers = ", ".join(escape(item) for item in skipped[:8])
        suffix = "…" if len(skipped) > 8 else ""
        lines.extend(["", f"Без цены/количества: {identifiers}{suffix}"])

    lines.extend(
        [
            "",
            "Анализ портфеля проведён по методике Valor. Оценка риска взвешивается по доле позиции. "
            "Разные валюты считаются отдельно.",
            "<i>Экспертная оценка, не инвестиционная рекомендация.</i>",
        ]
    )
    return "\n".join(lines)
