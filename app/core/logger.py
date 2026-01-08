import logging

class OwnLogsFilter(logging.Filter):
    """
    Фильтр, пропускающий логи только от указанных модулей.
    """
    def filter(self, record):
        whitelist = ["bot", "database", "agent"]
        return record.name in whitelist

def logger_config() -> None:
    logger = logging.getLogger()
    if logger.hasHandlers():
        return
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
    "[%(asctime)s.%(msecs)03d] %(module)s:%(lineno)d %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(OwnLogsFilter())
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler("bot_log.log", mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(OwnLogsFilter())
    logger.addHandler(file_handler)