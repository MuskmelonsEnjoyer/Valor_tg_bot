import asyncio

import aiohttp


async def _get_json(
    session: aiohttp.ClientSession, url: str, params: dict[str, str]
) -> dict:
    for attempt in range(3):
        try:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                payload = await response.json()
            if not isinstance(payload, dict):
                raise ValueError("MOEX returned an unexpected response")
            return payload
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt == 2:
                raise
            await asyncio.sleep(2**attempt)


def _section(payload: dict, name: str) -> tuple[list, list]:
    section = payload.get(name)
    if not isinstance(section, dict):
        raise ValueError(f"MOEX response has no '{name}' section")
    columns = section.get("columns")
    data = section.get("data")
    if not isinstance(columns, list) or not isinstance(data, list):
        raise ValueError(f"MOEX section '{name}' has an unexpected format")
    return columns, data


def _value(row: list, columns: dict[str, int], name: str):
    index = columns.get(name)
    return row[index] if index is not None and index < len(row) else None


def _column_map(columns: list[str]) -> dict[str, int]:
    return {name.upper(): index for index, name in enumerate(columns)}


def _first_price(row: list, columns: dict[str, int], fields: tuple[str, ...]):
    for field in fields:
        value = _value(row, columns, field)
        if value is not None:
            return value, field
    return None, None


def _price_source(field: str | None) -> str | None:
    if field == "LAST":
        return "trade"
    if field == "PREVPRICE":
        return "previous_close"
    if field in {"PREVWAPRICE", "PREVLEGALCLOSEPRICE"}:
        return "previous_reference"
    if field in {"QUOTE_MIDPOINT", "BID", "OFFER"}:
        return "quote"
    if field is not None:
        return "market_reference"
    return None


def _market_timestamp(row: list, columns: dict[str, int]):
    return _value(row, columns, "SYSTIME") or _value(row, columns, "TIME")


def _quote_fallback(row: list, columns: dict[str, int]):
    bid = _value(row, columns, "BID")
    offer = _value(row, columns, "OFFER")
    if bid is not None and offer is not None:
        return (bid + offer) / 2, "QUOTE_MIDPOINT"
    if bid is not None:
        return bid, "BID"
    if offer is not None:
        return offer, "OFFER"
    return None, None


def _set_share_price(data: dict, market_row: list, columns: dict[str, int]) -> None:
    price, source = _first_price(
        market_row,
        columns,
        (
            "LAST",
            "LCURRENTPRICE",
            "MARKETPRICE2",
            "MARKETPRICE",
            "CLOSEPRICE",
            "WAPRICE",
        ),
    )
    if price is None:
        price = data.get("prev_price")
        source = (
            data.get("prev_price_field") or "PREVPRICE"
            if price is not None
            else None
        )
    if price is None:
        price, source = _quote_fallback(market_row, columns)

    data["last"] = price
    data["last_price"] = price
    data["price_source"] = _price_source(source)
    data["price_field"] = source
    data["price_date"] = (
        _market_timestamp(market_row, columns)
        if source not in (None, "PREVPRICE", "PREVWAPRICE", "PREVLEGALCLOSEPRICE")
        else data.get("prev_date")
    )
    data["price_delay_minutes"] = (
        15
        if source not in (None, "PREVPRICE", "PREVWAPRICE", "PREVLEGALCLOSEPRICE")
        else 0
    )


def _set_bond_price(
    data: dict, market_row: list, columns: dict[str, int]
) -> None:
    percent, source = _first_price(
        market_row,
        columns,
        (
            "LAST",
            "LCURRENTPRICE",
            "MARKETPRICE2",
            "MARKETPRICE",
            "CLOSEPRICE",
            "WAPRICE",
        ),
    )
    if percent is None:
        percent = data.get("prev_price_percent")
        source = (
            data.get("prev_price_field") or "PREVPRICE"
            if percent is not None
            else None
        )
    if percent is None:
        percent, source = _quote_fallback(market_row, columns)

    face_value = data.get("face_value")
    price = percent * face_value / 100 if percent is not None and face_value else None
    data["last_price"] = price
    data["price_percent"] = percent
    data["price_source"] = _price_source(source)
    data["price_field"] = source
    data["price_date"] = (
        _market_timestamp(market_row, columns)
        if source not in (None, "PREVPRICE", "PREVWAPRICE", "PREVLEGALCLOSEPRICE")
        else data.get("prev_date")
    )
    data["price_delay_minutes"] = (
        15
        if source not in (None, "PREVPRICE", "PREVWAPRICE", "PREVLEGALCLOSEPRICE")
        else 0
    )


