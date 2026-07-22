import aiohttp

async def parsing_bonds():
    url = "https://iss.moex.com/iss/engines/stock/markets/bonds/boards/TQCB/securities.json"
    params = {
        "iss.only": "securities",
        "iss.meta": "off"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, ssl=False) as response:
            payload = await response.json()

    raw_columns = payload['securities']['columns']
    raw_data = payload['securities']['data']

    cols = {name: idx for idx, name in enumerate(raw_columns)}

    bonds_catalog = {}

    for bond in raw_data:
        isin = bond[cols['ISIN']] or bond[cols['SECID']]
        prev_price = bond[cols['PREVPRICE']]
        
        price_val = (prev_price * 10) if prev_price is not None else None

        bonds_catalog[isin] = {
            # FACEUNIT валюта номинала
            # OFFERDATE
            # BUYBACKPRICE
            # BUYBACKDATE
            # ISSUESIZE
            "bond_name": bond[cols['SHORTNAME']],
            "coupon_value": bond[cols['COUPONVALUE']],
            "next_coupon": bond[cols['NEXTCOUPON']],
            "accruedint": bond[cols['ACCRUEDINT']],
            "prevprice": price_val,
            "face_value": bond[cols['FACEVALUE']],
            "matdate": bond[cols['MATDATE']],
            "coupon_period": bond[cols['COUPONPERIOD']],
            "coupon_prercent": bond[cols["COUPONPERCENT"]]
        }

    return bonds_catalog