"""
Менеджер сессий Telegram-бота.

Stateless-архитектура: бот не хранит состояние пользователей в
оперативной памяти между апдейтами. Любое изменение сессии сразу
сериализуется в JSON-файл sessions/<user_id>.json, что обеспечивает:
    - изоляцию данных разных пользователей (по user_id);
    - сохранность состояния при перезапуске бота;
    - возможность запуска нескольких копий бота.

Функции:
    load_session(user_id)       - загрузка сессии из JSON
    save_session(user_id, data) - сохранение сессии в JSON
    create_new_session(user_id) - создание сессии по умолчанию
    all_sessions()              - список всех файлов сессий (для рассылок)
    clear_session(user_id)      - удаление файла сессии
"""

import json
from pathlib import Path

import config

SESSION_DIR = config.SESSION_DIR


def _session_path(user_id: int) -> Path:
    """Возвращает путь к файлу сессии пользователя."""
    return SESSION_DIR / f"{user_id}.json"


def load_session(user_id: int) -> dict:
    """
    Загружает сессию пользователя из JSON-файла.

    Если файл не существует — возвращается новая сессия
    со значениями по умолчанию.

    Параметры:
        user_id - идентификатор пользователя Telegram

    Возвращает:
        dict - состояние пользователя
    """
    path = _session_path(user_id)
    if not path.exists():
        return create_new_session(user_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Повреждённый файл сессии не должен ломать бота —
        # начинаем с чистой сессии.
        return create_new_session(user_id)


def save_session(user_id: int, data: dict) -> None:
    """
    Сохраняет сессию пользователя в JSON-файл.

    Параметры:
        user_id - идентификатор пользователя Telegram
        data    - состояние пользователя
    """
    path = _session_path(user_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def create_new_session(user_id: int) -> dict:
    """
    Создаёт новую сессию со значениями по умолчанию.

    Параметры:
        user_id - идентификатор пользователя Telegram

    Возвращает:
        dict с начальным состоянием:
            state              - состояние FSM (MENU/UPLOAD/BROADCAST)
            name               - имя игрока, за которым бот следит
            subscribed         - подписка на уведомления о новых результатах
            screen_message_id  - id сообщения-экрана для антифлума
                                  (редактируется через edit_text, а не
                                  отправляется новое сообщение)
            screen_chat_id     - чат, в котором живёт сообщение-экран
    """
    return {
        "state": "MENU",
        "name": None,
        "subscribed": False,
        "screen_message_id": None,
        "screen_chat_id": None,
    }


def all_sessions() -> list[tuple[int, dict]]:
    """
    Возвращает список всех пользователей с их сессиями.

    Используется для рассылки уведомлений подписчикам
    и рассылок администратора.

    Возвращает:
        список кортежей (user_id, session)
    """
    result = []
    for path in SESSION_DIR.glob("*.json"):
        try:
            user_id = int(path.stem)
        except ValueError:
            continue
        result.append((user_id, load_session(user_id)))
    return result


def clear_session(user_id: int) -> None:
    """
    Удаляет файл сессии пользователя.

    Параметры:
        user_id - идентификатор пользователя Telegram
    """
    path = _session_path(user_id)
    if path.exists():
        path.unlink()
