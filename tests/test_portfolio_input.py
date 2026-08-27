import unittest
from decimal import Decimal

from app.bot.handlers import _parse_position_input


class PortfolioInputTests(unittest.TestCase):
    def test_parses_price_and_quantity(self):
        self.assertEqual(
            _parse_position_input("985,50 10"), (Decimal("985.50"), 10)
        )

    def test_rejects_invalid_position(self):
        for value in ("985.50", "0 10", "985.50 0", "price 10"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    _parse_position_input(value)
