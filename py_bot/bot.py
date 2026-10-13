"""
Telegram-бот Sound Spy — «Полевой аналитик».

Бот является внешним сервисом-помощником для игры Sound Spy, а НЕ
копией игры в чате. Игровая логика остаётся в Pygame-приложении
(py_sound_spy), а бот работает с данными, которые игра выгружает:

    - agent_logs.csv  — таблица рекордов сессий (имя, время, тревоги, статус)
    - game_flight.log — «чёрный ящик» событий игрового цикла

Возможности:
    /start          - главное меню
    /help           - справка по командам
    /top            - таблица лидеров
    /stats [имя]    - личная статистика игрока
    /achievements   - ачивки игрока
    /upload         - загрузка CSV-файла результатов в общую базу
    /watch          - подписка на уведомления о новых результатах
    /restart        - сброс сессии и возврат в главное меню
    /flight         - сводка по логу игры
    /log N          - хвост game_flight.log (только для админов)
    /broadcast      - рассылка подписчикам (только для админов)

Архитектура:
    - stateless: состояние пользователя хранится в JSON-файлах
      sessions/<user_id>.json и не живёт в глобальной памяти
    - FSM (aiogram 3): MENU, UPLOAD, BROADCAST, WAIT_NAME
    - антифлуд: любой экран обновляется через edit_text
    - изоляция: каждая команда работает с сессией конкретного user_id

Запуск:
    1. pip install -r requirements.txt
    2. Создать бота у @BotFather, вставить токен в .env (BOT_TOKEN=...)
    3. python3 bot.py
"""

import asyncio
import io
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramServerError,
)
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    ErrorEvent,
    InlineKeyboardMarkup,
)

import analytics
import config
import keyboards
import session

# ============================================================
# Логирование событий бота
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(config.BOT_LOG, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ============================================================
# FSM: состояния бота
# ============================================================
class BotState(StatesGroup):
    """Конечный автомат бота: основные экраны и режимы ввода."""

    MENU = State()        # главное меню
    UPLOAD = State()      # ожидание CSV-файла с результатами
    BROADCAST = State()   # ввод текста рассылки (админ)
    WAIT_NAME = State()   # ввод имени игрока для статистики


# ============================================================
# Инициализация бота
# ============================================================
if not config.BOT_TOKEN:
    raise SystemExit(
        "Не задан BOT_TOKEN. Создайте бота у @BotFather и укажите токен "
        "в файле py_bot/.env (см. .env.example)."
    )

bot = Bot(
    token=config.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())


# ============================================================
# Вспомогательные функции
# ============================================================
async def show_screen(chat_id: int, user_id: int, text: str,
                      keyboard: InlineKeyboardMarkup) -> None:
    """
    Показывает пользователю экран бота через редактирование (edit_text).

    Нюанс (антифлуд): Telegram ограничивает частоту отправки сообщений,
    а чат засоряется, если бот шлёт новое сообщение на каждое нажатие
    кнопки. Поэтому бот держит для каждого пользователя одно
    «сообщение-экран»: его id и чат хранятся в JSON-сессии, а любой
    новый экран редактирует это сообщение через bot.edit_message_text().

    Логика:
        1. если id экрана есть — пробуем отредактировать;
        2. TelegramBadRequest «message is not modified» — текст не
           изменился, это норма, молча выходим;
        3. сообщение удалено/устарело/не в том чате — шлём новое и
           запоминаем его id в сессии;
        4. при сетевой ошибке (TelegramNetworkError) — одна повторная
           отправка, временные сбои Telegram бывают часто.

    Параметры:
        chat_id  - идентификатор чата экрана
        user_id  - идентификатор пользователя (ключ сессии)
        text     - текст экрана
        keyboard - инлайн-клавиатура экрана
    """
    sess = session.load_session(user_id)
    screen_id = sess.get("screen_message_id")
    screen_chat = sess.get("screen_chat_id")

    if screen_id and screen_chat == chat_id:
        try:
            await bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=screen_id,
                reply_markup=keyboard,
            )
            return
        except TelegramBadRequest as e:
            # Текст и клавиатура не изменились — редактировать нечего.
            if "message is not modified" in str(e):
                return
            # Сообщение удалено или недостижимо — шлём новое.
            logger.info("Экран %s недоступен (%s), отправляем новый", screen_id, e)
        except Exception as e:
            logger.info("Не удалось отредактировать экран %s: %s", screen_id, e)

    try:
        msg = await bot.send_message(chat_id, text, reply_markup=keyboard)
    except (TelegramNetworkError, TelegramServerError):
        # Временный сетевой сбой — одна повторная попытка.
        logger.warning("Сбой отправки экрана, повторная попытка")
        msg = await bot.send_message(chat_id, text, reply_markup=keyboard)

    sess["screen_message_id"] = msg.message_id
    sess["screen_chat_id"] = chat_id
    session.save_session(user_id, sess)


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    return user_id in config.ADMIN_IDS


