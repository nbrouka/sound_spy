"""
Класс охранника с патрулированием, слуховой и визуальной реакцией.

Охранник - это ИИ-противник, который движется по фиксированному маршруту
и реагирует на звуковые волны и прямое видение агента.

Конечный автомат состояний (FSM):
    Patrol       - обычное патрулирование по маршруту
    Investigating - расследование источника шума или преследование агента
    Returning    - возврат к прерванному маршруту после расследования

Механика:
    - Патрулирование: движение между точками маршрута
    - Слух: реакция на звуковые волны в радиусе слышимости
    - Зрение: проверка прямой видимости агента (без стен на линии)
    - Защита от застревания: автоматический переход к следующей точке
      при отсутствии движения в течение 90 кадров
"""

import math
import pygame

from py_sound_spy.constants import COLORS

# ============================================================
# Параметры охранника
# ============================================================
# Размер спрайта охранника в пикселях.
GUARD_SIZE = 20

# Скорость движения в пикселях за кадр:
GUARD_SPEED_PATROL = 1.6        # при патрулировании (медленно)
GUARD_SPEED_INVESTIGATE = 3.2   # при расследовании (быстро, в 2 раза)

# Радиус зрения охранника в пикселях.
# Если агент попадает в этот радиус и нет стен между ними -
# охранник переходит в состояние Investigating.
GUARD_VIEW_RADIUS = 90

# Дистанция, при которой охранник считается достигшим цели.
# Используется для перехода из Investigating в Returning.
GUARD_CAUGHT_DISTANCE = 18

# Количество кадров без движения, после которого охранник
# автоматически переключается на следующую точку маршрута.
# Защищает от застревания в стенах или углах.
STUCK_FRAME_THRESHOLD = 90

# Скорость затухания слухового индикатора в кадре.
# Значение 0.02 означает, что индикатор полностью исчезнет
# примерно за 50 кадров (0.02 * 50 = 1.0).
HEARING_ALERT_DECAY = 0.02

# ============================================================
# Стены лабиринта (дублируются для автономности модуля)
# ============================================================
# Хотя WALLS определен в constants.py, здесь они дублируются,
# чтобы модуль blind_guard.py мог работать независимо.
# Это упрощает тестирование и повторное использование.
WALLS = [
    pygame.Rect(0, 0, 800, 20),          # верхняя граница
    pygame.Rect(0, 580, 800, 20),        # нижняя граница
    pygame.Rect(0, 0, 20, 600),          # левая граница
    pygame.Rect(780, 0, 20, 600),        # правая граница
    pygame.Rect(200, 120, 20, 200),      # вертикальная стена
    pygame.Rect(360, 40, 20, 200),       # вертикальная стена
    pygame.Rect(520, 200, 20, 200),      # вертикальная стена
    pygame.Rect(140, 340, 200, 20),      # горизонтальная стена
    pygame.Rect(440, 440, 200, 20),      # горизонтальная стена
]


