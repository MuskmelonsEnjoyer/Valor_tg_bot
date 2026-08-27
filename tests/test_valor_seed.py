import unittest

from app.database.valor_seed import VALOR_ASSET_RISKS


class ValorSeedTests(unittest.TestCase):
    def test_catalog_contains_unique_excel_rows(self):
        keys = {
            (row["asset_type"], row["identifier"])
            for row in VALOR_ASSET_RISKS
        }

        self.assertEqual(len(VALOR_ASSET_RISKS), 70)
        self.assertEqual(len(keys), 70)
        self.assertIn(("share", "SBER"), keys)
        self.assertIn(("bond", "RU000A10EW93"), keys)

    def test_known_and_unknown_scores_are_normalized(self):
        for row in VALOR_ASSET_RISKS:
            for key, value in row.items():
                if key.endswith("_risk") and value is not None:
                    self.assertIn(value, range(1, 7))

        nlmk = next(
            row for row in VALOR_ASSET_RISKS if row["identifier"] == "NLMK"
        )
        self.assertIsNone(nlmk["inflation_risk"])
        self.assertEqual(nlmk["debt_risk"], 1)


if __name__ == "__main__":
    unittest.main()
