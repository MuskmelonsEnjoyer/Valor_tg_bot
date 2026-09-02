import unittest
from datetime import date
from types import SimpleNamespace

from app.database.valor_ofz_sync import (
    _build_row,
    _coupon_type,
    _is_active,
    _looks_like_ofz,
)


def instrument(
    secid: str,
    *,
    isin: str = "RU000A000000",
    name: str = "ОФЗ",
    boardid: str | None = "TQOB",
    **extra,
):
    return SimpleNamespace(
        secid=secid,
        isin=isin,
        instrument_type="bond",
        currency="RUB",
        extra_data={"bond_name": name, "boardid": boardid, **extra},
    )


class ValorOfzSyncTests(unittest.TestCase):
    def test_recognizes_ofz_but_not_a_corporate_bond(self):
        self.assertTrue(_looks_like_ofz(instrument("SU26248RMFS3")))
        self.assertFalse(
            _looks_like_ofz(
                instrument(
                    "RU000A10TEST",
                    name="Корпоративная облигация",
                    boardid="TQCB",
                )
            )
        )

    def test_t_invest_only_ofz_requires_both_su_code_and_name(self):
        self.assertTrue(
            _looks_like_ofz(
                instrument("SU26248RMFS3@TQOB", boardid=None, name="ОФЗ 26248")
            )
        )
        self.assertFalse(
            _looks_like_ofz(
                instrument("SU26248RMFS3@TQOB", boardid=None, name="Неизвестная")
            )
        )

    def test_coupon_family_is_derived_from_standard_issue_code(self):
        self.assertEqual(_coupon_type(instrument("SU26248RMFS3")), "Фикс")
        self.assertEqual(_coupon_type(instrument("SU25084RMFS3")), "Фикс")
        self.assertEqual(_coupon_type(instrument("SU29025RMFS1")), "Перемен")
        self.assertEqual(_coupon_type(instrument("SU24021RMFS6")), "Перемен")
        self.assertEqual(_coupon_type(instrument("SU46023RMFS6")), "Аморт")
        self.assertEqual(_coupon_type(instrument("SU52005RMFS4")), "Индекс")

    def test_api_flags_take_part_in_coupon_classification(self):
        floating = instrument("UNKNOWN", floating_coupon_flag=True)
        amortizing = instrument("UNKNOWN", amortization_flag=True)

        self.assertEqual(_coupon_type(floating), "Перемен")
        self.assertEqual(_coupon_type(amortizing), "Аморт")

    def test_matured_issue_is_not_active(self):
        old = instrument("SU26248RMFS3", matdate="2025-12-31")
        current = instrument("SU26249RMFS1", matdate="2026-09-02")

        self.assertFalse(_is_active(old, today=date(2026, 9, 2)))
        self.assertTrue(_is_active(current, today=date(2026, 9, 2)))

    def test_build_row_uses_name_isin_and_existing_profile(self):
        item = instrument(
            "SU26248RMFS3",
            isin="RU000A108EH4",
            name="ОФЗ 26248",
        )
        profile = (5, 1, 1, 1, 5, 1)

        row = _build_row(item, profile)

        self.assertEqual(row["identifier"], "RU000A108EH4")
        self.assertEqual(row["issuer"], "ОФЗ 26248")
        self.assertEqual(row["coupon_type"], "Фикс")
        self.assertEqual(row["inflation_risk"], 5)
        self.assertEqual(row["minority_shareholder_risk"], 1)


if __name__ == "__main__":
    unittest.main()
