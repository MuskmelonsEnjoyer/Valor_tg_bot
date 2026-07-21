from t_tech.invest import AsyncClient, InstrumentStatus, InstrumentIdType
from t_tech.invest.utils import quotation_to_decimal


async def get_all_instruments_list(token: str) -> list[dict]:
    async with AsyncClient(token) as client:
        shares = (
            await client.instruments.shares(
                instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
            )
        ).instruments
        bonds = (
            await client.instruments.bonds(
                instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
            )
        ).instruments
        etfs = (
            await client.instruments.etfs(
                instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
            )
        ).instruments

    result_list = []

    def pack_data(items, instrument_type):
        for item in items:
            result_list.append(
                {
                    "instrument_name": item.name,
                    "instrument_uid": item.uid,
                    "instrument_ticker": item.ticker,
                    "instrument_source_id": instrument_type,
                    "instrument_figi": item.figi,
                    "instrument_isin": item.isin,
                    "instrument_currency": item.currency,
                    "instrument_class_code": item.class_code,
                    "instrument_source_id": "T-invest",
                }
            )

    pack_data(shares, "share")
    pack_data(bonds, "bond")
    pack_data(etfs, "etf")

    return result_list


async def find_current_price(figi: str, token: str) -> float | None:
    async with AsyncClient(token) as client:
        try:
            instrument_response = await client.instruments.get_instrument_by(
                id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, id=figi
            )
            instrument_uid = instrument_response.instrument.uid
            price_response = await client.market_data.get_last_prices(
                instrument_id=[instrument_uid]
            )

            if price_response.last_prices:
                price_obj = price_response.last_prices[0].price
                current_price = quotation_to_decimal(price_obj)
                if instrument_response.instrument.instrument_type == "bond":
                    real_price = current_price * 10
                    return float(real_price)
                return float(current_price)
            else:
                print("Цена не найдена (нет данных о торгах)")
                return None

        except Exception as e:
            print(f"Ошибка при запросе: {e}")
            return None
