/**
 * SoundWave — круговая звуковая волна от шага агента.
 *
 * Порт py_sound_spy/sound_wave.py.
 * Волна расширяется от эпицентра, пока не достигнет max_radius,
 * затем деактивируется и удаляется из списка активных волн.
 */
import { WAVE_SPEED } from './constants.js';

export class SoundWave {
    /**
     * @param {number} x — центр волны по X (эпицентр)
     * @param {number} y — центр волны по Y
     * @param {number} maxRadius — максимальный радиус до затухания
     */
    constructor(x, y, maxRadius = 200) {
        this.x = x;
        this.y = y;
        this.radius = 1;
        this.maxRadius = maxRadius;
        this.speed = WAVE_SPEED;
        this.active = true;
    }

    /** Один кадр расширения. */
    update() {
        this.radius += this.speed;
        if (this.radius >= this.maxRadius) {
            this.active = false;
        }
    }

    /** true, если точка (px, py) находится внутри текущего радиуса волны. */
    reaches(px, py) {
        return Math.hypot(px - this.x, py - this.y) <= this.radius;
    }

    /** Прозрачность для Canvas: 1.0 у эпицентра → 0.0 на краю. */
    get alpha() {
        return Math.max(0, 1 - this.radius / this.maxRadius);
    }
}
