"""
Основной игровой цикл игры Sound Spy.

Этот модуль является "сердцем" игры. Он:
    1. Инициализирует Pygame и создаёт окно
    2. Управляет состояниями игры (меню, игра, экран завершения)
    3. Обрабатывает пользовательский ввод (клавиатура)
    4. Обновляет состояние всех игровых объектов
    5. Отрисовывает все элементы на экране
    6. Контролирует таймер и условия победы/поражения

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
)
from py_sound_spy.level import get_tile_at, draw_level
from py_sound_spy.sound_wave import SoundWave
from py_sound_spy.agent import Agent
from py_sound_spy.blind_guard import BlindGuard
from py_sound_spy.ui import draw_menu, draw_overlay_message, draw_danger_indicator, draw_game_over_screen


def main():
    """
    Основной игровой цикл.

    Состояния игры:
        MENU   - стартовый экран с правилами и легендой
        PLAY   - активный игровой процесс
        OVER   - экран завершения (победа/поражение)

    Логика работы:
        1. Бесконечный цикл while True
        2. На каждой итерации:
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
    # Переменные состояния игры
    # ============================================================
    # Текущее состояние игрового цикла (MENU/PLAY/OVER)
    state = "MENU"

    # Флаг победы (True) или поражения (False)
    win = False

    # Флаг окончания игры (True когда игра завершена)
    game_over = False

    # Объект охранника, который поймал агента (или None)
    caught_by = None

    # Флаг истечения времени (True если время вышло)
    timeout_reason = False

    # Время начала игры в миллисекундах (для таймера)
    start_ticks = 0

    # Игровые объекты (создаются при старте игры)
    guards = []   # список охранников
    waves = []    # список активных звуковых волн
    agent = None  # объект агента

    # ============================================================
    # Главный игровой цикл
    # ============================================================
    while True:
        # Текущее время в миллисекундах (для таймера и кулдаунов)
        now = pygame.time.get_ticks()

        # --------------------------------------------------------
        # 1. Обработка событий
        # --------------------------------------------------------
        for event in pygame.event.get():
            # Закрытие окна - завершение программы
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            # Обработка нажатий клавиш
            if event.type == pygame.KEYDOWN:
                # В меню: любая клавиша начинает игру
                if state == "MENU":
                    state = "PLAY"
                    start_ticks = pygame.time.get_ticks()
                    agent = Agent(80, 80)
                    guards = [
                        BlindGuard([(200, 160), (400, 160), (400, 360), (200, 360)], 0),
                        BlindGuard([(620, 120), (620, 320)], 0),
                        BlindGuard([(160, 160), (160, 480), (360, 480), (360, 240)], 0),
                    ]
                    waves = []
                    game_over = False
                    caught_by = None
                    timeout_reason = False

                # На экране завершения: R возвращает в меню
                elif state == "OVER" and event.key == pygame.K_r:
                    state = "MENU"

                # Во время игры при поимке: R возвращает в меню
                elif state == "PLAY" and game_over and caught_by is not None and event.key == pygame.K_r:
                    state = "MENU"

        # --------------------------------------------------------
        # 2. Обновление состояния и отрисовка
        # --------------------------------------------------------
        # Используем match/case для обработки состояний игры
        match state:
            case "MENU":
                # Отрисовываем стартовый экран
                draw_menu(screen, font, big_font)

            case "PLAY":
                # Вычисляем прошедшее и оставшееся время
                elapsed = (now - start_ticks) / 1000
                remaining = max(0, TIME_LIMIT_SECONDS - elapsed)

                # Если игра не завершена - обрабатываем ввод
                if not game_over:
                    # Считываем состояние всех клавиш
                    keys = pygame.key.get_pressed()

                    # Режим бега (зажатый Shift)
                    agent.running = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]

                    # Направления движения (стрелки или WASD)
                    up = keys[pygame.K_w] or keys[pygame.K_UP]
                    down = keys[pygame.K_s] or keys[pygame.K_DOWN]
                    left = keys[pygame.K_a] or keys[pygame.K_LEFT]
                    right = keys[pygame.K_d] or keys[pygame.K_RIGHT]

                    # Пытаемся двинуться в выбранном направлении
                    moved = False
                    if up:
                        moved = agent.move(0, -1, WALLS)
                    elif down:
                        moved = agent.move(0, 1, WALLS)
                    elif left:
                        moved = agent.move(-1, 0, WALLS)
                    elif right:
                        moved = agent.move(1, 0, WALLS)

                    # Если движение было и прошёл кулдаун - создаём волну
                    if moved and now - agent.last_wave_time >= agent.wave_cooldown:
                        tile = get_tile_at(*agent.rect.center)
                        # Радиус волны зависит от режима движения
                        max_radius = WALK_RADIUS if not agent.running else RUN_RADIUS
                        # Металл усиливает шум в 2 раза
                        if tile == 1:
                            max_radius *= 2
                        waves.append(SoundWave(agent.rect.centerx, agent.rect.centery, max_radius=max_radius))
                        agent.last_wave_time = now

                    # Обновляем все волны и удаляем неактивные
                    for wave in waves:
                        wave.update()
                    waves = [w for w in waves if w.active]

                    # Обновляем охранников и проверяем, видят ли они агента
                    for guard in guards:
                        if guard.update(waves, agent):
                            game_over = True
                            win = False
                            caught_by = guard
                            break

                    # Если ещё не конец игры - проверяем столкновения
                    if not game_over:
                        for guard in guards:
                            if agent.rect.colliderect(guard.rect):
                                game_over = True
                                win = False
                                caught_by = guard
                                break

                    # Проверяем, достиг ли агент финиша
                    tile_under = get_tile_at(*agent.rect.center)
                    if tile_under == 2:
                        game_over = True
                        win = True

                    # Проверяем, не истекло ли время
                    if remaining <= 0:
                        game_over = True
                        win = False
                        timeout_reason = True

                # Отрисовываем игровое поле
                draw_level(screen)
                for wave in waves:
                    wave.draw(screen)
                for guard in guards:
                    guard.draw(screen)
                agent.draw(screen)

                # Вычисляем уровень опасности от всех охранников
                danger = 0.0
                for guard in guards:
                    dist = (agent.rect.centerx - guard.rect.centerx) ** 2 + (agent.rect.centery - guard.rect.centery) ** 2
                    if dist < DANGER_RADIUS ** 2:
                        danger = max(danger, 1.0 - (dist ** 0.5) / DANGER_RADIUS)

                # Если агент пойман - показываем overlay, иначе индикатор опасности
                if caught_by is not None:
                    draw_overlay_message(screen, GAME_MESSAGES["caught"], font, big_font)
                else:
                    draw_danger_indicator(screen, danger, font)

                # Отрисовываем HUD (статус бега и таймер)
                status_text = font.render(f"Shift: {GAME_MESSAGES['status_run'] if agent.running else GAME_MESSAGES['status_walk']}", True, COLORS["text"])
                screen.blit(status_text, (30, 10))

                time_text = font.render(f"Время: {remaining:0.1f}", True, COLORS["text"])
                screen.blit(time_text, (WINDOW_WIDTH - time_text.get_width() - 30, 10))

                # Если игра завершена и это не поимка - переходим в экран OVER
                if game_over and caught_by is None:
                    state = "OVER"

            case "OVER":
                # Отрисовываем финальный экран
                draw_game_over_screen(screen, win, timeout_reason, font, big_font)

        # --------------------------------------------------------
        # 3. Обновление дисплея и контроль FPS
        # --------------------------------------------------------
        pygame.display.flip()  # показываем отрисованный кадр
        clock.tick(FPS)        # ограничиваем FPS


# Стандартный Python-паттерн для скриптов
if __name__ == "__main__":
    main()
