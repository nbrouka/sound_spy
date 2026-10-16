/**
 * widget.js — веб-виджет «Звуковой шпион» на HTML5 Canvas.
 *
 * Здесь только ПРЕДСТАВЛЕНИЕ и ввод:
 *   - игровой цикл через requestAnimationFrame (фиксированный шаг симуляции);
 *   - ввод с клавиатуры через массив-флаги (опрос состояния, без задержек ОС);
 *   - отрисовка уровня в радиусе видимости, сущностей и звуковых волн;
 *   - вызов вызываемых сценариев (кнопки + консоль).
 *
 * Вся игровая логика — в ядре: ../js_sound_spy/js/*
 */
import { Game } from '../../js_sound_spy/js/game.js';
import { LabyrinthField } from '../../js_sound_spy/js/labyrinth_field.js';
import {
    COLORS, TILE_SIZE, LEVEL_MATRIX, WALL_DATA, AGENT_SPAWN,
    GUARD_VIEW_RADIUS, GUARD_STATES,
} from '../../js_sound_spy/js/constants.js';
import { createScenarios } from './scenarios.js';

const GUARD_CONFIGS = [
    { route: [[200, 160], [400, 160], [400, 360], [200, 360]] },
    { route: [[620, 120], [620, 320]] },
    { route: [[160, 160], [160, 480], [360, 480], [360, 240]] },
];

// Радиус видимости вокруг агента: всё, что дальше, скрыто «туманом».
const VISIBLE_RADIUS = 150;
// Фиксированный шаг симуляции (60 Гц) — ядро считает «в кадрах».
const FRAME_MS = 1000 / 60;

export class Widget {
    /**
     * @param {HTMLCanvasElement} canvas
     * @param {HTMLElement} resultBox — элемент для сообщения о финале партии
     */
    constructor(canvas, resultBox) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.resultBox = resultBox;
        this.field = new LabyrinthField(LEVEL_MATRIX, WALL_DATA);

        // --- состояние виджета (сценарии меняют эти поля) ---
        this.showFog = true;      // туман видимости
        this.timeScale = 1;       // множитель времени
        this.paused = false;

        // --- управление ---
        this.keys = {};           // массив-флаги зажатых клавиш
        this._bindInput();

        this.restart();
        this.scenarios = createScenarios(this);

        // «Игровые часы» симуляции, мс (от них зависит кулдаун волн в ядре)
        this.simNowMs = 0;
        this.lastFrameTime = performance.now();
        this.accumulator = 0;

