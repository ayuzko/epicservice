# app/utils/logging_setup.py

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

from rich.logging import RichHandler


DEFAULT_LOG_FILE = "data/logs/app.log"
DEFAULT_LOG_LEVEL = "INFO"


class ContextAdapter(logging.LoggerAdapter):
    """Додає контекстні поля (user_id, sku, action, dept тощо) до кожного запису."""

    def process(self, msg, kwargs):
        extra = self.extra.copy()
        if "extra" in kwargs and isinstance(kwargs["extra"], dict):
            extra.update(kwargs["extra"])
        kwargs["extra"] = extra
        # Додаємо короткий префікс із ключового контексту
        prefix_parts = []
        for key in ("user_id", "dept", "sku", "action"):
            if key in extra:
                prefix_parts.append(f"{key}={extra[key]}")
        prefix = ("[" + " ".join(prefix_parts) + "] ") if prefix_parts else ""
        return prefix + str(msg), kwargs


def ensure_log_dir(log_file: str) -> None:
    p = Path(log_file).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)


def setup_logging(
    *,
    console_level: str = DEFAULT_LOG_LEVEL,
    file_level: str = "DEBUG",
    log_file: Optional[str] = None,
    max_bytes: int = 5 * 1024 * 1024,  # 5 MB
    backup_count: int = 5,
) -> None:
    """
    Налаштовує логування:
    - Кольоровий консольний лог (RichHandler).
    - Файловий лог із ротацією (RotatingFileHandler) на 5 МБ та 5 бекапів.
    """

    # Базова конфігурація кореневого логера
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # максимально; хендлери відфільтрують рівні нижче

    # Формат для файлу (детальний, з часом/модулем/рядком)
    file_fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Кольоровий консольний хендлер (без ANSI у файл)
    console_handler = RichHandler(
        rich_tracebacks=False,
        show_time=False,    # час є у файловому логу; консоль лишаємо компактною
        show_level=True,
        show_path=False,
        markup=True,
    )
    console_handler.setLevel(getattr(logging, console_level.upper(), logging.INFO))
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    # Файловий хендлер із ротацією
    target_log = log_file or os.environ.get("APP_LOG_FILE", DEFAULT_LOG_FILE)
    ensure_log_dir(target_log)
    file_handler = RotatingFileHandler(
        target_log,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, file_level.upper(), logging.DEBUG))
    file_handler.setFormatter(file_fmt)

    # Скидаємо існуючі хендлери, щоб не дублювати вивід при повторному виклику
    for h in list(root.handlers):
        root.removeHandler(h)

    root.addHandler(console_handler)
    root.addHandler(file_handler)


def get_logger(name: str, **context: Any) -> ContextAdapter:
    """
    Повертає логер з можливістю додавати контекстні поля:
    logger = get_logger(__name__, user_id=123, dept="610")
    logger.info("Почато імпорт", extra={"action": "import_start"})
    """
    base_logger = logging.getLogger(name)
    return ContextAdapter(base_logger, context or {})
