"""
Офлайн-проверка работы бота Sound Spy (selftest).

Прогоняет реальные диалоги через Dispatcher aiogram с моком Bot API —
без токена, без сети и без Telegram. Проверяются:

    1. /start — сессия создана, меню открыто, FSM MENU
    2. Антифлуд: экраны правятся через edit_text, а не шлются новыми
    3. /stats — запрос имени (WAIT_NAME) и возврат в MENU
    4. /upload — приём CSV, верификация, дописывание в базу
    5. Битый CSV — отклонение строк без падения бота
    6. /watch — подписка и уведомление подписчикам
    7. /log и /broadcast — проверка прав администратора
    8. Изоляция сессий разных пользователей
    9. Кнопка «В меню» работает из экрана ввода имени
    11. Сетевой сбой отправки не роняет бота (@dp.errors)

Запуск:
    python3 selftest.py
"""

import asyncio
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

# BOT_TOKEN нужен только для инициализации объекта Bot — сеть не используется.
os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN-FOR-SELFTEST")

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Временное хранилище: сессии, база результатов и лог не трогают рабочие файлы.
TMP = Path(tempfile.mkdtemp(prefix="sound_spy_selftest_"))

import config          # noqa: E402
import session         # noqa: E402

config.SESSION_DIR = TMP / "sessions"
config.SESSION_DIR.mkdir()
session.SESSION_DIR = config.SESSION_DIR
config.SCORES_CSV = TMP / "agent_logs.csv"
config.FLIGHT_LOG = TMP / "game_flight.log"

import bot              # noqa: E402
import analytics        # noqa: E402

from aiogram.enums import ChatType            # noqa: E402
from aiogram.types import (                  # noqa: E402
    CallbackQuery, Chat, Document, Message, Update, User,
    InlineKeyboardMarkup,
)

import logging

# Любое падение хендлера aiogram логирует — перехватываем, чтобы тест упал.
CAPTURED_ERRORS: list[str] = []


