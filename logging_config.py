import logging
import os
from logging.handlers import RotatingFileHandler
from pythonjsonlogger import json as jsonlogger
from config import config

def setup_logging():
    os.makedirs(config.log_dir, exist_ok=True)

    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    file_handler = RotatingFileHandler(
        os.path.join(config.log_dir, "sportedge.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
