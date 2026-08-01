import asyncio

import aiohttp


async def parsing_bonds(session: aiohttp.ClientSession) -> dict:
    url = "https://iss.moex.com/iss/engines/stock/markets/bonds/securities.json"
    params = {
        "iss.only": "securities,marketdata,marketdata_yields",
        "iss.meta": "off",
        "limit": "10000",
    }

    async with session.get(url, params=params, ssl=False) as response:
        payload = await response.json()

    cols_sec = {name: idx for idx, name in enumerate(payload["securities"]["columns"])}
    cols_md = {name: idx for idx, name in enumerate(payload["marketdata"]["columns"])}
    cols_yields = {name: idx for idx, name in enumerate(payload["marketdata_yields"]["columns"])}

    target_boards = {"TQCB", "TQOB"}
    bonds_catalog = {}

    for bond in payload["securities"]["data"]:
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
            "instrument_type": "bond",
        }

    for md in payload["marketdata"]["data"]:
        secid = md[cols_md["SECID"]]
        if secid in bonds_catalog:
            last_percent = md[cols_md["LAST"]]
            open_price = md[cols_md["OPEN"]]
            face_value = bonds_catalog[secid]["face_value"]
            
            if last_percent is not None and face_value is not None:
                actual_price = (last_percent / 100) * face_value
            else:
                actual_price = None
                
            bonds_catalog[secid]["last_price"] = actual_price
            bonds_catalog[secid]["open"] = open_price

    for yld in payload["marketdata_yields"]["data"]:
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

    async with session.get(url, params = params, ssl=False) as response:
        payload = await response.json()

    sec_columns = payload['securities']['columns']
    sec_data = payload['securities']['data']

    md_columns = payload['marketdata']['columns']
    md_data = payload['marketdata']['data']

    cols_sec = {name: idx for idx, name in enumerate(sec_columns)}
    cols_md = {name: idx for idx, name in enumerate(md_columns)}

    shares_catalog_sec = {}
    shares_catalog_md = {}

    for share in sec_data:
        secid = share[cols_sec['SECID']]

        shares_catalog_sec[secid] = {
            'name': share[cols_sec['SHORTNAME']],
            'isin': share[cols_sec['ISIN']],
            'currency': share[cols_sec['CURRENCYID']],
            'instrument_type': 'share',
        }

    for share in md_data:
        secid = share[cols_md['SECID']]

        shares_catalog_md[secid] = {
        "last": share[cols_md['LAST']],
        "open": share[cols_md["OPEN"]],
        }

    all_secids = shares_catalog_sec.keys() | shares_catalog_md.keys()
    shares_catalog = {
        secid: {
            **shares_catalog_sec.get(secid, {}),
            **shares_catalog_md.get(secid, {}),
        }
        for secid in all_secids
    }

    return shares_catalog


async def parsing_instruments():
    async with aiohttp.ClientSession() as session:
        shares, bonds = await asyncio.gather(
            parsing_shares(session), parsing_bonds(session)
        )
    return shares, bonds