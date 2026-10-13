"""
Конфигурация Telegram-бота Sound Spy.

Модуль централизует все пути и параметры, необходимые боту:
    - Чтение токена и списка администраторов из файла .env
    - Пути к данным, выгружаемым игрой (agent_logs.csv, game_flight.log)
    - Пути к рабочим файлам бота (JSON-сессии, лог бота)

Формат .env (py_bot/.env):
    BOT_TOKEN=123456:AA...          # токен от @BotFather
    ADMIN_IDS=123456789,987654321   # необязательно: id администраторов

Важно: файл .env содержит секреты и добавлен в .gitignore репозитория.
"""

import os
from pathlib import Path

# ============================================================
# Корневые директории
# ============================================================
# Каталог самого бота (sound_spy/py_bot/).
BOT_DIR = Path(__file__).resolve().parent

# Каталог репозитория (sound_spy/), нужен для импорта пакета игры
# py_sound_spy при локальном тестировании аналитики.
REPO_ROOT = BOT_DIR.parent

# ============================================================
# Данные игры (выгружаются пользователями или копируются из py_sound_spy/)
# ============================================================
# Файл таблицы рекордов, который ведёт игра (data_io.save_session).
# Подключается к боту: пользователи присылают свои копии, бот склеивает их
# в единую базу.
DATA_DIR = BOT_DIR / "data"
SCORES_CSV = DATA_DIR / "agent_logs.csv"

# Лог игровых событий «чёрный ящик» (game_flight.log из py_sound_spy/).
FLIGHT_LOG = DATA_DIR / "game_flight.log"

# ============================================================
# Рабочие файлы бота
# ============================================================
SESSION_DIR = BOT_DIR / "sessions"   # JSON-сессии по user_id (stateless)
LOG_DIR = BOT_DIR / "logs"           # лог событий бота
BOT_LOG = LOG_DIR / "bot_flight.log"

# ============================================================
# Параметры игры (дублируются из py_sound_spy/constants.py,
# чтобы бот не dependил от pygame и мог работать standalone)
# ============================================================
# Лимит времени на уровень в секундах (TIME_LIMIT_SECONDS в игре).
# Значение продублировано из py_sound_spy/constants.py, чтобы бот не
# зависел от pygame и мог работать standalone.
TIME_LIMIT_SECONDS = 120

# Допустимые значения статуса в таблице рекордов (data_io.save_session).
VALID_STATUSES = ("Победа", "Поимка", "Время вышло")

# Ожидаемый заголовок CSV-файла, который пишет игра.
CSV_HEADER = ["Имя", "Время", "Тревоги", "Статус"]

# ============================================================
# Порог верификации: результат считается правдоподобным,
# если время сессии не превышает лимит уровня с запасом
# ============================================================
MAX_PLAUSIBLE_TIME = TIME_LIMIT_SECONDS * 2


def _load_env(path: Path) -> dict:
    """
    Загружает переменные из .env без сторонних зависимостей.

    Формат: KEY=VALUE, комментарии начинаются с #.
    Переменные уже существующего окружения имеют приоритет.

    Параметры:
        path - путь к .env (может не существовать)

    Возвращает:
        dict с прочитанными парами ключ-значение
    """
    values = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


_ENV = _load_env(BOT_DIR / ".env")

# ============================================================
# Токен и администраторы
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN") or _ENV.get("BOT_TOKEN") or ""

# Список администраторов: любые id из этого списка получают
# доступ к командам /broadcast и /log.
ADMIN_IDS: list[int] = []
_admin_raw = os.environ.get("ADMIN_IDS") or _ENV.get("ADMIN_IDS") or ""
for chunk in _admin_raw.replace(";", ",").split(","):
    chunk = chunk.strip()
    if chunk.isdigit():
        ADMIN_IDS.append(int(chunk))

# Создаём рабочие каталоги, если их ещё нет.
SESSION_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
