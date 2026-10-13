"""
Аналитический движок бота Sound Spy.

Модуль работает с данными, которые выгружает игра, и не содержит
игровой логики — бот является сервисом-помощником для игры, а не её
копией в чате.

Источники данных:
    - agent_logs.csv  - таблица рекордов (Имя, Время, Тревоги, Статус),
                        которую игра дописывает по итогу каждой сессии
    - game_flight.log - «чёрный ящик» с событиями игрового цикла

Функции:
    parse_scores_csv(path)         - разбор CSV-файла рекордов
    parse_scores_text(text)        - разбор CSV из текста (загрузка в чат)
    append_records(records)        - дописывание результатов в общую базу
    leaderboard(records)           - таблица лидеров
    player_stats(records, name)    - личная статистика игрока
    achievements(records, name)    - ачивки игрока
    verify_record(record)          - верификация одного результата
    summarize_flight_log(path)     - сводка по логу игры
    tail_log(path, n)              - последние N строк файла
"""

import csv
import io
import logging
from dataclasses import dataclass
from pathlib import Path

import config

logger = logging.getLogger(__name__)

WIN = "Победа"
CAUGHT = "Поимка"
TIMEOUT = "Время вышло"


# ============================================================
# Модель записи
# ============================================================
@dataclass
class Record:
    """Одна строка таблицы рекордов игровой сессии."""

    name: str      # имя игрока (студента)
    time_sec: float  # время прохождения в секундах
    alerts: int    # количество поднятых охранниками тревог
    status: str    # Победа / Поимка / Время вышло

    def to_row(self) -> list:
        """Преобразует запись в строку CSV."""
        return [self.name, round(self.time_sec, 1), self.alerts, self.status]


# ============================================================
# Парсинг CSV
# ============================================================
def _parse_csv_rows(text: str) -> tuple[list[Record], list[str]]:
    """
    Разбирает текст CSV и валидирует каждую строку.

    Параметры:
        text - содержимое CSV-файла

    Возвращает:
        (records, errors) - список корректных записей и список
        текстовых описаний отклонённых строк
    """
    records: list[Record] = []
    errors: list[str] = []

    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return [], ["Файл пуст"]

    # Проверяем заголовок (игра пишет: Имя,Время,Тревоги,Статус)
    header = [cell.strip() for cell in rows[0]]
    if header != config.CSV_HEADER:
        errors.append(
            f"Неверный заголовок: ожидается «{','.join(config.CSV_HEADER)}», "
            f"получено «{','.join(header)}»"
        )
        return [], errors

    for line_no, row in enumerate(rows[1:], start=2):
        if len(row) != 4:
            errors.append(f"Строка {line_no}: ожидается 4 поля, получено {len(row)}")
            continue
        name, time_raw, alerts_raw, status = (cell.strip() for cell in row)
        try:
            time_sec = float(time_raw)
            alerts = int(alerts_raw)
        except ValueError:
            errors.append(
                f"Строка {line_no}: «Время» и «Тревоги» должны быть числами "
                f"(«{time_raw}», «{alerts_raw}»)"
            )
            continue

        record = Record(name=name, time_sec=time_sec, alerts=alerts, status=status)
        issues = verify_record(record)
        if issues:
            errors.append(f"Строка {line_no}: " + "; ".join(issues))
            continue
        records.append(record)

    return records, errors


def parse_scores_text(text: str) -> tuple[list[Record], list[str]]:
    """
    Разбирает CSV из текста, переданного в чат.

    Параметры:
        text - содержимое CSV-файла

    Возвращает:
        (records, errors)
    """
    return _parse_csv_rows(text)


def parse_scores_csv(path: Path) -> list[Record]:
    """
    Разбирает CSV-файл таблицы рекордов.

    Некорректные строки пропускаются с записью в лог — один битый
    файл не должен ломать работу бота.

    Параметры:
        path - путь к agent_logs.csv

    Возвращает:
        список записей Record (пустой, если файл отсутствует)
    """
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("Не удалось прочитать %s: %s", path, e)
        return []
    records, errors = _parse_csv_rows(text)
    for err in errors:
        logger.info("Пропущена строка в %s: %s", path.name, err)
    return records


