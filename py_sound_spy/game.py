"""
Основной игровой цикл игры Sound Spy.

Этот модуль является "сердцем" игры. Он:
    1. Инициализирует Pygame и создаёт окно
    2. Загружает конфигурацию уровня из spy_level.json
    3. Управляет состояниями игры (меню, игра, ввод имени, экран завершения)
    4. Обрабатывает пользовательский ввод (клавиатура)
    5. Обновляет состояние всех игровых объектов
    6. Ведёт логирование событий в game_flight.log
    7. Сохраняет результаты в agent_logs.csv
    8. Контролирует таймер и условия победы/поражения

Игровой цикл работает по принципу "requestAnimationFrame":
    - Обработка событий (events)
    - Обновление состояния (update)
    - Отрисовка (render)
    - Ограничение FPS
"""

import pygame
import sys

from py_sound_spy.constants import (
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    FPS,
    TIME_LIMIT_SECONDS,
    DANGER_RADIUS,
    COLORS,
    WALLS,
    GAME_MESSAGES,
    WALK_RADIUS,
    RUN_RADIUS,
    LEVEL_MATRIX,
)
from py_sound_spy.level import get_tile_at, draw_level
from py_sound_spy.sound_wave import SoundWave
from py_sound_spy.agent import Agent
from py_sound_spy.blind_guard import BlindGuard
from py_sound_spy.ui import draw_menu, draw_overlay_message, draw_danger_indicator, draw_game_over_screen, draw_text_centered
from py_sound_spy.data_io import load_level_config, setup_logging, log_event, save_session
from pathlib import Path


