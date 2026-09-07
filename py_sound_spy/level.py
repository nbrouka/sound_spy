"""
Утилиты для работы с лабиринтом.

Этот модуль отвечает за:
1. Определение типа плитки по пиксельным координатам (get_tile_at)
2. Отрисовку всего уровня: плиток пола и стен (draw_level)

Используемые константы импортируются из constants.py:
    TILE_SIZE      - размер плитки в пикселях
    GRID_COLUMNS   - количество колонок в сетке
    GRID_ROWS      - количество строк в сетке
    LEVEL_MATRIX   - матрица с типами плиток (0, 1, 2)
    COLORS         - палитра цветов
    WALLS          - список прямоугольных стен
"""

import pygame

from py_sound_spy.constants import (
    GRID_COLUMNS,
    GRID_ROWS,
    TILE_SIZE,
    LEVEL_MATRIX,
    COLORS,
    WALLS,
)


def get_tile_at(px, py):
    """
    Возвращает тип тайла по пиксельным координатам.

    Координаты переводим в индексы матрицы:
        gx = px // TILE_SIZE  (номер колонки)
        gy = py // TILE_SIZE  (номер строки)

    Возвращает:
        0 - бетонный пол
        1 - металлическая решётка
        2 - точка финиша
    """
    gx = px // TILE_SIZE
    gy = py // TILE_SIZE
    if 0 <= gx < GRID_COLUMNS and 0 <= gy < GRID_ROWS:
        return LEVEL_MATRIX[gy][gx]
    return 0


def draw_level(surface):
    """
    Отрисовывает плитки лабиринта и граничные стены.

    Проходит по всей матрице уровня и для каждой ячейки рисует
    прямоугольник соответствующего цвета. Затем отрисовывает
    все стены из списка WALLS.
    """
    for gy in range(GRID_ROWS):
        for gx in range(GRID_COLUMNS):
            tile = LEVEL_MATRIX[gy][gx]
            rect = pygame.Rect(gx * TILE_SIZE, gy * TILE_SIZE, TILE_SIZE, TILE_SIZE)
            color = COLORS["concrete"] if tile == 0 else COLORS["metal"] if tile == 1 else COLORS["finish"]
            pygame.draw.rect(surface, color, rect)
            pygame.draw.rect(surface, (60, 60, 60), rect, 1)

    for wall in WALLS:
        pygame.draw.rect(surface, COLORS["wall"], wall)
