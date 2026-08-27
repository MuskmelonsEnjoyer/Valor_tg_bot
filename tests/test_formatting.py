import unittest
from decimal import Decimal

from app.utils.formatting import clean_text, format_date, format_money


class FormattingTests(unittest.TestCase):
    def test_formats_money(self):
        self.assertEqual(format_money(Decimal("12345.678")), "12 345.68")

    def test_formats_optional_date(self):
        self.assertEqual(format_date("2026-11-25"), "25.11.2026")
        self.assertEqual(format_date(None), "Н/Д")

    def test_removes_unsupported_html(self):
        self.assertEqual(clean_text("<div><b>Важно</b><script>x</script></div>"), "<b>Важно</b>x")
