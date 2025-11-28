"""Logging utilities"""
from datetime import datetime
from storage import LOGS


def log(message: str) -> None:
    """Log a message to both console and in-memory buffer"""
    log_entry = {"t": datetime.now().isoformat(), "m": message}
    LOGS.append(log_entry)
    print(message)

