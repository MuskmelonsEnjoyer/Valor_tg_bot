import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> dict[str, str]:
    """Read simple KEY=VALUE entries without mutating the process environment."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return {}

    values = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_token: str
    database_url: str
    moex_refresh_interval_seconds: int
    t_invest_token: str | None
    t_invest_use_russian_ca: bool

    @classmethod
    def from_env(cls, *, require_telegram_token: bool = True) -> "Settings":
        dotenv_values = _load_dotenv()
        values = {
            "TELEGRAM_TOKEN": os.getenv(
                "TELEGRAM_TOKEN", dotenv_values.get("TELEGRAM_TOKEN", "")
            ).strip(),
            "DATABASE_URL": os.getenv(
                "DATABASE_URL", dotenv_values.get("DATABASE_URL", "")
            ).strip(),
            "MOEX_REFRESH_INTERVAL_SECONDS": os.getenv(
                "MOEX_REFRESH_INTERVAL_SECONDS",
                dotenv_values.get("MOEX_REFRESH_INTERVAL_SECONDS", "900"),
            ).strip(),
            "T_INVEST_TOKEN": os.getenv(
                "T_INVEST_TOKEN", dotenv_values.get("T_INVEST_TOKEN", "")
            ).strip(),
            "SSL_TBANK_VERIFY": os.getenv(
                "SSL_TBANK_VERIFY",
                dotenv_values.get("SSL_TBANK_VERIFY", "true"),
            ).strip(),
        }
        required = (
            ["TELEGRAM_TOKEN", "DATABASE_URL"]
            if require_telegram_token
            else ["DATABASE_URL"]
        )
        missing = [name for name in required if not values[name]]
        if missing:
            names = ", ".join(missing)
            raise RuntimeError(f"Missing required environment variables: {names}")

        if not values["DATABASE_URL"].startswith("postgresql+asyncpg://"):
            raise RuntimeError(
                "DATABASE_URL must use the postgresql+asyncpg:// driver"
            )

        try:
            refresh_interval = int(values["MOEX_REFRESH_INTERVAL_SECONDS"])
        except ValueError as exc:
            raise RuntimeError(
                "MOEX_REFRESH_INTERVAL_SECONDS must be an integer"
            ) from exc
        if refresh_interval < 60:
            raise RuntimeError(
                "MOEX_REFRESH_INTERVAL_SECONDS must be at least 60 seconds"
            )

        ssl_tbank_verify = values["SSL_TBANK_VERIFY"].lower()
        valid_boolean_values = {
            "1",
            "true",
            "yes",
            "on",
            "0",
            "false",
            "no",
            "off",
        }
        if ssl_tbank_verify not in valid_boolean_values:
            raise RuntimeError(
                "SSL_TBANK_VERIFY must be true/false, yes/no, on/off or 1/0"
            )

        return cls(
            telegram_token=values["TELEGRAM_TOKEN"],
            database_url=values["DATABASE_URL"],
            moex_refresh_interval_seconds=refresh_interval,
            t_invest_token=values["T_INVEST_TOKEN"] or None,
            t_invest_use_russian_ca=ssl_tbank_verify in {"1", "true", "yes", "on"},
        )
