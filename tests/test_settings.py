import os
import unittest
from unittest.mock import patch

from app.core.settings import Settings


class SettingsTests(unittest.TestCase):
    def test_loads_valid_environment(self):
        env = {
            "TELEGRAM_TOKEN": "token",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
            "T_INVEST_TOKEN": "",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.telegram_token, "token")
        self.assertEqual(settings.database_url, env["DATABASE_URL"])
        self.assertEqual(settings.moex_refresh_interval_seconds, 900)
        self.assertTrue(settings.t_invest_use_russian_ca)

    def test_rejects_too_frequent_moex_refresh(self):
        env = {
            "TELEGRAM_TOKEN": "token",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
            "MOEX_REFRESH_INTERVAL_SECONDS": "30",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "at least 60"):
                Settings.from_env()

    def test_reports_missing_variables(self):
        with patch("app.core.settings._load_dotenv", return_value={}):
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "TELEGRAM_TOKEN"):
                    Settings.from_env()

    def test_requires_asyncpg_url(self):
        env = {
            "TELEGRAM_TOKEN": "token",
            "DATABASE_URL": "postgresql://user:pass@localhost/db",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, r"postgresql\+asyncpg"):
                Settings.from_env()

    def test_management_command_does_not_require_telegram_token(self):
        env = {
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env(require_telegram_token=False)

        self.assertIsInstance(settings.telegram_token, str)

    def test_t_invest_catalog_token_is_optional(self):
        env = {
            "TELEGRAM_TOKEN": "token",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
            "T_INVEST_TOKEN": "",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()
        self.assertIsNone(settings.t_invest_token)

        env["T_INVEST_TOKEN"] = "read-only-token"
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()
        self.assertEqual(settings.t_invest_token, "read-only-token")

    def test_can_disable_bundled_t_invest_ca(self):
        env = {
            "TELEGRAM_TOKEN": "token",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
            "SSL_TBANK_VERIFY": "false",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()

        self.assertFalse(settings.t_invest_use_russian_ca)