def format_record_line(record: analytics.Record) -> str:
    """Форматирует одну запись для уведомлений."""
    return (
        f"<b>{record.name}</b>: {record.time_sec:.1f} с, "
        f"тревог: {record.alerts}, статус: {record.status}"
    )


# ============================================================
# Команды
# ============================================================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """
    Обработчик /start.

    Создаёт сессию пользователя и открывает главное меню.
    """
    logger.info("User %d: /start", message.from_user.id)
    user_id = message.from_user.id
    sess = session.load_session(user_id)
    sess["state"] = "MENU"
    sess["screen_message_id"] = None
    session.save_session(user_id, sess)
    await state.set_state(BotState.MENU)

    text = (
        "🎮 <b>ЗВУКОВОЙ ШПИОН — Полевой аналитик</b>\n\n"
        "Бот работает с результатами игры Sound Spy: рекорды, личная "
        "статистика, ачивки и уведомления.\n\n"
        "Загрузите свой <code>agent_logs.csv</code> через "
        "«📤 Загрузить результаты», чтобы попасть в общий рейтинг."
    )
    await show_screen(message.chat.id, user_id, text,
                      keyboards.menu_keyboard(is_admin(user_id), sess.get("subscribed", False)))


@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик /help — справка по всем командам бота."""
    logger.info("User %d: /help", message.from_user.id)
    text = (
        "🎮 <b>Полевой аналитик Sound Spy</b>\n\n"
        "Бот — сервис для игры, а не игра в чате. Логика остаётся в "
        "Pygame-приложении, бот анализирует выгруженные данные.\n\n"
        "<b>Команды:</b>\n"
        "/top — таблица лидеров\n"
        "/stats [имя] — личная статистика\n"
        "/achievements [имя] — ачивки\n"
        "/upload — загрузить agent_logs.csv в общую базу\n"
        "/watch — подписка на уведомления о новых результатах\n"
        "/restart — сброс сессии и возврат в главное меню\n"
        "/flight — сводка «чёрного ящика» игры\n"
        "/help — эта справка"
    )
    await message.answer(text)


@dp.message(Command("top"))
async def cmd_top(message: Message):
    """Обработчик /top — таблица лидеров (экран редактируется)."""
    logger.info("User %d: /top", message.from_user.id)
    user_id = message.from_user.id
    sess = session.load_session(user_id)
    records = analytics.parse_scores_csv(config.SCORES_CSV)
    table = analytics.format_leaderboard(records, highlight=sess.get("name"))
    await show_screen(
        message.chat.id, user_id,
        f"🏆 <b>Топ игроков</b>\n\n<pre>{table}</pre>",
        keyboards.back_keyboard(),
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext):
    """
    Обработчик /stats [имя] — личная статистика.

    Без аргумента использует имя из сессии, иначе просит его ввести.
    """
    logger.info("User %d: /stats", message.from_user.id)
    user_id = message.from_user.id
    sess = session.load_session(user_id)
    args = message.text.split(maxsplit=1)
    name = args[1].strip() if len(args) > 1 else sess.get("name")
    if not name:
        await state.set_state(BotState.WAIT_NAME)
        await message.answer("Введите имя игрока, как оно записано в таблице рекордов:")
        return
    records = analytics.parse_scores_csv(config.SCORES_CSV)
    stats = analytics.player_stats(records, name)
    sess["name"] = name
    session.save_session(user_id, sess)
    await show_screen(message.chat.id, user_id,
                      analytics.format_stats(stats, name),
                      keyboards.back_keyboard())


