/**
 * BlindGuard — слепой, но чуткий охранник с конечным автоматом.
 *
 * Порт py_sound_spy/blind_guard.py.
 *
 * Конечный автомат (FSM) — три состояния:
 *   Patrol        — патрулирование по маршруту
 *   Investigating — расследование шума или преследование агента
 *   Returning     — возврат к прерванной точке маршрута
 *
 * Отличие от Python-версии: слух считается по
 * ЭКСПОНЕНЦИАЛЬНОЙ формуле затухания, а не по бинарному радиусу.
 * Охранник слышит волну, если громкость на его расстоянии от эпицентра
 * превышает порог слышимости (см. sound_physics.js).
 */
import { Rect } from './rect.js';
import { loudness, distance, GUARD_HEARING_THRESHOLD } from './sound_physics.js';
import {
    GUARD_SIZE,
    GUARD_SPEED_PATROL,
    GUARD_SPEED_INVESTIGATE,
    GUARD_VIEW_RADIUS,
    GUARD_CAUGHT_DISTANCE,
    STUCK_FRAME_THRESHOLD,
    HEARING_ALERT_DECAY,
    GUARD_STATES,
} from './constants.js';

export class BlindGuard {
    /**
     * @param {[number, number][]} patrolPoints — точки маршрута
     * @param {number} startIndex — начальная точка маршрута
     * @param {Rect[]} walls — стены уровня
     */
    constructor(patrolPoints, startIndex = 0, walls = []) {
        this.walls = walls;
        // Защита уровня: точка маршрута внутри стены сдвигается к свободной
        this.patrolPoints = patrolPoints.map(([px, py]) =>
            this._rectInWalls(px, py) ? BlindGuard._nearestFreeCell(px, py, walls) : [px, py]
        );

        this.pointIndex = startIndex % this.patrolPoints.length;
        const [sx, sy] = this.patrolPoints[this.pointIndex];
        this.rect = new Rect(sx, sy, GUARD_SIZE, GUARD_SIZE);

        this.speedPatrol = GUARD_SPEED_PATROL;
        this.speedInvestigate = GUARD_SPEED_INVESTIGATE;
        this.state = GUARD_STATES.PATROL;
        this.alertTarget = null;
        this.returnIndex = this.pointIndex;
        this.stuckFrames = 0;
        this.lastCenter = this.rect.center;
        this.hearingAlert = 0; // 0.0 … 1.0 — индикатор «услышал!»
    }

    /**
     * Один кадр логики охранника.
     * @param {SoundWave[]} waves — активные волны
     * @param {Agent} agent — агент (для проверки зрения)
     * @returns {boolean} true — охранник видит агента (поимка)
     */
    update(waves, agent) {
        const oldCenter = this.rect.center;

        switch (this.state) {
            case GUARD_STATES.PATROL: {
                const target = this.patrolPoints[this.pointIndex];
                this._stepToward(target, this.speedPatrol);
                if (this.rect.collidepoint(target[0], target[1])) {
                    this.pointIndex = (this.pointIndex + 1) % this.patrolPoints.length;
                }
                // Слух: громкость источника шума на нашем расстоянии
                for (const wave of waves) {
                    if (!wave.active) continue;
                    const d = distance(this.rect.centerx, this.rect.centery, wave.x, wave.y);
                    if (d <= wave.radius && loudness(wave.x, wave.y, this.rect.centerx, this.rect.centery) >= GUARD_HEARING_THRESHOLD) {
                        this._startInvestigating(wave.x, wave.y);
                        break;
                    }
                }
                // Зрение: прямой взгляд на агента
                if (this._canSeeAgent(agent)) {
                    this._startInvestigating(agent.rect.centerx, agent.rect.centery);
                }
                break;
            }

            case GUARD_STATES.INVESTIGATING: {
                if (this.alertTarget) {
                    this._stepToward(this.alertTarget, this.speedInvestigate);
                    const distToAlert = distance(
                        this.rect.centerx, this.rect.centery,
                        this.alertTarget[0], this.alertTarget[1]
                    );
                    if (distToAlert < GUARD_CAUGHT_DISTANCE || !waves.some((w) => w.active)) {
                        this.state = GUARD_STATES.RETURNING;
                        this.alertTarget = null;
                    }
                }
                if (this._canSeeAgent(agent)) {
                    return true; // поимка!
                }
                break;
            }

            case GUARD_STATES.RETURNING: {
                const target = this.patrolPoints[this.returnIndex];
                this._stepToward(target, this.speedPatrol);
                if (this.rect.collidepoint(target[0], target[1])) {
                    this.state = GUARD_STATES.PATROL;
                    this.pointIndex = this.returnIndex;
                }
                break;
            }
        }

        // Детект застревания: позиция не меняется N кадров → следующая точка
        if (this.rect.center[0] === oldCenter[0] && this.rect.center[1] === oldCenter[1]) {
            this.stuckFrames += 1;
        } else {
            this.stuckFrames = 0;
        }

        // Затухание слухового индикатора
        if (this.hearingAlert > 0) {
            this.hearingAlert = Math.max(0, this.hearingAlert - HEARING_ALERT_DECAY);
        }
        if (this.stuckFrames > STUCK_FRAME_THRESHOLD) {
            this.pointIndex = (this.pointIndex + 1) % this.patrolPoints.length;
            this.stuckFrames = 0;
        }

        return false;
    }

