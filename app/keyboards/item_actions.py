from aiogram.utils.keyboard import InlineKeyboardBuilder

def build_item_action_kb(sku: str, current_qty: float, max_qty: float, in_list_qty: float):
    """
    sku: Артикул товара
    current_qty: Сколько пользователь "наклацал" прямо сейчас (для ввода) или шаг
    max_qty: Доступный остаток (Залишок - Резерв)
    in_list_qty: Сколько УЖЕ собрано в списке (для отображения)
    """
    builder = InlineKeyboardBuilder()

    # Ряд 1: [-] [ Кількість ] [+]
    # callback_data формат: action:sku:qty
    builder.button(text="➖", callback_data=f"act:dec:{sku}")
    builder.button(text=f"🛒 {in_list_qty} шт.", callback_data="act:noop") # Просто инфо
    builder.button(text="➕", callback_data=f"act:inc:{sku}")

    # Ряд 2: Добавить всё (остаток)
    left_to_pick = max(0.0, max_qty - in_list_qty)
    if left_to_pick > 0:
        builder.button(text=f"📥 Додати все ({left_to_pick})", callback_data=f"act:all:{sku}")
    else:
        # Если все собрано, можно предложить добавить излишек
        builder.button(text="⚠️ Додати надлишок (+1)", callback_data=f"act:surplus:{sku}")

    # Ряд 3: Ввод числа вручную
    builder.button(text="🔢 Ввести число", callback_data=f"act:input:{sku}")

    # Ряд 4: Фото и Комментарий
    builder.button(text="📷 +Фото", callback_data=f"act:photo:{sku}")
    builder.button(text="💬 +Комент", callback_data=f"act:comment:{sku}")

    # Ряд 5: Навигация (если это карусель, тут будут стрелки, пока просто Назад)
    builder.button(text="🔙 Назад", callback_data="act:back")

    builder.adjust(3, 1, 1, 2, 1)
    return builder.as_markup()