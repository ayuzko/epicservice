# app/services/items.py

from __future__ import annotations

from typing import Any, Dict

from app.config.departments_map import get_department_name


def _fmt_qty(value: Any) -> str:
    """
    Форматує кількість/резерв:
    - якщо число ціле (1, 3, 5) -> без .0, як штуки;
    - якщо дробове (4.7, 3.1) -> показуємо із збереженням дроби й додаємо "кг".
    """
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)

    if num.is_integer():
        return f"{int(num)}"
    else:
        s = f"{num:.3f}".rstrip("0").rstrip(".")
        return f"{s} кг"


def format_item_card(item: Dict[str, Any]) -> str:
    """
    Формує текст картки товару для відправки в Telegram (parse_mode=HTML).

    Структура:
    📦 Назва
    🆔 Артикул (жирний)
    ──────────────
    📂 Відділ / група
    ⏳ Без руху
    ──────────────
    📷 Фото: в розробці
    ──────────────
    💵 Ціна
    ──────────────
    📊 Стан складу
    📉 Залишок (жирний)
    🔒 Резерв (жирний)
    ──────────────
    💬 Останній коментар: в розробці
    """

    name = item.get("name") or "Без назви"
    sku = item.get("sku") or "—"
    dept_code = item.get("dept_code") or "—"

    # Назву відділу беремо з item.dept_name, а якщо там порожньо — з departments.json
    raw_dept_name = item.get("dept_name") or ""
    mapped_dept_name = get_department_name(str(dept_code)) if dept_code != "—" else None
    dept_name = raw_dept_name or mapped_dept_name or ""

    group_name = item.get("group_name") or ""
    mt_months = item.get("mt_months")
    base_qty = item.get("base_qty", 0)
    base_reserve = item.get("base_reserve", 0)
    price = item.get("price")

    lines: list[str] = []

    # Заголовок + артикул (жирний)
    lines.append(f"📦 {name}")
    lines.append(f"🆔 Артикул: <b>{sku}</b>")
    lines.append("──────────────")

    # Відділ / група
    dept_part = f"Відділ: {dept_code}"
    if dept_name:
        dept_part += f" ({dept_name})"
    if group_name:
        lines.append(f"📂 {dept_part} // Група: {group_name}")
    else:
        lines.append(f"📂 {dept_part}")

    # МТ (без руху)
    if mt_months is not None:
        try:
            mt_val = float(mt_months)
            lines.append(f"⏳ Без руху: {mt_val:.0f} міс.")
        except (TypeError, ValueError):
            lines.append(f"⏳ Без руху: {mt_months}")
    else:
        lines.append("⏳ Без руху: н/д")

    # Блок під фото
    lines.append("──────────────")
    lines.append("📷 Фото: в розробці")
    lines.append("──────────────")

    # Ціна
    if price is not None:
        try:
            price_val = float(price)
            lines.append(f"💵 Ціна: {price_val:.2f} грн")
        except (TypeError, ValueError):
            lines.append(f"💵 Ціна: {price}")
    else:
        lines.append("💵 Ціна: н/д")

    # Розділювач перед станом складу
    lines.append("──────────────")

    # Стан складу
    qty_str = _fmt_qty(base_qty)
    reserve_str = _fmt_qty(base_reserve)

    lines.append("📊 Стан складу:")
    lines.append(f"📉 Залишок (база): <b>{qty_str}</b>")
    lines.append(f"🔒 Резерв (база): <b>{reserve_str}</b>")

    # Блок під останній коментар
    lines.append("──────────────")
    lines.append("💬 Останній коментар: в розробці")

    return "\n".join(lines)
