/**
 * Agent — агент, управляемый пользователем.
 *
 * Порт py_sound_spy/agent.py.
 * Инкапсуляция: движение и проверка коллизий — внутри move(),
 * генерация шума — внутри makeWave(). Игровой цикл только спрашивает.
 */
import { Rect } from './rect.js';
import { SoundWave } from './sound_wave.js';
import {
    AGENT_SIZE,
    AGENT_SPEED_WALK,
    AGENT_SPEED_RUN,
    WALK_RADIUS,
    RUN_RADIUS,
    WAVE_COOLDOWN_MS,
} from './constants.js';

export class Agent {
    /**
     * @param {number} x — пиксельная координата левого верхнего угла
     * @param {number} y
     */
    constructor(x, y) {
        this.rect = new Rect(x, y, AGENT_SIZE, AGENT_SIZE);
        this.speedWalk = AGENT_SPEED_WALK;
        this.speedRun = AGENT_SPEED_RUN;
        this.running = false; // зажатый Shift
        this.lastWaveTime = 0;
        this.waveCooldown = WAVE_COOLDOWN_MS;
    }

    /**
     * Пытается сдвинуть агента в направлении (dx, dy).
     * @param {number} dx, dy — направление (-1, 0 или 1)
     * @param {Rect[]} walls — стены для проверки коллизий
     * @returns {boolean} true — движение выполнено, false — заблокировано
     */
    move(dx, dy, walls) {
        const speed = this.running ? this.speedRun : this.speedWalk;
        const newRect = this.rect.move(dx * speed, dy * speed);

        for (const wall of walls) {
            if (newRect.colliderect(wall)) {
                return false; // упёрлись в стену — состояние не меняем
            }
        }

        this.rect = newRect;
        return true;
    }

    /**
     * Создаёт звуковую волну от текущего шага (с учётом кулдауна).
     * @param {number} nowMs — текущее время в миллисекундах
     * @param {number} tile — тип плитки под агентом (0 бетон, 1 металл, 2 финиш)
     * @returns {SoundWave|null} новая волна или null, если кулдаун не прошёл
     */
    makeWave(nowMs, tile) {
        if (nowMs - this.lastWaveTime < this.waveCooldown) {
            return null;
        }
        const wave = new SoundWave(this.rect.centerx, this.rect.centery, this.maxRadiusFor(tile));
        this.lastWaveTime = nowMs;
        return wave;
    }

    /** Радиус шума: бег громче ходьбы, металлическая плитка удваивает. */
    maxRadiusFor(tile) {
        let radius = this.running ? RUN_RADIUS : WALK_RADIUS;
        if (tile === 1) {
            radius *= 2;
        }
        return radius;
    }
}
