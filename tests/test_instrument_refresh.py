import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.services.instrument_refresh import (
    initialize_catalog_readiness,
    refresh_instruments_periodically,
)


class InstrumentRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_database_catalog_is_ready_without_network(self):
        with patch(
            "app.services.instrument_refresh.instrument_catalog_has_data",
            new=AsyncMock(return_value=True),
        ):
            self.assertTrue(await initialize_catalog_readiness())

    async def test_refreshes_immediately_and_can_be_cancelled(self):
        refresh = AsyncMock()

        with patch(
            "app.services.instrument_refresh.upload_bonds_shares", refresh
        ):
            task = asyncio.create_task(refresh_instruments_periodically(3600))
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        refresh.assert_awaited_once()

    async def test_refresh_failure_does_not_stop_loop(self):
        refresh = AsyncMock(
            side_effect=[RuntimeError("temporary"), asyncio.CancelledError]
        )

        with patch(
            "app.services.instrument_refresh.upload_bonds_shares", refresh
        ):
            task = asyncio.create_task(refresh_instruments_periodically(0))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        self.assertGreaterEqual(refresh.await_count, 2)


if __name__ == "__main__":
    unittest.main()