@dp.message(Command("achievements"))
async def cmd_achievements(message: Message, state: FSMContext):
    """Обработчик /achievements [имя] — ачивки игрока."""
    logger.info("User %d: /achievements", message.from_user.id)
    user_id = message.from_user.id
    sess = session.load_session(user_id)
    args = message.text.split(maxsplit=1)
    name = args[1].strip() if len(args) > 1 else sess.get("name")
    if not name:
        await state.set_state(BotState.WAIT_NAME)
        await message.answer("Введите имя игрока для показа ачивок:")
        return
    records = analytics.parse_scores_csv(config.SCORES_CSV)
    sess["name"] = name
    session.save_session(user_id, sess)
    await show_screen(message.chat.id, user_id,
                      analytics.format_achievements(records, name),
                      keyboards.back_keyboard())


@dp.message(Command("upload"))
async def cmd_upload(message: Message, state: FSMContext):
    """Обработчик /upload — включает режим ожидания CSV-файла."""
    logger.info("User %d: /upload", message.from_user.id)
    user_id = message.from_user.id
    sess = session.load_session(user_id)
    sess["state"] = "UPLOAD"
    session.save_session(user_id, sess)
    await state.set_state(BotState.UPLOAD)
    await show_screen(
        message.chat.id,
        user_id,
        "📤 Пришлите файл <code>agent_logs.csv</code> с результатами игр.\n"
        "Формат: Имя, Время, Тревоги, Статус",
        keyboards.upload_cancel_keyboard(),
    )


@dp.message(Command("watch"))
async def cmd_watch(message: Message):
    """Обработчик /watch — переключение подписки на уведомления."""
    logger.info("User %d: /watch", message.from_user.id)
    user_id = message.from_user.id
    sess = session.load_session(user_id)
    sess["subscribed"] = not sess.get("subscribed", False)
    session.save_session(user_id, sess)
    state = "включена" if sess["subscribed"] else "выключена"
    await message.answer(f"🔔 Подписка на уведомления {state}.")


@dp.message(Command("restart"))
async def cmd_restart(message: Message, state: FSMContext):
    """
    Обработчик /restart — полный сброс сессии пользователя.

    Удаляет JSON-файл сессии (имя игрока, подписка, id экрана),
    сбрасывает FSM и открывает главное меню — состояние как при
    первом запуске. Старый экран в чате остаётся, но бот больше
    его не редактирует: новое меню приходит отдельным сообщением.

    Параметры:
        message - сообщение с командой /restart
        state   - контекст FSM
    """
    user_id = message.from_user.id
    logger.info("User %d: /restart — сброс сессии", user_id)

    # 1. Удаляем файл сессии и создаём чистую.
    session.clear_session(user_id)
    sess = session.create_new_session(user_id)
    sess["state"] = "MENU"
    sess["screen_message_id"] = None      # старый экран больше не трогаем
    session.save_session(user_id, sess)

    # 2. Сбрасываем FSM в MENU.
    await state.set_state(BotState.MENU)

    # 3. Открываем главное меню новым сообщением.
    text = (
        "🎮 <b>ЗВУКОВОЙ ШПИОН — Полевой аналитик</b>\n\n"
        "Бот работает с результатами игры Sound Spy: рекорды, личная "
        "статистика, ачивки и уведомления.\n\n"
        "Загрузите свой <code>agent_logs.csv</code> через "
        "«📤 Загрузить результаты», чтобы попасть в общий рейтинг."
    )
    await show_screen(message.chat.id, user_id, text,
                      keyboards.menu_keyboard(is_admin(user_id), False))


@dp.message(Command("flight"))
async def cmd_flight(message: Message):
    """Обработчик /flight — сводка по логу игры (экран редактируется)."""
    logger.info("User %d: /flight", message.from_user.id)
    user_id = message.from_user.id
    summary = analytics.summarize_flight_log()
    await show_screen(message.chat.id, user_id,
                      analytics.format_log_summary(summary),
                      keyboards.back_keyboard())


