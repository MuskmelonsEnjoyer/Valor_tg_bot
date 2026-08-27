import asyncio
import logging

from app.database.requests import instrument_catalog_has_data, upload_bonds_shares


logger = logging.getLogger("instrument_refresh")
_catalog_ready = False


def catalog_is_ready() -> bool:
    return _catalog_ready


def _mark_catalog_ready() -> None:
    global _catalog_ready
    _catalog_ready = True


async def initialize_catalog_readiness() -> bool:
    """Make an existing DB catalog available before the network refresh."""
    try:
        if await instrument_catalog_has_data():
            _mark_catalog_ready()
            logger.info("Existing instrument catalog is ready for search")
    except Exception:
        # The scheduled refresh still gets a chance to repair/populate the
        # catalog; readiness detection itself must not stop bot startup.
        logger.exception("Could not inspect the existing instrument catalog")
    return catalog_is_ready()


async def refresh_instruments_periodically(
    interval_seconds: int, t_invest_token: str | None = None
) -> None:
    """Refresh the unified T-Invest/MOEX catalog until the app is stopped."""
    initial_failures = 0
    while True:
        refresh_succeeded = False
        try:
            logger.info("Starting scheduled instrument catalog refresh")
            updated_count = await upload_bonds_shares(t_invest_token)
            if updated_count:
                _mark_catalog_ready()
                initial_failures = 0
                refresh_succeeded = True
                logger.info(
                    "Scheduled instrument catalog refresh completed: %s instruments",
                    updated_count,
                )
            else:
                logger.warning("Instrument catalog refresh returned no instruments")
        except asyncio.CancelledError:
            raise
        except Exception:
            # A temporary upstream or database failure must not kill the bot.
            logger.exception("Scheduled instrument catalog refresh failed")

        if not catalog_is_ready() and not refresh_succeeded and initial_failures < 3:
            initial_failures += 1
            await asyncio.sleep(min(interval_seconds, 10 * initial_failures))
        else:
            await asyncio.sleep(interval_seconds)
