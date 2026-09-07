"""
Функции отрисовки интерфейса игры.

Этот модуль отвечает за все визуальные элементы интерфейса:
    - Стартовый экран с правилами и легендой (draw_menu)
    - Оверлей сообщений (draw_overlay_message)
    - Индикатор уровня опасности (draw_danger_indicator)
    - Финальный экран завершения игры (draw_game_over_screen)
    - Вспомогательные функции для текста и легенды

Все функции принимают surface (поверхность Pygame) и рисуют на ней
соответствующие элементы интерфейса.
"""

import pygame

from py_sound_spy.constants import (
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    COLORS,
    GAME_MESSAGES,
)


def draw_text_centered(surface, text, y, font, color=(240, 240, 240)):
    """
    Отрисовывает текст по центру экрана по горизонтали.

    Параметры:
        surface - поверхность Pygame для отрисовки
        text    - текст для отображения
        y       - вертикальная позиция (пиксели от верха)
        font    - шрифт Pygame для рендеринга текста
        color   - цвет текста в формате RGB
    """
    rendered = font.render(text, True, color)
    surface.blit(rendered, (surface.get_width() // 2 - rendered.get_width() // 2, y))


def draw_legend_item(surface, color, symbol_type, text, x, y, font):
    """
    Отрисовывает элемент легенды: цветной значок + подпись.

    Параметры:
        surface     - поверхность Pygame
        color       - цвет значка в формате RGB
        symbol_type - тип значка: "rect", "circle", "ring", "wall"
        text        - подпись элемента
        x, y        - позиция левого верхнего угла значка
        font        - шрифт для подписи
    """
    size = 14
    match symbol_type:
        case "rect":
            pygame.draw.rect(surface, color, (x, y, size, size))
        case "circle":
            pygame.draw.circle(surface, color, (x + size // 2, y + size // 2), size // 2)
        case "ring":
            pygame.draw.circle(surface, color, (x + size // 2, y + size // 2), size // 2, 2)
        case "wall":
            pygame.draw.rect(surface, (60, 60, 60), (x, y, size, size))
            pygame.draw.rect(surface, (200, 200, 200), (x, y, size, size), 1)

    text_surf = font.render(text, True, (240, 240, 240))
    surface.blit(text_surf, (x + size + 8, y + 1))


def draw_menu(surface, font, big_font):
    """
    Отрисовывает стартовый экран с правилами и легендой.

    Структура экрана:
        - Заголовок "ЗВУКОВОЙ ШПИОН" крупным шрифтом
        - Подзаголовок "Побег из лаборатории"
        - Две колонки: ПРАВИЛА и ЛЕГЕНДА
        - Подсказка "Нажмите любую клавишу для старта"
    """
    surface.fill((20, 20, 20))
    draw_text_centered(surface, GAME_MESSAGES["title"], 70, big_font, COLORS["agent"])
    draw_text_centered(surface, GAME_MESSAGES["subtitle"], 110, font)

    left_x = 80      # позиция левой колонки (правила)
    right_x = 440    # позиция правой колонки (легенда)
    section_y = 150  # вертикальная позиция заголовков колонок

    surface.blit(font.render("ПРАВИЛА", True, COLORS["alert"]), (left_x, section_y))
    surface.blit(font.render("ЛЕГЕНДА", True, COLORS["alert"]), (right_x, section_y))

    rules = [
        "Стрелки — движение по лабиринту",
        "Shift — бег (быстрее, но шум сильнее)",
        "Металл усиливает шум в 2 раза",
        "Доберитесь до зелёной зоны",
        "Охранники реагируют на звук",
        "Охранники видят вас на прямой",
        "Касание — поимка, 120 секунд",
        "R — возврат в меню",
    ]
    for i, line in enumerate(rules):
        surface.blit(font.render(line, True, COLORS["text"]), (left_x, section_y + 28 + i * 24))

    legend_items = [
        (COLORS["agent"], "rect", "Агент — вы, цель: финиш"),
        (COLORS["guard"], "rect", "Охранник — патрулирует"),
        (COLORS["alert"], "ring", "Тревога — расследует шум"),
        ((255, 0, 0), "ring", "Звуковая волна — от шагов"),
        (COLORS["concrete"], "rect", "Бетон — тихий пол"),
        (COLORS["metal"], "rect", "Металл — громкий пол"),
        (COLORS["finish"], "rect", "Финиш — выход"),
        (COLORS["wall"], "wall", "Стена — препятствие"),
    ]
    for i, item in enumerate(legend_items):
        draw_legend_item(surface, item[0], item[1], item[2], right_x, section_y + 28 + i * 24, font)

    draw_text_centered(surface, GAME_MESSAGES["menu_hint"], 390, font, COLORS["alert"])


def draw_overlay_message(surface, message, font, big_font):
    """
    Рисует затемнённый overlay с сообщением по центру экрана.

    Используется при:
        - Поимке агента охранником
        - Других событиях, требующих внимания игрока

    Эффект:
        - Полупрозрачный чёрный overlay (alpha=140)
        - Крупный текст по центру
    """
    overlay = pygame.Surface((surface.get_width(), surface.get_height()), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 140))
    surface.blit(overlay, (0, 0))
    draw_text_centered(surface, message, surface.get_height() // 2 - 10, big_font, COLORS["guard"])


def draw_danger_indicator(surface, danger, font):
    """
    Рисует красный overlay и шкалу уровня опасности.

    Показывается, когда игрок находится рядом с охранником (danger > 0).
    Интенсивность эффекта зависит от близости к охраннику:
        - danger = 0.0   - нет опасности, индикатор скрыт
        - danger = 1.0   - максимальная опасность, полный overlay

    Визуальные элементы:
        1. Красный полупрозрачный overlay (интенсивность зависит от danger)
        2. Шкала "УРОВЕНЬ ОПАСНОСТИ" внизу экрана
        3. Цвет шкалы: жёлтый (опасность < 0.6) или оранжевый (опасность >= 0.6)
    """
    if danger <= 0.0:
        return
    overlay = pygame.Surface((surface.get_width(), surface.get_height()), pygame.SRCALPHA)
    alpha = int(danger * 180)
    overlay.fill((255, 0, 0, alpha))
    surface.blit(overlay, (0, 0))

    bar_width = 220
    bar_height = 18
    bar_x = surface.get_width() // 2 - bar_width // 2
    bar_y = surface.get_height() - 50
    pygame.draw.rect(surface, (40, 40, 40), (bar_x - 2, bar_y - 2, bar_width + 4, bar_height + 4))
    fill = int(bar_width * danger)
    color = (255, 200, 30) if danger < 0.6 else (255, 80, 20)
    pygame.draw.rect(surface, color, (bar_x, bar_y, fill, bar_height))
    pygame.draw.rect(surface, (200, 200, 200), (bar_x, bar_y, bar_width, bar_height), 2)
    label = font.render("УРОВЕНЬ ОПАСНОСТИ", True, (230, 230, 230))
    surface.blit(label, (surface.get_width() // 2 - label.get_width() // 2, bar_y - 28))


def draw_game_over_screen(surface, win, timeout_reason, font, big_font):
    """
    Отрисовывает финальный экран завершения игры.

    Варианты исхода:
        1. timeout_reason=True  - истекло время ("Время вышло!")
        2. win=True             - агент достиг финиша ("ПОБЕДА!")
        3. win=False            - агент пойман ("ПОИМКА!")

    На экране:
        - Крупный текст результата (цвет зависит от исхода)
        - Подсказка "Нажмите R для возврата в меню"
    """
    match (timeout_reason, win):
        case (True, _):
            msg = GAME_MESSAGES["timeout"]
            color = COLORS["alert"]
        case (False, True):
            msg = GAME_MESSAGES["win"]
            color = COLORS["finish"]
        case (False, False):
            msg = "ПОИМКА!"
            color = COLORS["guard"]
    draw_text_centered(surface, msg, 220, big_font, color)
    draw_text_centered(surface, GAME_MESSAGES["menu_restart"], 290, font)
