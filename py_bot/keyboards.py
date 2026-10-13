"""
Инлайн-клавиатуры бота Sound Spy.

Все экраны бота открываются и обновляются через инлайн-кнопки:
бот редактирует существующее сообщение вместо отправки новых
(предотвращение флуда в чате).
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def menu_keyboard(is_admin: bool = False, subscribed: bool = False) -> InlineKeyboardMarkup:
    """
    Главное меню бота-аналитика.

    Параметры:
        is_admin    - показывать ли админские кнопки (лог, рассылка)
        subscribed  - текущее состояние подписки на уведомления

    Возвращает:
        InlineKeyboardMarkup главного меню
    """
    rows = [
        [InlineKeyboardButton(text="🏆 Топ игроков", callback_data="top")],
        [
            InlineKeyboardButton(text="📊 Моя статистика", callback_data="stats"),
            InlineKeyboardButton(text="🎖 Ачивки", callback_data="achievements"),
        ],
        [InlineKeyboardButton(text="📤 Загрузить результаты", callback_data="upload")],
        [InlineKeyboardButton(text="🛩 Сводка полётов", callback_data="flight")],
    ]
    if subscribed:
        rows.append([InlineKeyboardButton(text="🔔 Уведомления: вкл", callback_data="unsubscribe")])
    else:
        rows.append([InlineKeyboardButton(text="🔕 Уведомления: выкл", callback_data="subscribe")])
    if is_admin:
        rows.append([
            InlineKeyboardButton(text="📜 Хвост лога", callback_data="log"),
            InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def upload_cancel_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура экрана загрузки результатов.

    Возвращает:
        InlineKeyboardMarkup с кнопкой отмены
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✖️ Отмена", callback_data="menu")],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура возврата в главное меню.

    Возвращает:
        InlineKeyboardMarkup с кнопкой «Назад»
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu")],
    ])