        requestAnimationFrame(this.loop);
    }

    restart() {
        this.game = new Game(this.field, AGENT_SPAWN, GUARD_CONFIGS);
        this.waves = this.game.waves;   // ссылка на список активных волн ядра
        this.agent = this.game.agent;
        this.guards = this.game.guards;
        this.resultBox.textContent = '';
        this.resultBox.className = 'result';
    }

    _bindInput() {
        addEventListener('keydown', (e) => {
            const k = e.key.toLowerCase();
            this.keys[k] = true;
            if (k === 'r') this.restart();
            if (['w', 'a', 's', 'd', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(k)) {
                e.preventDefault(); // блокируем скролл страницы
            }
        });
        addEventListener('keyup', (e) => { this.keys[e.key.toLowerCase()] = false; });
    }

    _readInput() {
        const k = (name) => this.keys[name] === true;
        return {
            up: k('w') || k('arrowup') || k('ц'),
            down: k('s') || k('arrowdown') || k('ы'),
            left: k('a') || k('arrowleft') || k('ф'),
            right: k('d') || k('arrowright') || k('в'),
            running: k('shift'),
        };
    }

    /** Один шаг симуляции фиксированной длительности. */
    step() {
        if (this.game.over) return;
        const input = this._readInput();
        this.agent.running = input.running;
        this.game.update(input, this.simNowMs);
        this.waves = this.game.waves; // ядро пересобирает список активных волн
        if (this.game.over) this._showResult();
    }

    /** Игровой цикл: фиксированный шаг симуляции + рендер каждый кадр. */
    loop = (now) => {
        const deltaMs = Math.min(now - this.lastFrameTime, 100); // защита от «прыжков»
        this.lastFrameTime = now;

        if (!this.paused) {
            this.accumulator += deltaMs * this.timeScale;
            this.simNowMs += deltaMs * this.timeScale;
            while (this.accumulator >= FRAME_MS) {
                this.step();
                this.accumulator -= FRAME_MS;
            }
        }

        this.render();
        this._updateHud();
        requestAnimationFrame(this.loop);
    };

    // ==================== ОТРИСОВКА ====================

    render() {
        const { ctx } = this;
        const cx = this.agent.rect.centerx;
        const cy = this.agent.rect.centery;

        ctx.fillStyle = '#000';                       // экран залит чёрным
        ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        if (this.showFog) {
            this._drawTilesInRadius(cx, cy);          // уровень — только рядом с агентом
        } else {
            this._drawAllTiles();
        }
        this._drawWalls(cx, cy);
        this._drawWaves();
        this._drawGuards();
        this._drawAgent();
        this._drawViewCircles();
    }

    _drawTilesInRadius(cx, cy) {
        const { ctx } = this;
        for (let row = 0; row < this.field.rows; row++) {
            for (let col = 0; col < this.field.columns; col++) {
                const tile = this.field.matrix[row][col];
                if (tile === 0) continue;
                const x = col * TILE_SIZE;
                const y = row * TILE_SIZE;
                const dx = x + TILE_SIZE / 2 - cx;
                const dy = y + TILE_SIZE / 2 - cy;
                if (Math.hypot(dx, dy) > VISIBLE_RADIUS) continue; // вне видимости
                ctx.fillStyle = tile === 1 ? COLORS.metal : COLORS.finish;
                ctx.fillRect(x, y, TILE_SIZE - 1, TILE_SIZE - 1);
            }
        }
    }

    _drawAllTiles() {
        const { ctx } = this;
        for (let row = 0; row < this.field.rows; row++) {
            for (let col = 0; col < this.field.columns; col++) {
                const tile = this.field.matrix[row][col];
                if (tile === 0) continue;
                ctx.fillStyle = tile === 1 ? COLORS.metal : COLORS.finish;
                ctx.fillRect(col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE - 1, TILE_SIZE - 1);
            }
        }
    }

    _drawWalls(cx, cy) {
        const { ctx } = this;
        ctx.fillStyle = '#0a0a0a';
        for (const wall of this.field.walls) {
            if (this.showFog && Math.hypot(wall.centerx - cx, wall.centery - cy) > VISIBLE_RADIUS) continue;
            ctx.fillRect(wall.x, wall.y, wall.w, wall.h);
        }
    }

    /** Сценарий «акустика»: расширяющиеся круги rgba(255,0,0,alpha). */
    _drawWaves() {
        const { ctx } = this;
        for (const wave of this.waves) {
            ctx.strokeStyle = `rgba(255, 0, 0, ${wave.alpha.toFixed(3)})`;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(wave.x, wave.y, wave.radius, 0, Math.PI * 2);
            ctx.stroke();
        }
    }

    _drawGuards() {
        const { ctx } = this;
        for (const guard of this.guards) {
            ctx.fillStyle = COLORS.guard;
            ctx.fillRect(guard.rect.x, guard.rect.y, guard.rect.w, guard.rect.h);

            // индикатор тревоги над головой (состояние Investigating)
            if (guard.state === GUARD_STATES.INVESTIGATING) {
                const pulse = 10 + Math.sin(performance.now() / 90) * 3;
                ctx.strokeStyle = COLORS.alert;
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(guard.rect.centerx, guard.rect.y - 16, pulse, 0, Math.PI * 2);
                ctx.stroke();
            }
            // индикатор «услышал!» — пульсирующее кольцо вокруг охранника
            if (guard.hearingAlert > 0) {
                const r = 16 + (1 - guard.hearingAlert) * 12;
                ctx.strokeStyle = `rgba(255, 255, 120, ${(guard.hearingAlert * 0.9).toFixed(3)})`;
                ctx.beginPath();
                ctx.arc(guard.rect.centerx, guard.rect.centery, r, 0, Math.PI * 2);
                ctx.stroke();
            }
        }
    }

    _drawAgent() {
        const { ctx } = this;
        ctx.fillStyle = this.agent.running ? '#7ec8ff' : COLORS.agent;
        ctx.fillRect(this.agent.rect.x, this.agent.rect.y, this.agent.rect.w, this.agent.rect.h);
    }

    /** Тонкие круги радиуса зрения — «антенны» охранников. */
    _drawViewCircles() {
        const { ctx } = this;
        ctx.strokeStyle = 'rgba(230, 50, 50, 0.10)';
        for (const guard of this.guards) {
            ctx.beginPath();
            ctx.arc(guard.rect.centerx, guard.rect.centery, GUARD_VIEW_RADIUS, 0, Math.PI * 2);
            ctx.stroke();
        }
    }

    // ==================== HUD ====================

    _updateHud() {
        document.querySelector('#mode').textContent = this.agent.running ? 'БЕГ' : 'ХОДЬБА';
        document.querySelector('#steps').textContent = this.game.stats.steps;
        document.querySelector('#waves').textContent = this.game.stats.waves;
        document.querySelector('#alerts').textContent = this.game.stats.alerts;
        document.querySelector('#guards').textContent =
            this.guards.map((g) => g.state[0]).join('/');
    }

    _showResult() {
        if (this.game.result === 'win') {
            this.resultBox.textContent = 'ПОБЕДА! Нажмите R';
            this.resultBox.className = 'result win';
        } else {
            this.resultBox.textContent = 'ПОИМКА! Нажмите R';
            this.resultBox.className = 'result lose';
        }
    }
}

// ==================== ЗАПУСК ====================
const canvas = document.querySelector('#game');
const resultBox = document.querySelector('#result');
const widget = new Widget(canvas, resultBox);

// кнопки сценариев: data-scenario="loudWave" → scenarios.loudWave()
for (const btn of document.querySelectorAll('[data-scenario]')) {
    btn.addEventListener('click', () => {
        const name = btn.dataset.scenario;
        widget.scenarios[name]();
    });
}

// API для консоли: SoundSpy.scenarios.alarmAll()
window.SoundSpy = { widget, scenarios: widget.scenarios };
console.log('SoundSpy готов. Сценарии: SoundSpy.scenarios.alarmAll(), .loudWave(400,300), .calm()');
