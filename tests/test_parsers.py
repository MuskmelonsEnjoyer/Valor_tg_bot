import unittest

from app.services.api_moex import _section, _set_bond_price, _set_share_price
from app.services.files import find_quantity


class MoexParserTests(unittest.TestCase):
    def test_extracts_valid_section(self):
        columns, data = _section(
            {"securities": {"columns": ["SECID"], "data": [["SBER"]]}},
            "securities",
        )
        self.assertEqual(columns, ["SECID"])
        self.assertEqual(data, [["SBER"]])

    def test_rejects_missing_section(self):
        with self.assertRaisesRegex(ValueError, "securities"):
            _section({}, "securities")

    def test_share_uses_previous_price_when_no_trade_exists(self):
        data = {"prev_price": 101.25, "prev_date": "2026-08-01"}
        columns = {"SECID": 0, "LAST": 1, "SYSTIME": 2}
        _set_share_price(data, ["SBER", None, None], columns)

        self.assertEqual(data["last"], 101.25)
        self.assertEqual(data["price_source"], "previous_close")
        self.assertEqual(data["price_date"], "2026-08-01")

    def test_bond_converts_previous_percent_price_to_money(self):
        data = {"face_value": 1000, "prev_price_percent": 98.5, "prev_date": "2026-08-01"}
        columns = {"SECID": 0, "LAST": 1, "SYSTIME": 2}
        _set_bond_price(data, ["SU000", None, None], columns)

        self.assertEqual(data["last_price"], 985.0)
        self.assertEqual(data["price_source"], "previous_close")

    def test_share_uses_quote_midpoint_as_last_available_price(self):
        data = {}
        columns = {"SECID": 0, "LAST": 1, "BID": 2, "OFFER": 3}
        _set_share_price(data, ["SBER", None, 100.0, 102.0], columns)

        self.assertEqual(data["last"], 101.0)
        self.assertEqual(data["price_source"], "quote")

    def test_uses_previous_reference_price_when_previous_trade_is_missing(self):
        data = {
            "prev_price": 99.5,
            "prev_price_field": "PREVWAPRICE",
            "prev_date": "2026-08-01",
        }
        columns = {"SECID": 0, "LAST": 1}
        _set_share_price(data, ["SBER", None], columns)

        self.assertEqual(data["price_source"], "previous_reference")


class ExcelParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_position(self):
        rows = [
            ("3.1 Движение по ценным бумагам инвестора",),
            ("Сбербанк", "SBER", "RU0009029540", 1, 2, 3, 4, 5, 10.0),
            ("3.2 Движение по производным финансовым инструментам",),
        ]

        positions = await find_quantity(rows)

        self.assertEqual(
            positions,
            [
                {
                    "name": "Сбербанк",
                    "ticker": "SBER",
                    "isin": "RU0009029540",
                    "quantity": 10.0,
                }
            ],
        )

    async def test_rejects_unknown_report_format(self):
        with self.assertRaisesRegex(ValueError, "разделы 3.1 и 3.2"):
            await find_quantity([("другой отчет",)])

    async def test_keeps_positional_columns_with_empty_cells(self):
        rows = [
            ("3.1 Движение по ценным бумагам инвестора",),
            ("Сбербанк", "SBER", "RU0009029540", None, 2, 3, 4, 5, 7),
            ("3.2 Движение по производным финансовым инструментам",),
        ]

        positions = await find_quantity(rows)

        self.assertEqual(positions[0]["quantity"], 7)