def main():
    """
    Основной игровой цикл.

    Состояния игры:
        MENU       - стартовый экран с правилами и легендой
        PLAY       - активный игровой процесс
        NAME_INPUT - ввод имени игрока после завершения игры
        OVER       - экран завершения (победа/поражение)

    Логика работы:
        1. Загрузка конфигурации уровня из spy_level.json
        2. Настройка логирования
        3. Бесконечный цикл while True
        4. На каждой итерации:
            a. Обработка событий (закрытие окна, нажатия клавиш)
            b. Обновление состояния игры в зависимости от текущего state
            c. Отрисовка соответствующего экрана
            d. Обновление дисплея (pygame.display.flip)
            e. Ограничение FPS (clock.tick)
    """
    # Инициализация Pygame и модуля шрифтов
    pygame.init()
    pygame.font.init()

    # Создание окна игры
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Sound Spy")

    # Часы для контроля FPS
    clock = pygame.time.Clock()

    # Шрифты для интерфейса
    font = pygame.font.Font(None, 24)      # мелкий шрифт (статусы, таймер)
    big_font = pygame.font.Font(None, 52)  # крупный шрифт (заголовки, сообщения)

    # ============================================================
    # Загрузка конфигурации уровня
    # ============================================================
    config_path = Path(__file__).with_name("spy_level.json")
    try:
        config = load_level_config(config_path)
        print(f"Уровень загружен из {config_path}")
    except Exception as e:
        print(f"Ошибка загрузки уровня: {e}. Используются значения по умолчанию.")
        config = {}

    # Обновляем константы из конфигурации, если она загружена
    if config:
        if "level" in config:
            LEVEL_MATRIX[:] = config["level"]
        if "walls" in config:
            WALLS[:] = [pygame.Rect(w["x"], w["y"], w["w"], w["h"]) for w in config["walls"]]

    # ============================================================
    # Настройка логирования
    # ============================================================
    log_path = Path(__file__).with_name("game_flight.log")
    setup_logging(log_path)
    log_event("Игра запущена")

    # ============================================================
    # Переменные состояния игры
    # ============================================================
    state = "MENU"

    win = False
    game_over = False
    caught_by = None
    timeout_reason = False
    start_ticks = 0
    alerts_raised = 0

    guards = []
    waves = []
    agent = None

    player_name = ""
    input_text = ""

    # ============================================================
    # Главный игровой цикл
    # ============================================================
    while True:
        now = pygame.time.get_ticks()

        # --------------------------------------------------------
        # 1. Обработка событий
        # --------------------------------------------------------
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                log_event("Игра закрыта")
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN:
                if state == "MENU":
                    state = "PLAY"
                    start_ticks = pygame.time.get_ticks()
                    agent = Agent(80, 80)
                    alerts_raised = 0

                    if config and "guards" in config:
                        guards = [
                            BlindGuard([tuple(p) for p in g["route"]], 0)
                            for g in config["guards"]
                        ]
                    else:
                        guards = [
                            BlindGuard([(200, 160), (400, 160), (400, 360), (200, 360)], 0),
                            BlindGuard([(620, 120), (620, 320)], 0),
                            BlindGuard([(160, 160), (160, 480), (360, 480), (360, 240)], 0),
                        ]
                    waves = []
                    game_over = False
                    caught_by = None
                    timeout_reason = False
                    log_event("Игра началась")

                elif state == "NAME_INPUT":
                    if event.key == pygame.K_RETURN and input_text.strip():
                        player_name = input_text.strip()
                        csv_path = Path(__file__).with_name("agent_logs.csv")
                        elapsed = (pygame.time.get_ticks() - start_ticks) / 1000
                        status = "Победа" if win else "Поимка"
                        save_session(csv_path, player_name, elapsed, alerts_raised, status)
                        log_event(f"Результат сохранён: {player_name}, {elapsed:.1f}с, {status}")
                        input_text = ""
                        state = "OVER"
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    elif event.key == pygame.K_r:
                        input_text = ""
                        state = "MENU"
                    elif event.key < 256 and event.key >= 32:
                        input_text += event.unicode

                elif state == "OVER" and event.key == pygame.K_r:
                    state = "MENU"

        # --------------------------------------------------------
        # 2. Обновление состояния и отрисовка
        # --------------------------------------------------------
        match state:
            case "MENU":
                draw_menu(screen, font, big_font)

            case "PLAY":
                elapsed = (now - start_ticks) / 1000
                remaining = max(0, TIME_LIMIT_SECONDS - elapsed)

                if not game_over:
                    keys = pygame.key.get_pressed()
                    agent.running = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]

                    up = keys[pygame.K_w] or keys[pygame.K_UP]
                    down = keys[pygame.K_s] or keys[pygame.K_DOWN]
                    left = keys[pygame.K_a] or keys[pygame.K_LEFT]
                    right = keys[pygame.K_d] or keys[pygame.K_RIGHT]

                    moved = False
                    if up:
                        moved = agent.move(0, -1, WALLS)
                    elif down:
                        moved = agent.move(0, 1, WALLS)
                    elif left:
                        moved = agent.move(-1, 0, WALLS)
                    elif right:
                        moved = agent.move(1, 0, WALLS)

                    if moved:
                        log_event(f"Агент совершил шаг в {agent.rect.center}")

                    if moved and now - agent.last_wave_time >= agent.wave_cooldown:
                        tile = get_tile_at(*agent.rect.center)
                        max_radius = WALK_RADIUS if not agent.running else RUN_RADIUS
                        if tile == 1:
                            max_radius *= 2
                        waves.append(SoundWave(agent.rect.centerx, agent.rect.centery, max_radius=max_radius))
                        agent.last_wave_time = now

                    for wave in waves:
                        wave.update()
                    waves = [w for w in waves if w.active]

                    for guard in guards:
                        prev_state = guard.state
                        heard = guard.update(waves, agent)
                        if guard.state == "Investigating" and prev_state != "Investigating":
                            alerts_raised += 1
                            log_event(f"Охранник услышал шум в {guard.rect.center}")
                        if heard:
                            game_over = True
                            win = False
                            caught_by = guard
                            log_event("Агент пойман охранником")
                            break

                    tile_under = get_tile_at(*agent.rect.center)
                    if tile_under == 2:
                        game_over = True
                        win = True
                        log_event("Агент достиг финиша")

                    if remaining <= 0:
                        game_over = True
                        win = False
                        timeout_reason = True
                        log_event("Время вышло")

                draw_level(screen)
                for wave in waves:
                    wave.draw(screen)
                for guard in guards:
                    guard.draw(screen)
                agent.draw(screen)

                danger = 0.0
                for guard in guards:
                    dist = (agent.rect.centerx - guard.rect.centerx) ** 2 + (agent.rect.centery - guard.rect.centery) ** 2
                    if dist < DANGER_RADIUS ** 2:
                        danger = max(danger, 1.0 - (dist ** 0.5) / DANGER_RADIUS)

                if caught_by is not None:
                    draw_overlay_message(screen, GAME_MESSAGES["caught"], font, big_font)
                else:
                    draw_danger_indicator(screen, danger, font)

                status_text = font.render(f"Shift: {GAME_MESSAGES['status_run'] if agent.running else GAME_MESSAGES['status_walk']}", True, COLORS["text"])
                screen.blit(status_text, (30, 10))

                time_text = font.render(f"Время: {remaining:0.1f}", True, COLORS["text"])
                screen.blit(time_text, (WINDOW_WIDTH - time_text.get_width() - 30, 10))

                if game_over and caught_by is None:
                    state = "NAME_INPUT" if win else "OVER"
                elif game_over and caught_by is not None:
                    state = "NAME_INPUT"

            case "NAME_INPUT":
                draw_level(screen)
                for wave in waves:
                    wave.draw(screen)
                for guard in guards:
                    guard.draw(screen)
                agent.draw(screen)

                draw_overlay_message(screen, GAME_MESSAGES["caught"] if not win else GAME_MESSAGES["win"], font, big_font)

                prompt = font.render("Введите имя и нажмите Enter:", True, COLORS["text"])
                screen.blit(prompt, (WINDOW_WIDTH // 2 - prompt.get_width() // 2, WINDOW_HEIGHT // 2 + 40))

                name_surf = font.render(input_text + "|", True, COLORS["alert"])
                screen.blit(name_surf, (WINDOW_WIDTH // 2 - name_surf.get_width() // 2, WINDOW_HEIGHT // 2 + 80))

            case "OVER":
                draw_game_over_screen(screen, win, timeout_reason, font, big_font)

        # --------------------------------------------------------
        # 3. Обновление дисплея и контроль FPS
        # --------------------------------------------------------
        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()
