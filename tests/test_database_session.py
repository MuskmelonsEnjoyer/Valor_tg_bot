import unittest
from unittest.mock import patch

from app.database.session import run_migrations


class DatabaseSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_programmatic_migration_preserves_application_logging(self):
        database_url = "postgresql+asyncpg://user:pass@localhost/test"

        with patch("app.database.session.command.upgrade") as upgrade:
            await run_migrations(database_url)

        config, revision = upgrade.call_args.args
        self.assertEqual(revision, "head")
        self.assertFalse(config.attributes["configure_logger"])


if __name__ == "__main__":
    unittest.main()