    _startInvestigating(targetX, targetY) {
        this.state = GUARD_STATES.INVESTIGATING;
        this.alertTarget = [targetX, targetY];
        this.returnIndex = this.pointIndex;
        this.hearingAlert = 1;
    }

    /** Сдвиг к цели со «скольжением» вдоль стен (по диагонали → X → Y). */
    _stepToward(target, speed) {
        const dx = target[0] - this.rect.centerx;
        const dy = target[1] - this.rect.centery;
        const d = Math.hypot(dx, dy);
        if (d === 0) return;
        const nx = dx / d;
        const ny = dy / d;

        const full = this.rect.move(nx * speed, ny * speed);
        if (!this._centerInWalls(full)) {
            this.rect = full;
            return;
        }
        const stepX = this.rect.move(nx * speed, 0);
        if (!this._centerInWalls(stepX)) {
            this.rect = stepX;
            return;
        }
        const stepY = this.rect.move(0, ny * speed);
        if (!this._centerInWalls(stepY)) {
            this.rect = stepY;
        }
    }

    /** Центр прямоугольника попал в одну из стен? */
    _centerInWalls(rect) {
        const [cx, cy] = rect.center;
        return this.walls.some((wall) => wall.collidepoint(cx, cy));
    }

    _rectInWalls(px, py) {
        const test = new Rect(px, py, GUARD_SIZE, GUARD_SIZE);
        return this.walls.some((wall) => test.colliderect(wall));
    }

    /** Видит агента: в радиусе зрения И нет стен на линии взгляда. */
    _canSeeAgent(agent) {
        const d = Math.hypot(
            this.rect.centerx - agent.rect.centerx,
            this.rect.centery - agent.rect.centery
        );
        if (d > GUARD_VIEW_RADIUS) return false;
        return !this._lineIntersectsWalls(this.rect.center, agent.rect.center);
    }

    /** Прямая видимость: отрезок разбивается на шаги, каждый проверяется. */
    _lineIntersectsWalls(start, end) {
        const steps = Math.max(10, Math.hypot(end[0] - start[0], end[1] - start[1]) / 10);
        for (let i = 1; i < steps; i++) {
            const t = i / steps;
            const x = start[0] + (end[0] - start[0]) * t;
            const y = start[1] + (end[1] - start[1]) * t;
            for (const wall of this.walls) {
                if (wall.collidepoint(Math.floor(x), Math.floor(y))) return true;
            }
        }
        return false;
    }

    /** Ближайшая свободная позиция к точке (статический помощник). */
    static _nearestFreeCell(px, py, walls) {
        for (let r = 1; r < 120; r += 4) {
            for (const sx of [-r, 0, r]) {
                for (const sy of [-r, 0, r]) {
                    if (sx === 0 && sy === 0) continue;
                    const nx = px + sx;
                    const ny = py + sy;
                    const test = new Rect(nx, ny, GUARD_SIZE, GUARD_SIZE);
                    if (!walls.some((wall) => test.colliderect(wall))) {
                        return [nx, ny];
                    }
                }
            }
        }
        return [px, py];
    }
}
