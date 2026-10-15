/**
 * Game — игровой цикл БЕЗ отрисовки (чистая логика).
 *
 * Порт управляющей части py_sound_spy/game.py: движение, генерация волн,
 * реакции охранников, условия победы/поимки, счётчики сессии.
 * Этот класс одинаково работает в браузере (index.html) и в Node (main.js):
 * от слова «отрисовка» он не зависит.
 */
import { Agent } from './agent.js';
import { BlindGuard } from './blind_guard.js';
import { LabyrinthField } from './labyrinth_field.js';
import { GUARD_STATES } from './constants.js';
import { loudness, GUARD_HEARING_THRESHOLD } from './sound_physics.js';

export class Game {
    /**
     * @param {LabyrinthField} field
     * @param {{x: number, y: number}} agentSpawn
     * @param {{route: [number,number][]}[]} guardConfigs
     */
    constructor(field, agentSpawn, guardConfigs = []) {
        this.field = field;
        this.agent = new Agent(agentSpawn.x, agentSpawn.y);
        this.guards = guardConfigs.map((g) => new BlindGuard(g.route, g.startIndex ?? 0, field.walls));
        this.waves = [];
        this.events = [];        // «чёрный ящик» текущей сессии
        this.stats = { steps: 0, alerts: 0, waves: 0 };
        this.over = false;
        this.result = null;      // 'win' | 'caught'
    }

    /**
     * Один кадр игры.
     * @param {{up,down,left,right,running}} input — состояние управления
     * @param {number} nowMs — текущее время в ms (для кулдауна волн)
     * @returns {boolean} поимлен ли агент на этом кадре
     */
    update(input, nowMs) {
        if (this.over) return false;

        // 1. Движение агента
        let moved = false;
        if (input.up) moved = this.agent.move(0, -1, this.field.walls);
        else if (input.down) moved = this.agent.move(0, 1, this.field.walls);
        else if (input.left) moved = this.agent.move(-1, 0, this.field.walls);
        else if (input.right) moved = this.agent.move(1, 0, this.field.walls);

        if (moved) {
            this.stats.steps += 1;
            this.events.push(`Шаг ${this.stats.steps}: агент в ${this.agent.rect.center}`);
        }

        // 2. Генерация волны (кулдаун + металл ×2)
        if (moved) {
            const tile = this.field.getTileAt(this.agent.rect.centerx, this.agent.rect.centery);
            const wave = this.agent.makeWave(nowMs, tile);
            if (wave) {
                this.waves.push(wave);
                this.stats.waves += 1;
            }
        }

        // 3. Расширение волн и удаление затухших
        for (const wave of this.waves) wave.update();
        this.waves = this.waves.filter((w) => w.active);

        // 4. Логика охранников
        for (const guard of this.guards) {
            const prevState = guard.state;
            const caught = guard.update(this.waves, this.agent);
            if (guard.state === GUARD_STATES.INVESTIGATING && prevState !== GUARD_STATES.INVESTIGATING) {
                this.stats.alerts += 1;
                this.events.push(
                    guard.alertTarget && this._isSoundTarget(guard)
                        ? `Охранник УСЛЫШАЛ шум → тревога #${this.stats.alerts}`
                        : `Охранник УВИДЕЛ агента → тревога #${this.stats.alerts}`
                );
            }
            if (caught) {
                this.over = true;
                this.result = 'caught';
                this.events.push('Охранник увидел агента — ПОИМКА');
                return true;
            }
        }

        // 5. Победа: агент на плитке финиша
        const tileUnder = this.field.getTileAt(this.agent.rect.centerx, this.agent.rect.centery);
        if (tileUnder === 2) {
            this.over = true;
            this.result = 'win';
            this.events.push('Агент достиг точки эвакуации — ПОБЕДА');
        }
        return false;
    }

    /** Цель тревоги была эпицентром одной из активных волн? */
    _isSoundTarget(guard) {
        if (!guard.alertTarget) return false;
        const [tx, ty] = guard.alertTarget;
        return this.waves.some(
            (w) => Math.hypot(w.x - tx, w.y - ty) < 1 &&
                   loudness(w.x, w.y, guard.rect.centerx, guard.rect.centery) >= GUARD_HEARING_THRESHOLD
        );
    }
}