class BlindGuard:
    """
    Охранник с конечным автоматом состояний.

    Состояния:
        Patrol       - движение по фиксированному маршруту
        Investigating - поиск источника звука или преследование агента
        Returning    - возврат к точке, где был прерван патруль

    Атрибуты:
        patrol_points   - список точек маршрута (пиксельные координаты)
        point_index     - текущий индекс точки маршрута
        rect            - прямоугольник охранника (позиция + размер)
        speed_patrol    - скорость при патрулировании
        speed_investigate - скорость при расследовании
        state           - текущее состояние FSM
        alert_target    - цель для движения в состоянии Investigating
        return_index    - точка маршрута, к которой нужно вернуться
        stuck_frames    - счётчик кадров без движения
        hearing_alert   - уровень слухового индикатора (0.0 - 1.0)
    """

    def __init__(self, patrol_points, start_index=0):
        """
        Создаёт охранника с заданным маршрутом патрулирования.

        Параметры:
            patrol_points - список кортежей (x, y) с точками маршрута
            start_index   - индекс начальной точки маршрута
        """
        # Если какая-то точка маршрута попала в стену, ищем ближайшую
        # свободную позицию. Это защищает от некорректного уровня.
        self.patrol_points = []
        for px, py in patrol_points:
            test_rect = pygame.Rect(px, py, GUARD_SIZE, GUARD_SIZE)
            if any(test_rect.colliderect(wall) for wall in WALLS):
                nx, ny = self._nearest_free_cell(px, py)
                self.patrol_points.append((nx, ny))
            else:
                self.patrol_points.append((px, py))

        self.point_index = start_index % len(self.patrol_points)
        start_pos = self.patrol_points[self.point_index]
        self.rect = pygame.Rect(start_pos[0], start_pos[1], GUARD_SIZE, GUARD_SIZE)
        self.speed_patrol = GUARD_SPEED_PATROL
        self.speed_investigate = GUARD_SPEED_INVESTIGATE
        self.state = "Patrol"
        self.alert_target = None
        self.return_index = self.point_index
        self.stuck_frames = 0
        self.last_center = self.rect.center
        self.hearing_alert = 0.0

    def update(self, waves, agent):
        """
        Обновляет состояние охранника на каждом кадре.

        Логика:
            1. Запоминаем старую позицию для детекта застревания
            2. В зависимости от состояния (Patrol/Investigating/Returning)
               выполняем соответствующую логику
            3. Проверяем застревание и затухание слухового индикатора
            4. Возвращаем True, если охранник видит агента (для поимки)

        Параметры:
            waves  - список активных звуковых волн
            agent  - объект агента для проверки видимости

        Возвращает:
            True  - охранник видит агента (можно ловить)
            False - охранник не видит агента
        """
        old_center = self.rect.center

        # Конечный автомат состояний охранника
        match self.state:
            case "Patrol":
                # Движемся к текущей точке маршрута
                target = self.patrol_points[self.point_index]
                self._step_toward(target, self.speed_patrol)
                if self.rect.collidepoint(target):
                    self.point_index = (self.point_index + 1) % len(self.patrol_points)

                # Проверяем все активные волны на предмет попадания в радиус
                for wave in waves:
                    if not wave.active:
                        continue
                    dist = math.hypot(self.rect.centerx - wave.x, self.rect.centery - wave.y)
                    if dist <= wave.radius:
                        self.state = "Investigating"
                        self.alert_target = (wave.x, wave.y)
                        self.return_index = self.point_index
                        self.hearing_alert = 1.0
                        break

                # Проверяем, видит ли охранник агента напрямую
                if self._can_see_agent(agent):
                    self.state = "Investigating"
                    self.alert_target = agent.rect.center
                    self.return_index = self.point_index
                    self.hearing_alert = 1.0

            case "Investigating":
                # Движемся к цели (источник звука или агент)
                if self.alert_target:
                    self._step_toward(self.alert_target, self.speed_investigate)
                    dist_to_alert = math.hypot(
                        self.rect.centerx - self.alert_target[0],
                        self.rect.centery - self.alert_target[1],
                    )
                    # Если дошли до цели или волны затухли - возвращаемся
                    if dist_to_alert < GUARD_CAUGHT_DISTANCE or not any(w.active for w in waves):
                        self.state = "Returning"
                        self.alert_target = None

                # Если видим агента - возвращаем True для поимки
                if self._can_see_agent(agent):
                    return True

            case "Returning":
                # Возвращаемся к точке, где прервали патруль
                target = self.patrol_points[self.return_index]
                self._step_toward(target, self.speed_patrol)
                if self.rect.collidepoint(target):
                    self.state = "Patrol"
                    self.point_index = self.return_index

        # Детект застревания: если позиция не меняется N кадров подряд,
        # переключаемся на следующую точку маршрута
        if self.rect.center == old_center:
            self.stuck_frames += 1
        else:
            self.stuck_frames = 0

        # Затухание слухового индикатора
        if self.hearing_alert > 0.0:
            self.hearing_alert = max(0.0, self.hearing_alert - HEARING_ALERT_DECAY)

        # Если застряли надолго - сбрасываем на следующую точку
        if self.stuck_frames > STUCK_FRAME_THRESHOLD:
            self.point_index = (self.point_index + 1) % len(self.patrol_points)
            self.stuck_frames = 0

        return False

    def _step_toward(self, target, speed):
        """
        Сдвигает охранника к цели, пытаясь скользить вдоль стен.

        Алгоритм:
            1. Пытаемся двигаться по диагонали (полный шаг)
            2. Если блокирует стена - пытаемся двигаться только по X
            3. Если всё ещё блокирует - только по Y
        Это позволяет охраннику обходить препятствия, а не застревать.
        """
        dx = target[0] - self.rect.centerx
        dy = target[1] - self.rect.centery
        dist = math.hypot(dx, dy)
        if dist == 0:
            return
        dx, dy = dx / dist, dy / dist

        new_rect = self.rect.move(dx * speed, dy * speed)
        if not self._center_collides_wall(new_rect):
            self.rect = new_rect
            return

        new_rect_x = self.rect.move(dx * speed, 0)
        if not self._center_collides_wall(new_rect_x):
            self.rect = new_rect_x
            return

        new_rect_y = self.rect.move(0, dy * speed)
        if not self._center_collides_wall(new_rect_y):
            self.rect = new_rect_y

    def _center_collides_wall(self, rect):
        """
        Проверяет, попадает ли центр прямоугольника в любую стену.

        Используется только центр (а не весь rect), чтобы охранник
        мог приближаться к стенам вплотную, не застревая.
        """
        cx, cy = rect.center
        for wall in WALLS:
            if wall.collidepoint(cx, cy):
                return True
        return False

    def _can_see_agent(self, agent):
        """
        Проверяет, видит ли охранник агента.

        Условия видимости:
            1. Дистанция до агента меньше GUARD_VIEW_RADIUS
            2. На линии между охранником и агентом нет стен

        Возвращает:
            True  - агент виден
            False - агент не виден (слишком далеко или есть стена)
        """
        if math.hypot(self.rect.centerx - agent.rect.centerx, self.rect.centery - agent.rect.centery) > GUARD_VIEW_RADIUS:
            return False
        return not self._line_intersects_walls(self.rect.center, agent.rect.center)

    def _line_intersects_walls(self, start, end):
        """
        Проверяет, пересекает ли отрезок между двумя точками стены.

        Алгоритм:
            1. Разбиваем отрезок на N шагов
            2. На каждом шаге проверяем, попадает ли точка в стену
            3. Если хотя бы одна точка попала в стену - отрезок пересекает стену

        Это реализует проверку "прямой видимости" (line of sight).
        """
        steps = max(10, int(math.hypot(end[0] - start[0], end[1] - start[1]) / 10))
        for i in range(1, steps):
            t = i / steps
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            point = pygame.Rect(x - 1, y - 1, 2, 2)
            for wall in WALLS:
                if point.colliderect(wall):
                    return True
        return False

    @staticmethod
    def _nearest_free_cell(px, py):
        """
        Ищет ближайшую свободную позицию к указанной.

        Алгоритм:
            1. Проверяем исходную позицию
            2. Если она в стене - проверяем позиции на расстоянии 1, 5, 9...
            3. Возвращаем первую свободную позицию
        """
        for r in range(1, 120, 4):
            for sx in (-r, 0, r):
                for sy in (-r, 0, r):
                    if sx == 0 and sy == 0:
                        continue
                    nx, ny = px + sx, py + sy
                    test_rect = pygame.Rect(nx, ny, GUARD_SIZE, GUARD_SIZE)
                    if not any(test_rect.colliderect(wall) for wall in WALLS):
                        return nx, ny
        return px, py

    def draw(self, surface):
        """
        Отрисовывает охранника с индикаторами состояния.

        Визуальные элементы:
            1. Красный прямоугольник - сам охранник
            2. Жёлтое кольцо - индикатор тревоги (состояние Investigating)
            3. Пульсирующее жёлтое кольцо - слуховой отклик на звук
        """
        pygame.draw.rect(surface, (230, 50, 50), self.rect, border_radius=4)
        if self.state == "Investigating":
            pygame.draw.circle(surface, (255, 220, 40), self.rect.center, 12, 2)
        if self.hearing_alert > 0.0:
            alpha = int(self.hearing_alert * 220)
            radius = 18 + int((1.0 - self.hearing_alert) * 14)
            indicator_surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(indicator_surf, (255, 255, 120, alpha), (radius, radius), radius, 3)
            surface.blit(indicator_surf, (self.rect.centerx - radius, self.rect.centery - radius))
