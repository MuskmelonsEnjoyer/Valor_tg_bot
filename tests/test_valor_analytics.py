import unittest

from app.services.valor_analytics import (
    calculate_portfolio_risks,
    format_portfolio_risks,
    format_valor_asset_profile,
)


class ValorAnalyticsTests(unittest.TestCase):
    def test_scores_are_weighted_by_position_value(self):
        positions = [
            {
                "asset_type": "share",
                "identifier": "AAA",
                "currency": "RUB",
                "market_value": 100,
            },
            {
                "asset_type": "share",
                "identifier": "BBB",
                "currency": "RUB",
                "market_value": 300,
            },
        ]
        profiles = {
            ("share", "AAA"): {"inflation_risk": 1},
            ("share", "BBB"): {"inflation_risk": 5},
        }

        report = calculate_portfolio_risks(positions, profiles)
        inflation = report["groups"][0]["factors"][0]

        self.assertAlmostEqual(inflation["score"], 4.0)
        self.assertAlmostEqual(inflation["percent_of_max"], 400 / 6)
        self.assertEqual(inflation["coverage"], 1.0)

    def test_missing_factor_is_excluded_and_coverage_is_shown(self):
        positions = [
            {
                "asset_type": "share",
                "identifier": "AAA",
                "currency": "RUB",
                "market_value": 100,
            },
            {
                "asset_type": "share",
                "identifier": "BBB",
                "currency": "RUB",
                "market_value": 300,
            },
        ]
        profiles = {
            ("share", "AAA"): {"inflation_risk": None},
            ("share", "BBB"): {"inflation_risk": 5},
        }

        report = calculate_portfolio_risks(positions, profiles)
        inflation = report["groups"][0]["factors"][0]

        self.assertEqual(inflation["score"], 5.0)
        self.assertEqual(inflation["coverage"], 0.75)

    def test_currencies_are_not_mixed(self):
        positions = [
            {
                "asset_type": "share",
                "identifier": "AAA",
                "currency": "RUB",
                "market_value": 100,
            },
            {
                "asset_type": "bond",
                "identifier": "BBB",
                "currency": "USD",
                "market_value": 10,
            },
        ]
        profiles = {
            ("share", "AAA"): {"inflation_risk": 1},
            ("bond", "BBB"): {"inflation_risk": 5},
        }

        report = calculate_portfolio_risks(positions, profiles)

        self.assertEqual([group["currency"] for group in report["groups"]], ["RUB", "USD"])
        self.assertEqual(report["groups"][0]["factors"][0]["score"], 1.0)
        self.assertEqual(report["groups"][1]["factors"][0]["score"], 5.0)

    def test_formatter_contains_scale_and_disclaimer(self):
        report = calculate_portfolio_risks(
            [
                {
                    "asset_type": "share",
                    "identifier": "AAA",
                    "currency": "RUB",
                    "market_value": 100,
                }
            ],
            {("share", "AAA"): {"inflation_risk": 2}},
        )

        text = format_portfolio_risks(report)

        self.assertIn("2.0/6", text)
        self.assertIn("Покрытие подборкой", text)
        self.assertIn("не инвестиционная рекомендация", text)

    def test_single_asset_profile_contains_excel_metadata_and_risks(self):
        text = format_valor_asset_profile(
            {
                "asset_type": "share",
                "identifier": "SBER",
                "issuer": "Сбербанк",
                "sector": "Банкинг",
                "company_type": "Дивидендная",
                "inflation_risk": 2,
                "geopolitical_risk": 6,
                "domestic_political_risk": 2,
                "debt_risk": 3,
                "currency_risk": 4,
                "minority_shareholder_risk": 1,
            }
        )

        self.assertIn("Сбербанк", text)
        self.assertIn("<code>SBER</code>", text)
        self.assertIn("Банкинг", text)
        self.assertIn("Геополитика/страна: <b>6/6</b>", text)


if __name__ == "__main__":
    unittest.main()
