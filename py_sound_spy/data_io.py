"""
Утилиты для работы с внешними данными: загрузка конфигурации уровня,
логирование игровых событий и сохранение результатов в CSV.

Функции:
    load_level_config(path)       - загрузка и валидация spy_level.json
    setup_logging(log_path)       - настройка логирования в файл
    save_session(csv_path, ...)   - запись результата сессии в agent_logs.csv
"""

import json
import logging
import csv
from pathlib import Path


def load_level_config(path: Path) -> dict:
    """
    Загружает и валидирует файл конфигурации уровня spy_level.json.

    Параметры:
        path - путь к файлу spy_level.json

    Возвращает:
        dict с ключами: level, exit, guards, walls

    Исключения:
        FileNotFoundError - если файл не найден
        ValueError - если структура файла повреждена или отсутствуют поля
    """
    if not path.exists():
        raise FileNotFoundError(f"Файл {path} не найден")

    with open(path, "r", encoding="utf-8") as f:
        try:
            config = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Ошибка парсинга JSON: {e}")

    _validate_config(config)
    return config


def _validate_config(config: dict) -> None:
    """
    Проверяет корректность структуры конфигурации уровня.

    Проверки:
        - presence обязательных полей
        - типы и размеры матрицы уровня
        - корректность координат стен
        - наличие маршрутов у охранников
    """
    required_keys = ["level", "guards", "exit", "walls"]
    missing = [k for k in required_keys if k not in config]
    if missing:
        raise ValueError(f"В конфигурации отсутствуют поля: {missing}")

    level = config["level"]
    if not isinstance(level, list) or not level:
        raise ValueError("Поле 'level' должно быть непустым списком")
    for row in level:
        if not isinstance(row, list) or len(row) != len(level[0]):
            raise ValueError("Каждая строка 'level' должна быть списком одинаковой длины")
        for cell in row:
            if cell not in (0, 1, 2):
                raise ValueError(f"Недопустимое значение ячейки уровня: {cell}")

    for i, guard in enumerate(config["guards"]):
        if "route" not in guard or not isinstance(guard["route"], list):
            raise ValueError(f"У охранника #{i} отсутствует или неверное поле 'route'")
        for point in guard["route"]:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError(f"Некорректная точка маршрута у охранника #{i}: {point}")

    exit_coords = config["exit"]
    if "x" not in exit_coords or "y" not in exit_coords:
        raise ValueError("Поле 'exit' должно содержать 'x' и 'y'")

    for i, wall in enumerate(config["walls"]):
        for key in ("x", "y", "w", "h"):
            if key not in wall:
                raise ValueError(f"У стены #{i} отсутствует поле '{key}'")


def setup_logging(log_path: Path) -> None:
    """
    Настраивает модуль logging для записи в файл.

    Параметры:
        log_path - путь к файлу лога game_flight.log

    Формат записи:
        HH:MM:SS | LEVEL | MESSAGE
    """
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def log_event(message: str) -> None:
    """
    Записывает событие в лог-файл.

    Параметры:
        message - текстовое описание события
    """
    logging.info(message)


def save_session(csv_path: Path, name: str, time_sec: float, alerts: int, status: str) -> None:
    """
    Дописывает результат игровой сессии в CSV-файл.

    Если файл не существует или пуст - создаёт его с заголовком.

    Параметры:
        csv_path  - путь к agent_logs.csv
        name      - имя игрока
        time_sec  - длительность сессии в секундах
        alerts    - количество поднятых тревог
        status    - итоговый статус: "Победа", "Поимка", "Время вышло"
    """
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Имя", "Время", "Тревоги", "Статус"])
        writer.writerow([name, round(time_sec, 1), alerts, status])
