# app/config/departments_map.py

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from app.utils.logging_setup import get_logger


log = get_logger(__name__, action="departments")

# Шлях до JSON з маппінгом відділів
DEPARTMENTS_JSON_PATH = Path(__file__).with_name("departments.json")


@lru_cache(maxsize=1)
def load_departments_map() -> Dict[str, str]:
    """
    Завантажує маппінг кодів відділів із JSON-файлу.

    Якщо файл відсутній або пошкоджений – повертає порожній словник
    і пише попередження в лог.
    """
    if not DEPARTMENTS_JSON_PATH.exists():
        log.warning("departments.json не знайдено: %s", DEPARTMENTS_JSON_PATH)
        return {}

    try:
        text = DEPARTMENTS_JSON_PATH.read_text(encoding="utf-8")
        data = json.loads(text)
    except Exception:
        log.exception("Помилка читання departments.json")
        return {}

    if not isinstance(data, dict):
        log.warning("departments.json має неочікувану структуру (очікуємо object)")
        return {}

    # Нормалізуємо ключі як рядки
    result: Dict[str, str] = {}
    for code, name in data.items():
        try:
            code_str = str(code).strip()
            name_str = str(name).strip()
        except Exception:
            continue
        if not code_str:
            continue
        result[code_str] = name_str

    log.info(
        "Маппінг відділів завантажено, записів=%s",
        len(result),
        extra={"codes": list(result.keys())},
    )
    return result


def get_department_name(dept_code: str) -> Optional[str]:
    """
    Повертає назву відділу за кодом із маппінгу departments.json
    або None, якщо немає відповідності.
    """
    if dept_code is None:
        return None

    code = str(dept_code).strip()
    if not code:
        return None

    mapping = load_departments_map()
    return mapping.get(code)