@dp.message(Command("log"))
async def cmd_log(message: Message):
    """Обработчик /log N — хвост лога игры (только для админов)."""
    logger.info("User %d: /log", message.from_user.id)
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Команда доступна только администраторам.")
        return
    args = message.text.split(maxsplit=1)
    lines = 20
    if len(args) > 1 and args[1].strip().isdigit():
        lines = min(100, int(args[1].strip()))
    tail = analytics.tail_log(config.FLIGHT_LOG, lines)
    if not tail:
        text = "Лог игры не найден (нет файла game_flight.log)."
    else:
        text = f"📜 Последние события игры:\n\n<pre>{chr(10).join(tail[-lines:])}</pre>"
    await show_screen(message.chat.id, message.from_user.id, text,
                      keyboards.back_keyboard())


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    """Обработчик /broadcast — рассылка подписчикам (только для админов)."""
    logger.info("User %d: /broadcast", message.from_user.id)
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Команда доступна только администраторам.")
        return
    await state.set_state(BotState.BROADCAST)
    await message.answer("Введите текст рассылки для подписчиков:")


# ============================================================
# Инлайн-кнопки
# ============================================================
@dp.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню."""
    logger.info("User %d: кнопка «меню»", callback.from_user.id)
    user_id = callback.from_user.id
    sess = session.load_session(user_id)
    sess["state"] = "MENU"
    session.save_session(user_id, sess)
    await state.set_state(BotState.MENU)
    await show_screen(
        callback.message.chat.id,
        user_id,
        "🎮 <b>ЗВУКОВОЙ ШПИОН — Полевой аналитик</b>\n\nВыберите действие:",
        keyboards.menu_keyboard(is_admin(user_id), sess.get("subscribed", False)),
    )
    await callback.answer()


@dp.callback_query(F.data == "top")
async def cb_top(callback: CallbackQuery):
    """Кнопка «Топ игроков» — таблица лидеров."""
    logger.info("User %d: кнопка «топ»", callback.from_user.id)
    user_id = callback.from_user.id
    sess = session.load_session(user_id)
    records = analytics.parse_scores_csv(config.SCORES_CSV)
    table = analytics.format_leaderboard(records, highlight=sess.get("name"))
    await show_screen(
        callback.message.chat.id,
        user_id,
        f"🏆 <b>Топ игроков</b>\n\n<pre>{table}</pre>",
        keyboards.back_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "stats")
async def cb_stats(callback: CallbackQuery, state: FSMContext):
    """Кнопка «Моя статистика»."""
    logger.info("User %d: кнопка «статистика»", callback.from_user.id)
    user_id = callback.from_user.id
    sess = session.load_session(user_id)
    name = sess.get("name")
    if not name:
        await state.set_state(BotState.WAIT_NAME)
        await show_screen(
            callback.message.chat.id,
            user_id,
            "📊 Введите имя игрока, как оно записано в таблице рекордов:",
            keyboards.back_keyboard(),
        )
        await callback.answer()
        return
    records = analytics.parse_scores_csv(config.SCORES_CSV)
    text = analytics.format_stats(analytics.player_stats(records, name), name)
    await show_screen(callback.message.chat.id, user_id, text, keyboards.back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "achievements")
async def cb_achievements(callback: CallbackQuery, state: FSMContext):
    """Кнопка «Ачивки»."""
    logger.info("User %d: кнопка «ачивки»", callback.from_user.id)
    user_id = callback.from_user.id
    sess = session.load_session(user_id)
    name = sess.get("name")
    if not name:
        await state.set_state(BotState.WAIT_NAME)
        await show_screen(
            callback.message.chat.id,
            user_id,
            "🎖 Введите имя игрока для показа ачивок:",
            keyboards.back_keyboard(),
        )
        await callback.answer()
        return
    records = analytics.parse_scores_csv(config.SCORES_CSV)
    text = analytics.format_achievements(records, name)
    await show_screen(callback.message.chat.id, user_id, text, keyboards.back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "flight")
async def cb_flight(callback: CallbackQuery):
    """Кнопка «Сводка полётов» — аналитика лога игры."""
    logger.info("User %d: кнопка «сводка полётов»", callback.from_user.id)
    user_id = callback.from_user.id
    summary = analytics.summarize_flight_log()
    await show_screen(
        callback.message.chat.id,
        user_id,
        analytics.format_log_summary(summary),
        keyboards.back_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "upload")
async def cb_upload(callback: CallbackQuery, state: FSMContext):
    """Кнопка «Загрузить результаты» — режим ожидания CSV."""
    logger.info("User %d: кнопка «загрузить»", callback.from_user.id)
    user_id = callback.from_user.id
    sess = session.load_session(user_id)
    sess["state"] = "UPLOAD"
    session.save_session(user_id, sess)
    await state.set_state(BotState.UPLOAD)
    await show_screen(
        callback.message.chat.id,
        user_id,
        "📤 Пришлите файл <code>agent_logs.csv</code> с результатами игр.\n"
        "Формат: Имя, Время, Тревоги, Статус",
        keyboards.upload_cancel_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data.in_({"subscribe", "unsubscribe"}))
async def cb_subscribe(callback: CallbackQuery):
    """Кнопки подписки/отписки на уведомления о новых результатах."""
    logger.info("User %d: подписка переключена", callback.from_user.id)
    user_id = callback.from_user.id
    sess = session.load_session(user_id)
    sess["subscribed"] = callback.data == "subscribe"
    session.save_session(user_id, sess)
    await show_screen(
        callback.message.chat.id,
        user_id,
        "🎮 <b>ЗВУКОВОЙ ШПИОН — Полевой аналитик</b>\n\nВыберите действие:",
        keyboards.menu_keyboard(is_admin(user_id), sess["subscribed"]),
    )
    await callback.answer("Подписка обновлена")


@dp.callback_query(F.data == "log")
async def cb_log(callback: CallbackQuery):
    """Кнопка «Хвост лога» (админ) — последние события «чёрного ящика»."""
    logger.info("User %d: кнопка «лог»", callback.from_user.id)
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для админов", show_alert=True)
        return
    user_id = callback.from_user.id
    tail = analytics.tail_log(config.FLIGHT_LOG, 15)
    if not tail:
        text = "Лог игры не найден (нет файла game_flight.log)."
    else:
        text = f"📜 Последние события игры:\n\n<pre>{chr(10).join(tail)}</pre>"
    await show_screen(callback.message.chat.id, user_id, text, keyboards.back_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "broadcast")
async def cb_broadcast(callback: CallbackQuery, state: FSMContext):
    """Кнопка «Рассылка» (админ) — ввод текста рассылки."""
    logger.info("User %d: кнопка «рассылка»", callback.from_user.id)
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для админов", show_alert=True)
        return
    user_id = callback.from_user.id
    await state.set_state(BotState.BROADCAST)
    await show_screen(
        callback.message.chat.id,
        user_id,
        "📢 Введите текст рассылки для подписчиков:",
        keyboards.back_keyboard(),
    )
    await callback.answer()


# ============================================================
# Обработка файлов и текстовых сообщений по состояниям FSM
# ============================================================
@dp.message(StateFilter(BotState.UPLOAD), F.document)
async def handle_upload(message: Message, state: FSMContext):
    """
    Приём CSV-файла с результатами.

    Алгоритм:
        1. Скачиваем файл из Telegram
        2. Парсим и верифицируем каждую строку
        3. Корректные записи дописываем в общую базу agent_logs.csv
        4. Подписчиков уведомляем о новых результатах
        5. Возвращаем игрока в меню
    """
    user_id = message.from_user.id
    try:
        buffer = io.BytesIO()
        try:
            await bot.download(message.document, destination=buffer)
        except (TelegramNetworkError, TelegramServerError):
            # Файловый сервер Telegram может отвечать с задержкой —
            # делаем одну повторную попытку скачивания.
            logger.warning("Сбой скачивания файла, повторная попытка")
            await bot.download(message.document, destination=buffer)
        text = buffer.getvalue().decode("utf-8-sig")
    except Exception as e:
        logger.warning("User %d: ошибка загрузки файла: %s", user_id, e)
        await message.answer("⛔ Не удалось прочитать файл. Отправьте CSV.")
        return

    records, errors = analytics.parse_scores_text(text)
    added = analytics.append_records(records)

    report = ["📥 <b>Результат обработки файла</b>", ""]
    report.append(f"Добавлено записей: {added}")
    if errors:
        report.append("")
        report.append("Отклонено строк:")
        for err in errors[:10]:
            report.append(f"• {err}")
    else:
        report.append("Все строки прошли верификацию ✅")

    # Уведомляем подписчиков о новых результатах
    if records:
        winners = [r for r in records if r.status == analytics.WIN]
        if winners:
            note = "🏁 <b>Новый результат в базе:</b>\n" + "\n".join(
                format_record_line(r) for r in winners[:5]
            )
            for sub_id, sub_sess in session.all_sessions():
                if sub_id != user_id and sub_sess.get("subscribed"):
                    try:
                        await bot.send_message(sub_id, note)
                    except Exception as e:
                        logger.info("Не удалось уведомить %s: %s", sub_id, e)

    await state.set_state(BotState.MENU)
    sess = session.load_session(user_id)
    sess["state"] = "MENU"
    session.save_session(user_id, sess)
    await show_screen(
        message.chat.id,
        user_id,
        "\n".join(report),
        keyboards.menu_keyboard(is_admin(user_id), sess.get("subscribed", False)),
    )
    logger.info("User %d: загружено %d записей, %d отклонено", user_id, added, len(errors))


@dp.message(StateFilter(BotState.UPLOAD))
async def handle_upload_wrong(message: Message):
    """Подсказка, если в режиме загрузки прислали не файл."""
    logger.info("User %d: в UPLOAD отправлен не файл", message.from_user.id)
    await message.answer("📤 Ожидается CSV-файл. Отправьте документ или нажмите «Отмена».")


@dp.message(StateFilter(BotState.WAIT_NAME))
async def handle_name(message: Message, state: FSMContext):
    """Приём имени игрока для статистики/ачивок."""
    user_id = message.from_user.id
    name = message.text.strip()
    sess = session.load_session(user_id)
    sess["name"] = name
    session.save_session(user_id, sess)
    await state.set_state(BotState.MENU)

    records = analytics.parse_scores_csv(config.SCORES_CSV)
    found = analytics.player_stats(records, name) is not None
    if not found:
        await show_screen(
            message.chat.id,
            user_id,
            f"Игрок «{name}» пока не найден в базе. Имя сохранено — "
            f"оно будет использовано по умолчанию.",
            keyboards.menu_keyboard(is_admin(user_id), sess.get("subscribed", False)),
        )
        return
    await show_screen(message.chat.id, user_id,
                      analytics.format_achievements(records, name),
                      keyboards.back_keyboard())


@dp.message(StateFilter(BotState.BROADCAST))
async def handle_broadcast(message: Message, state: FSMContext):
    """Рассылка текста подписчикам (только для админов)."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        await state.clear()
        return
    sent = 0
    for sub_id, sub_sess in session.all_sessions():
        if sub_id != user_id and sub_sess.get("subscribed"):
            try:
                await bot.send_message(sub_id, f"📢 {message.text}")
                sent += 1
            except Exception as e:
                logger.info("Рассылка: не доставлено %s: %s", sub_id, e)
    await state.set_state(BotState.MENU)
    await message.answer(f"📢 Рассылка отправлена {sent} подписчикам.")


