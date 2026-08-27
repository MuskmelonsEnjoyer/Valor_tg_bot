import logging
import sys
from logging.handlers import RotatingFileHandler


class OwnLogsFilter(logging.Filter):
    """
    Фильтр, пропускающий INFO/DEBUG только от наших модулей,
    но ВСЕГДА пропускающий любые ОШИБКИ (ERROR и выше) и логи от root.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR:
            return True

        if record.name == "root":
            return True
        
        whitelist = [
            "bot",
            "database",
            "agent",
            "news_parser",
            "handlers",
            "main",
            "instrument_refresh",
            "t_invest",
            "langgraph",
            "langchain",
        ]

        return any(record.name.startswith(name) for name in whitelist)


def logger_config() -> None:
    logger = logging.getLogger()
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "[%(asctime)s.%(msecs)03d] %(module)s:%(lineno)d %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Настройка консоли
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(OwnLogsFilter())
    logger.addHandler(console_handler)

    # Настройка файла
    file_handler = RotatingFileHandler(
        "bot_log.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(OwnLogsFilter())
    logger.addHandler(file_handler)