async def parsing_bonds(session: aiohttp.ClientSession) -> dict:
    url = "https://iss.moex.com/iss/engines/stock/markets/bonds/securities.json"
    params = {
        "iss.only": "securities,marketdata,marketdata_yields",
        "iss.meta": "off",
        "limit": "10000",
    }

    payload = await _get_json(session, url, params)

    sec_columns, sec_data = _section(payload, "securities")
    md_columns, md_data = _section(payload, "marketdata")
    yield_columns, yield_data = _section(payload, "marketdata_yields")
    cols_sec = _column_map(sec_columns)
    cols_md = _column_map(md_columns)
    cols_yields = _column_map(yield_columns)

    target_boards = {"TQCB", "TQOB"}
    bonds_catalog = {}

    for bond in sec_data:
        boardid = bond[cols_sec["BOARDID"]]
        if boardid not in target_boards:
            continue

        secid = bond[cols_sec["SECID"]]
        bonds_catalog[secid] = {
            "boardid": boardid,
            "faceunit": bond[cols_sec["FACEUNIT"]],
            "bond_name": bond[cols_sec["SHORTNAME"]],
            "coupon_value": bond[cols_sec["COUPONVALUE"]],
            "next_coupon": bond[cols_sec["NEXTCOUPON"]],
            "accruedint": bond[cols_sec["ACCRUEDINT"]],
            "face_value": bond[cols_sec["FACEVALUE"]],
            "matdate": bond[cols_sec["MATDATE"]],
            "currency": bond[cols_sec["CURRENCYID"]],
            "coupon_period": bond[cols_sec["COUPONPERIOD"]],
            "coupon_percent": bond[cols_sec["COUPONPERCENT"]],
            "isin": bond[cols_sec["ISIN"]],
            "prev_price_percent": _value(bond, cols_sec, "PREVPRICE")
            or _value(bond, cols_sec, "PREVWAPRICE")
            or _value(bond, cols_sec, "PREVLEGALCLOSEPRICE"),
            "prev_price_field": (
                "PREVPRICE"
                if _value(bond, cols_sec, "PREVPRICE") is not None
                else "PREVWAPRICE"
                if _value(bond, cols_sec, "PREVWAPRICE") is not None
                else "PREVLEGALCLOSEPRICE"
                if _value(bond, cols_sec, "PREVLEGALCLOSEPRICE") is not None
                else None
            ),
            "prev_date": _value(bond, cols_sec, "PREVDATE"),
            "instrument_type": "bond",
        }

    for md in md_data:
        secid = md[cols_md["SECID"]]
        if secid in bonds_catalog:
            data = bonds_catalog[secid]
            _set_bond_price(data, md, cols_md)
            face_value = data["face_value"]
            open_percent = _value(md, cols_md, "OPEN")
            data["open"] = (
                open_percent * face_value / 100
                if open_percent is not None and face_value is not None
                else None
            )

    for yld in yield_data:
        secid = yld[cols_yields["SECID"]]
        if secid in bonds_catalog:
            bonds_catalog[secid]["effectiveyield"] = yld[cols_yields["EFFECTIVEYIELD"]]
            bonds_catalog[secid]["duration"] = yld[cols_yields["DURATION"]]

    return bonds_catalog


async def parsing_shares(session: aiohttp.ClientSession):
    url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"

    params = {"iss.only": "securities,marketdata",
                  "iss.meta": "off",
                  "limit": "10000",
                }

    payload = await _get_json(session, url, params)

    sec_columns, sec_data = _section(payload, "securities")
    md_columns, md_data = _section(payload, "marketdata")

    cols_sec = _column_map(sec_columns)
    cols_md = _column_map(md_columns)

    shares_catalog_sec = {}
    shares_catalog_md = {}

    for share in sec_data:
        secid = share[cols_sec['SECID']]

        shares_catalog_sec[secid] = {
            'name': share[cols_sec['SHORTNAME']],
            'isin': share[cols_sec['ISIN']],
            'currency': share[cols_sec['CURRENCYID']],
            'prev_price': _value(share, cols_sec, 'PREVPRICE')
            or _value(share, cols_sec, 'PREVWAPRICE')
            or _value(share, cols_sec, 'PREVLEGALCLOSEPRICE'),
            'prev_price_field': (
                'PREVPRICE'
                if _value(share, cols_sec, 'PREVPRICE') is not None
                else 'PREVWAPRICE'
                if _value(share, cols_sec, 'PREVWAPRICE') is not None
                else 'PREVLEGALCLOSEPRICE'
                if _value(share, cols_sec, 'PREVLEGALCLOSEPRICE') is not None
                else None
            ),
            'prev_date': _value(share, cols_sec, 'PREVDATE'),
            'instrument_type': 'share',
        }

    for share in md_data:
        secid = share[cols_md['SECID']]

        shares_catalog_md[secid] = {"open": _value(share, cols_md, "OPEN")}
        _set_share_price(shares_catalog_md[secid], share, cols_md)

    all_secids = shares_catalog_sec.keys() | shares_catalog_md.keys()
    shares_catalog = {
        secid: {
            **shares_catalog_sec.get(secid, {}),
            **shares_catalog_md.get(secid, {}),
        }
        for secid in all_secids
    }

    for data in shares_catalog.values():
        if data.get("last") is None and data.get("prev_price") is not None:
            data["last"] = data["prev_price"]
            data["last_price"] = data["prev_price"]
            data["price_source"] = _price_source(data.get("prev_price_field"))
            data["price_field"] = data.get("prev_price_field")
            data["price_date"] = data.get("prev_date")
            data["price_delay_minutes"] = 0
        else:
            data.setdefault("price_date", data.get("prev_date"))
            data.setdefault("price_delay_minutes", 15)

    return shares_catalog


async def parsing_instruments():
    timeout = aiohttp.ClientTimeout(total=90, connect=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        shares, bonds = await asyncio.gather(
            parsing_shares(session), parsing_bonds(session)
        )
    return shares, bonds