# ============================================================
# Глобальный обработчик ошибок
# ============================================================
@dp.errors()
async def on_error(event: ErrorEvent) -> bool:
    """
    Ловит любое необработанное исключение в хендлерах.

    Нюанс: без этого одна сетевая ошибка (например, таймаут при отправке
    экрана) «съедала» апдейт молча. Теперь ошибка всегда попадает в
    bot_flight.log, а пользователь получает понятное сообщение вместо
    отсутствия реакции.

    Параметры:
        event - событие ошибки aiogram (содержит update и exception)

    Возвращает:
        True — ошибка обработана, апдейт можно подтвердить
    """
    logger.error("Ошибка при обработке апдейта: %s", event.exception,
                 exc_info=event.exception)
    try:
        if event.update.message:
            await bot.send_message(
                event.update.message.chat.id,
                "⚠️ Временный сбой. Попробуйте ещё раз или отправьте /start.",
            )
        elif event.update.callback_query:
            await event.update.callback_query.answer(
                "⚠️ Временный сбой, попробуйте ещё раз", show_alert=True)
    except Exception as e:  # даже аварийное уведомление не должно ломать бота
        logger.warning("Не удалось уведомить пользователя об ошибке: %s", e)
    return True


# ============================================================
# Запуск
# ============================================================
async def main():
    """Точка входа: запуск long polling."""
    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
