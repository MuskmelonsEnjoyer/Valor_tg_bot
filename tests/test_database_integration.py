import os
import unittest
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.settings import Settings
from app.database import models, requests
from app.database.session import (
    configure_database,
    get_session_factory,
    on_shutdown,
    run_migrations,
)


@unittest.skipUnless(
    os.getenv("RUN_DB_TESTS") == "1",
    "Set RUN_DB_TESTS=1 to run PostgreSQL integration tests",
)
class DatabaseIntegrationTests(unittest.IsolatedAsyncioTestCase):
    user_id = 900000000000 + (os.getpid() % 1000000)
    secid = f"AUDIT{uuid4().hex[:8].upper()}"
    isin = f"XS{uuid4().hex[:10].upper()}"[:12]
    second_secid = f"AUDIT{uuid4().hex[:8].upper()}"
    second_isin = f"XS{uuid4().hex[:10].upper()}"[:12]
    neo_secid = f"NEO{uuid4().hex[:8].upper()}@SPB"

    async def asyncSetUp(self):
        settings = Settings.from_env(require_telegram_token=False)
        configure_database(settings.database_url)
        await run_migrations(settings.database_url)
        async with get_session_factory()() as session, session.begin():
            await session.execute(
                pg_insert(models.Instruments).values(
                    [
                        {
                            "secid": self.secid,
                            "isin": self.isin,
                            "instrument_type": "share",
                            "currency": "RUB",
                            "extra_data": {"name": "integration-test"},
                        },
                        {
                            "secid": self.second_secid,
                            "isin": self.second_isin,
                            "instrument_type": "share",
                            "currency": "RUB",
                            "extra_data": {"name": "integration-test-2"},
                        },
                        {
                            "secid": self.neo_secid,
                            "isin": None,
                            "instrument_type": "share",
                            "currency": "USD",
                            "extra_data": {
                                "name": "Neo integration-test",
                                "ticker": "NBISPERPA",
                                "uid": "neo-integration-uid",
                                "asset_type": "neoasset",
                            },
                        },
                    ]
                )
            )

    async def asyncTearDown(self):
        async with get_session_factory()() as session, session.begin():
            await session.execute(
                delete(models.AppUser).where(models.AppUser.user_id == self.user_id)
            )
            await session.execute(
                delete(models.Instruments).where(
                    models.Instruments.secid.in_(
                        (self.secid, self.second_secid, self.neo_secid)
                    )
                )
            )
        await on_shutdown()

    async def test_token_portfolio_and_cascade_delete(self):
        token = "integration-test-token"
        self.assertIsNone(await requests.get_user_token(self.user_id))

        await requests.save_user_token(self.user_id, token)
        self.assertEqual(await requests.get_user_token(self.user_id), token)

        self.assertTrue(
            await requests.upload_user_portfolio(
                self.user_id, self.secid, "123.4500", 3
            )
        )
        self.assertTrue(
            await requests.upload_user_portfolio(
                self.user_id, self.second_secid, "50.0000", 2
            )
        )
        search_results, has_next = await requests.search_instruments(
            "integration-test", "share"
        )
        self.assertFalse(has_next)
        self.assertEqual(search_results[0]["secid"], self.secid)
        self.assertEqual(
            (await requests.get_instrument_info(self.secid))["isin"], self.isin
        )
        neo_results, _ = await requests.search_instruments(self.neo_secid, "share")
        self.assertEqual(neo_results[0]["secid"], self.neo_secid)
        self.assertEqual(neo_results[0]["asset_type"], "neoasset")

        async with get_session_factory()() as session, session.begin():
            await session.execute(
                update(models.Instruments)
                .where(models.Instruments.secid == self.secid)
                .values(
                    extra_data={
                        "name": "refreshed-instrument",
                        "last_price": 321.45,
                    }
                )
            )

        portfolio = await requests.get_user_portfolio(self.user_id)
        self.assertEqual(len(portfolio), 2)
        first_position = next(item for item in portfolio if item["isin"] == self.isin)
        self.assertEqual(first_position["quantity"], 3)
        self.assertEqual(first_position["name"], "refreshed-instrument")
        self.assertEqual(first_position["last_price"], 321.45)

        saved_count, skipped = await requests.sync_user_portfolio(
            self.user_id,
            [
                {"secid": self.secid, "avg_price": "200", "quantity": 4},
                {"secid": "UNKNOWN", "avg_price": "100", "quantity": 1},
            ],
        )
        self.assertEqual(saved_count, 1)
        self.assertEqual(skipped, ["UNKNOWN"])

        portfolio = await requests.get_user_portfolio(self.user_id)
        self.assertEqual(len(portfolio), 2)
        second_position = next(
            item for item in portfolio if item["isin"] == self.second_isin
        )
        self.assertEqual(second_position["quantity"], 2)

        self.assertTrue(await requests.delete_user(self.user_id))
        async with get_session_factory()() as session:
            self.assertIsNone(
                await session.scalar(
                    select(models.UserToken).where(
                        models.UserToken.user_id == self.user_id
                    )
                )
            )
            self.assertEqual(
                len(
                    (
                        await session.scalars(
                            select(models.UserPortfolio).where(
                                models.UserPortfolio.user_id == self.user_id
                            )
                        )
                    ).all()
                ),
                0,
            )

    async def test_valor_catalog_is_seeded_and_queryable(self):
        async with get_session_factory()() as session:
            count = await session.scalar(
                select(func.count()).select_from(models.ValorAssetRisk)
            )
        self.assertEqual(count, 70)

        profiles = await requests.get_valor_risk_profiles(
            {("share", "sber"), ("bond", "ru000a10ew93")}
        )
        self.assertEqual(profiles[("share", "SBER")]["inflation_risk"], 2)
        self.assertEqual(profiles[("bond", "RU000A10EW93")]["debt_risk"], 2)

        results, has_next = await requests.list_valor_assets(
            asset_type="share", query="Сбер", limit=8
        )
        self.assertFalse(has_next)
        self.assertEqual([row["identifier"] for row in results], ["SBER"])
        selected = await requests.get_valor_asset(results[0]["id"])
        self.assertEqual(selected["issuer"], "Сбербанк")