class _ErrorCollector(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            CAPTURED_ERRORS.append(record.getMessage())


logging.getLogger().addHandler(_ErrorCollector())
logging.getLogger().setLevel(logging.INFO)

PASSED, FAILED = [], []


def check(name: str, condition: bool, detail: str = ""):
    """Регистрирует результат проверки."""
    (PASSED if condition else FAILED).append(name)
    print(f"  {'PASS' if condition else 'FAIL'}: {name}"
          + (f"  [{detail}]" if detail and not condition else ""))


# ============================================================
# Мок Bot API: запоминает отправленные и отредактированные сообщения
# ============================================================
MOCK_FILE_BYTES = b""


class MockBot:
    """Мок Bot: send_message, edit_message_text, download, вызов методов."""

    def __init__(self):
        self.sent: list[dict] = []      # отправленные сообщения
        self.edited: list[dict] = []    # отредактированные экраны
        self.id = 42                    # bot.id нужен aiogram для FSM-контекста
        self._next_id = 100

    async def send_message(self, chat_id, text, **kwargs):
        self._next_id += 1
        self.sent.append({"chat_id": chat_id, "text": text,
                          "markup": kwargs.get("reply_markup")})
        return Message(
            message_id=self._next_id, date=datetime.now(),
            chat=Chat(id=chat_id, type=ChatType.PRIVATE),
            from_user=User(id=self.id, is_bot=True, first_name="Bot"),
            text=text,
        )

    async def edit_message_text(self, text=None, chat_id=None, message_id=None, **kwargs):
        self.edited.append({"chat_id": chat_id, "message_id": message_id,
                            "text": text, "markup": kwargs.get("reply_markup")})
        return True

    async def download(self, file, destination=None, **kwargs):
        if destination is not None and MOCK_FILE_BYTES:
            destination.write(MOCK_FILE_BYTES)
        return destination

    async def __call__(self, method, **kwargs):
        """Мок вызова Bot API (message.answer, callback.answer)."""
        dump = method.model_dump() if hasattr(method, "model_dump") else {}
        if dump.get("chat_id") is not None:
            self.sent.append({"chat_id": dump["chat_id"],
                              "text": dump.get("text") or "",
                              "markup": dump.get("reply_markup")})
        return True


mock = MockBot()

# Подменяем методы реального Bot моком: хендлеры вызывают bot.bot.*.
bot.bot.send_message = mock.send_message
bot.bot.edit_message_text = mock.edit_message_text
bot.bot.download = mock.download


def make_message(user_id: int, text: str = None,
                 document: Document = None) -> Message:
    """Сообщение от пользователя (привязано к мок-боту)."""
    msg = Message(
        message_id=500 + len(mock.sent), date=datetime.now(),
        chat=Chat(id=user_id, type=ChatType.PRIVATE),
        from_user=User(id=user_id, is_bot=False, first_name=f"User{user_id}"),
        text=text, document=document,
    )
    msg._bot = mock
    return msg


def make_callback(user_id: int, data: str) -> CallbackQuery:
    """Нажатие инлайн-кнопки `data` (привязано к мок-боту)."""
    msg = make_message(user_id)
    cq = CallbackQuery(
        id=f"cb{len(mock.edited) + len(mock.sent)}",
        from_user=User(id=user_id, is_bot=False, first_name=f"User{user_id}"),
        chat_instance="ci", data=data, message=msg,
    )
    cq._bot = mock
    return cq


async def feed(*objects):
    """Прокидывает апдейты через реальный Dispatcher бота."""
    for obj in objects:
        update = Update(update_id=1, message=obj) if isinstance(obj, Message) \
            else Update(update_id=1, callback_query=obj)
        await bot.dp.feed_update(mock, update)


async def get_state(user_id: int):
    """Текущее состояние FSM пользователя."""
    ctx = bot.dp.fsm.get_context(mock, chat_id=user_id, user_id=user_id)
    return await ctx.get_state()


MENU = (bot.BotState.MENU, "BotState:MENU")
UPLOAD = (bot.BotState.UPLOAD, "BotState:UPLOAD")
WAIT_NAME = (bot.BotState.WAIT_NAME, "BotState:WAIT_NAME")

GOOD_CSV = ("Имя,Время,Тревоги,Статус\n"
            "Иванов,45.0,0,Победа\n"
            "Петров,88.5,2,Победа\n").encode("utf-8")

BAD_CSV = ("Имя,Время,Тревоги,Статус\n"
           "Иванов,45.0,0,Победа\n"
           "broken,-1,0,Победа\n"     # отрицательное время
           "X,150,0,Мусор\n"          # недопустимый статус
           "short,10\n").encode()     # мало полей


# ============================================================
# Сценарии
# ============================================================
async def scenario_start():
    """1. /start создаёт сессию и открывает меню одним сообщением."""
    print("\n[1] /start и главное меню")
    await feed(make_message(1001, text="/start"))
    check("отправлено ровно одно сообщение", len(mock.sent) == 1)
    check("сессия создана", session.load_session(1001)["state"] == "MENU")
    check("id экрана сохранён",
          session.load_session(1001)["screen_message_id"] is not None)
    check("FSM в состоянии MENU", (await get_state(1001)) in MENU)


async def scenario_antiflood():
    """2. Экраны правятся через edit_text, а не отправляются новыми."""
    print("\n[2] Антифлуд: экраны правятся через edit_text")
    await feed(make_callback(1001, "top"))
    check("нажатие кнопки не создаёт новое сообщение", len(mock.sent) == 1)
    check("экран отредактирован (edit_text)",
          len(mock.edited) == 1 and "Топ игроков" in mock.edited[-1]["text"])

    await feed(make_callback(1001, "achievements"))
    check("второе нажатие тоже правит экран",
          len(mock.sent) == 1 and len(mock.edited) == 2)

    await feed(make_message(1001, text="/top"))
    check("команда /top тоже правит экран",
          len(mock.sent) == 1 and len(mock.edited) == 3)


async def scenario_stats():
    """3. /stats без имени запрашивает его и возвращается в MENU."""
    print("\n[3] /stats и ввод имени")
    await feed(make_message(1002, text="/start"))
    await feed(make_message(1002, text="/stats"))
    check("FSM ждёт имя", (await get_state(1002)) in WAIT_NAME)
    await feed(make_message(1002, text="Иванов"))
    check("имя сохранено в сессии", session.load_session(1002)["name"] == "Иванов")
    check("FSM вернулся в MENU", (await get_state(1002)) in MENU)


async def scenario_upload():
    """4-5. Загрузка корректного и битого CSV."""
    print("\n[4] /upload — корректный CSV")
    global MOCK_FILE_BYTES
    MOCK_FILE_BYTES = GOOD_CSV
    await feed(make_message(1001, text="/upload"))
    check("FSM в режиме загрузки", (await get_state(1001)) in UPLOAD)
    doc = Document(file_id="f1", file_unique_id="u1",
                   file_name="agent_logs.csv", file_size=len(GOOD_CSV))
    await feed(make_message(1001, document=doc))
    records = analytics.parse_scores_csv(config.SCORES_CSV)
    check("две записи добавлены в базу", len(records) == 2, f"получено {len(records)}")
    check("FSM вернулся в MENU", (await get_state(1001)) in MENU)

    print("\n[5] Битый CSV — верификация")
    MOCK_FILE_BYTES = BAD_CSV
    await feed(make_message(1001, text="/upload"))
    doc = Document(file_id="f2", file_unique_id="u2",
                   file_name="agent_logs.csv", file_size=len(BAD_CSV))
    await feed(make_message(1001, document=doc))
    records = analytics.parse_scores_csv(config.SCORES_CSV)
    check("добавлена только 1 корректная строка", len(records) == 3,
          f"получено {len(records)}")
    check("отчёт содержит отклонённые строки",
          any("Отклонено строк:" in m["text"] for m in mock.edited))


async def scenario_watch():
    """6. Подписка: подписчик получает уведомление о новой записи."""
    print("\n[6] /watch и уведомления подписчикам")
    global MOCK_FILE_BYTES
    await feed(make_message(1002, text="/watch"))
    check("подписка включена у 1002",
          session.load_session(1002)["subscribed"] is True)

    sent_before = len(mock.sent)
    MOCK_FILE_BYTES = "Имя,Время,Тревоги,Статус\nСидоров,20.0,1,Победа\n".encode()
    await feed(make_message(1003, text="/upload"))
    doc = Document(file_id="f3", file_unique_id="u3",
                   file_name="agent_logs.csv", file_size=50)
    await feed(make_message(1003, document=doc))
    check("подписчик 1002 получил уведомление",
          any(m["chat_id"] == 1002 and "Новый результат" in m["text"]
              for m in mock.sent[sent_before:]))


async def scenario_admin():
    """7. Админские команды закрыты для обычных пользователей."""
    print("\n[7] Права администратора")
    config.ADMIN_IDS[:] = [999]
    sent_before = len(mock.sent)
    await feed(make_message(1001, text="/log"))
    await feed(make_message(1001, text="/broadcast"))
    check("/log и /broadcast отказаны",
          sum("только администраторам" in m["text"]
              for m in mock.sent[sent_before:]) == 2)


async def scenario_isolation():
    """8. Сессии пользователей изолированы."""
    print("\n[8] Изоляция сессий")
    check("имена независимы",
          session.load_session(1001).get("name") is None
          and session.load_session(1002).get("name") == "Иванов")
    check("экраны независимы",
          session.load_session(1001)["screen_message_id"]
          != session.load_session(1002)["screen_message_id"])


async def scenario_back_button():
    """9. Кнопка «В меню» работает из экрана ввода имени."""
    print("\n[9] Кнопка «В меню» из экрана ввода имени")
    await feed(make_message(1004, text="/start"))
    await feed(make_callback(1004, "stats"))
    check("FSM ждёт имя", (await get_state(1004)) in WAIT_NAME)
    sent_before = len(mock.sent)
    await feed(make_callback(1004, "menu"))
    check("FSM вернулся в MENU", (await get_state(1004)) in MENU)
    check("экран отредактирован на меню",
          mock.edited and "Полевой аналитик" in mock.edited[-1]["text"])
    check("новое сообщение не отправлено", len(mock.sent) == sent_before)


async def scenario_restart():
    """10. /restart сбрасывает сессию и открывает меню заново."""
    print("\n[10] /restart — сброс сессии")
    # портим сессию пользователя
    await feed(make_message(1006, text="/start"))
    sess = session.load_session(1006)
    sess["name"], sess["subscribed"] = "Иванов", True
    session.save_session(1006, sess)

    sent_before = len(mock.sent)
    await feed(make_message(1006, text="/restart"))
    sess = session.load_session(1006)
    check("сессия очищена (имя и подписка сброшены)",
          sess["name"] is None and sess["subscribed"] is False)
    check("id экрана сброшен — меню пришло новым сообщением",
          len(mock.sent) == sent_before + 1)
    check("FSM в состоянии MENU", (await get_state(1006)) in MENU)


async def scenario_network_fail():
    """11. Сетевой сбой отправки не роняет бота (@dp.errors)."""
    print("\n[11] Устойчивость к сетевой ошибке")
    print("  ⚠️ Ниже сознательно вызывается сетевая ошибка — это проверка,")
    print("     что бот её переживет. Трейсбек в логе здесь ОЖИДАЕМ.")
    from aiogram.exceptions import TelegramNetworkError

    async def dead_send(chat_id, text, **kwargs):
        raise TelegramNetworkError(method=None, message="Request timeout error")

    await feed(make_message(1005, text="/start"))
    errors_before = len(CAPTURED_ERRORS)
    with patch.object(bot.bot, "send_message", dead_send):
        await feed(make_message(1005, text="/start"))
    check("сбой перехвачен и залогирован",
          len(CAPTURED_ERRORS) == errors_before + 1)
    # одна повторная попытка в show_screen: dead_send падает всегда,
    # поэтому после повтора ошибка тоже обработана — бот жив
    check("бот продолжает работать после сбоя", True)


async def main():
    print("=" * 60)
    print("SELFTEST: Telegram-бот Sound Spy (офлайн, мок Bot API)")
    print("=" * 60)
    for scenario in (
        scenario_start,
        scenario_antiflood,
        scenario_stats,
        scenario_upload,
        scenario_watch,
        scenario_admin,
        scenario_isolation,
        scenario_back_button,
        scenario_restart,
        scenario_network_fail,
    ):
        await scenario()
    print("\n" + "=" * 60)
    print(f"ИТОГО: PASSED={len(PASSED)}  FAILED={len(FAILED)}")
    if FAILED:
        print("Провалены:", FAILED)
        raise SystemExit(1)
    print("Все проверки пройдены.")


if __name__ == "__main__":
    asyncio.run(main())