def append_records(records: list[Record], path: Path = None) -> int:
    """
    Дописывает проверенные записи в конец общей базы CSV.

    Если файл не существует — создаёт его с заголовком.

    Параметры:
        records - список записей для добавления
        path    - путь к CSV (по умолчанию config.SCORES_CSV)

    Возвращает:
        int - количество реально добавленных строк
    """
    if path is None:
        path = config.SCORES_CSV
    if not records:
        return 0

    file_exists = path.exists() and path.stat().st_size > 0
    path.parent.mkdir(exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(config.CSV_HEADER)
        for record in records:
            writer.writerow(record.to_row())
    return len(records)


# ============================================================
# Верификация результата
# ============================================================
def verify_record(record: Record) -> list[str]:
    """
    Проверяет результат сессии на непротиворечивость.

    Проверки:
        - имя не пустое и не длиннее 32 символов
        - время сессии положительно и не превышает разумный предел
        - число тревог — неотрицательное целое
        - статус из допустимого набора игры

    Параметры:
        record - проверяемая запись

    Возвращает:
        список найденных проблем (пустой, если всё корректно)
    """
    issues = []
    if not record.name:
        issues.append("пустое имя игрока")
    if len(record.name) > 32:
        issues.append("имя длиннее 32 символов")
    if record.time_sec <= 0:
        issues.append("время сессии должно быть больше 0")
    elif record.time_sec > config.MAX_PLAUSIBLE_TIME:
        issues.append(
            f"время {record.time_sec:.1f}с превышает лимит уровня "
            f"({config.TIME_LIMIT_SECONDS}с) более чем вдвое"
        )
    if record.alerts < 0:
        issues.append("число тревог не может быть отрицательным")
    if record.status not in config.VALID_STATUSES:
        issues.append(f"недопустимый статус «{record.status}»")
    return issues


# ============================================================
# Таблица лидеров
# ============================================================
def _rank_key(record: Record):
    """
    Ключ сортировки: победы — по времени (быстрее лучше),
    поражения — по времени выживания (дольше лучше).
    """
    if record.status == WIN:
        return (0, record.time_sec, record.alerts)
    return (1, -record.time_sec, -record.alerts)


def leaderboard(records: list[Record], limit: int = 10) -> list[Record]:
    """
    Возвращает топ игроков из базы результатов.

    Параметры:
        records - все загруженные записи
        limit   - размер таблицы

    Возвращает:
        отсортированный список Record
    """
    return sorted(records, key=_rank_key)[:limit]


def format_leaderboard(records: list[Record], highlight: str = None) -> str:
    """
    Форматирует таблицу лидеров в моноширинный текст для Telegram.

    Параметры:
        records  - записи для отображения
        highlight- имя игрока, чьи строки отмечаются звёздочкой

    Возвращает:
        строка с таблицей (для отправки в теге <pre>)
    """
    rows = leaderboard(records)
    if not rows:
        return "База результатов пуста. Загрузите agent_logs.csv через меню."

    lines = ["#   Имя                  Время   Тревоги  Статус"]
    for i, r in enumerate(rows, start=1):
        mark = "*" if highlight and r.name == highlight else " "
        lines.append(
            f"{mark}{i:<2} {r.name[:18]:<18} {r.time_sec:>6.1f}s {r.alerts:>8}  {r.status}"
        )
    return "\n".join(lines)


# ============================================================
# Личная статистика
# ============================================================
def player_stats(records: list[Record], name: str) -> dict | None:
    """
    Считает статистику игрока по всем его сессиям.

    Параметры:
        records - все загруженные записи
        name    - имя игрока

    Возвращает:
        dict со статистикой или None, если игрок не найден
    """
    mine = [r for r in records if r.name == name]
    if not mine:
        return None

    wins = [r for r in mine if r.status == WIN]
    return {
        "games": len(mine),
        "wins": len(wins),
        "losses": len(mine) - len(wins),
        "winrate": round(100 * len(wins) / len(mine)),
        "best_time": min((r.time_sec for r in wins), default=None),
        "avg_time": round(sum(r.time_sec for r in mine) / len(mine), 1),
        "avg_alerts": round(sum(r.alerts for r in mine) / len(mine), 1),
        "total_alerts": sum(r.alerts for r in mine),
        "best_alerts": min((r.alerts for r in wins), default=None),
    }


def format_stats(stats: dict, name: str) -> str:
    """
    Форматирует личную статистику для отправки в Telegram.

    Параметры:
        stats - результат player_stats
        name  - имя игрока

    Возвращает:
        текстовая сводка
    """
    if stats is None:
        return f"Игрок «{name}» не найден в базе результатов."

    best = f"{stats['best_time']:.1f} с" if stats["best_time"] is not None else "—"
    lines = [
        f"📊 Статистика игрока: {name}",
        "",
        f"Сессий всего: {stats['games']}",
        f"Побед: {stats['wins']} ({stats['winrate']}%)",
        f"Поражений: {stats['losses']}",
        f"Лучшее время: {best}",
        f"Среднее время: {stats['avg_time']:.1f} с",
        f"Среднее число тревог: {stats['avg_alerts']}",
        f"Всего поднято тревог: {stats['total_alerts']}",
    ]
    return "\n".join(lines)


# ============================================================
# Ачивки
# ============================================================
@dataclass
class Achievement:
    """Награда за игровое достижение."""

    id: str
    title: str
    description: str
    earned: bool


def achievements(records: list[Record], name: str) -> list[Achievement]:
    """
    Вычисляет ачивки игрока по его сессиям.

    Правила:
        ghost    «Призрак»        - победа без единой поднятой тревоги
        sprinter «Скороход»       - победа быстрее 60 секунд
        survivor «Выживший»       - победа, несмотря на 3 и более тревоги
        veteran  «Ветеран»        - 5 и более завершённых сессий
        legend   «Легенда лабы»   - 10 и более побед

    Параметры:
        records - все загруженные записи
        name    - имя игрока

    Возвращает:
        список Achievement (всегда всех 5 наград с флагом earned)
    """
    mine = [r for r in records if r.name == name]
    wins = [r for r in mine if r.status == WIN]

    defs = [
        ("ghost", "Призрак", "Победа без единой тревоги", any(r.alerts == 0 for r in wins)),
        ("sprinter", "Скороход", "Победа быстрее 60 секунд",
         any(r.time_sec < 60 for r in wins)),
        ("survivor", "Выживший", "Победа при 3+ тревогах",
         any(r.alerts >= 3 for r in wins)),
        ("veteran", "Ветеран", "5 завершённых сессий", len(mine) >= 5),
        ("legend", "Легенда лаборатории", "10 побед", len(wins) >= 10),
    ]
    return [Achievement(*d) for d in defs]


def format_achievements(records: list[Record], name: str) -> str:
    """
    Форматирует список ачивок игрока для Telegram.

    Параметры:
        records - все загруженные записи
        name    - имя игрока

    Возвращает:
        текстовая сводка по всем ачивкам
    """
    items = achievements(records, name)
    lines = [f"🎖 Ачивки игрока: {name}", ""]
    for a in items:
        mark = "✅" if a.earned else "❌"
        lines.append(f"{mark} {a.title} — {a.description}")
    earned = sum(1 for a in items if a.earned)
    lines.append("")
    lines.append(f"Получено: {earned} из {len(items)}")
    return "\n".join(lines)


# ============================================================
# Работа с логом игры
# ============================================================
def summarize_flight_log(path: Path = None) -> dict:
    """
    Считает сводку по «чёрному ящику» игры.

    Разбирает game_flight.log и подсчитывает ключевые события:
    шаги агента, реакции охранников, поимки, финиши, таймауты.

    Параметры:
        path - путь к логу (по умолчанию config.FLIGHT_LOG)

    Возвращает:
        dict со счётчиками событий
    """
    if path is None:
        path = config.FLIGHT_LOG
    summary = {
        "steps": 0,
        "heard": 0,
        "caught": 0,
        "finished": 0,
        "timeouts": 0,
        "total": 0,
    }
    if not path.exists():
        return summary

    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "|" not in line:
                continue
            summary["total"] += 1
            message = line.split("|", 2)[-1]
            if "совершил шаг" in message:
                summary["steps"] += 1
            elif "услышал шум" in message:
                summary["heard"] += 1
            elif "пойман" in message:
                summary["caught"] += 1
            elif "достиг финиша" in message:
                summary["finished"] += 1
            elif "Время вышло" in message:
                summary["timeouts"] += 1
    except OSError as e:
        logger.warning("Не удалось прочитать лог %s: %s", path, e)
    return summary


def format_log_summary(summary: dict) -> str:
    """
    Форматирует сводку лога игры для Telegram.

    Параметры:
        summary - результат summarize_flight_log

    Возвращает:
        текстовая сводка
    """
    return (
        "🛩 Сводка «чёрного ящика» игры:\n"
        f"Событий записано: {summary['total']}\n"
        f"Шагов агента: {summary['steps']}\n"
        f"Реакций охранников на шум: {summary['heard']}\n"
        f"Поимок: {summary['caught']}\n"
        f"Финишей: {summary['finished']}\n"
        f"Таймаутов: {summary['timeouts']}"
    )


def tail_log(path: Path, lines: int = 20) -> list[str]:
    """
    Возвращает последние N строк файла (хвост лога).

    Параметры:
        path  - путь к файлу
        lines - количество строк

    Возвращает:
        список строк (пустой, если файл отсутствует)
    """
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return content[-lines:]
