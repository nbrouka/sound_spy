/**
 * scenarios.js — вызываемые сценарии веб-виджета.
 *
 * Сценарий — именованная функция, которая меняет поведение или состояние
 * виджета. Каждый сценарий можно вызвать:
 *   1. из консоли браузера:  SoundSpy.scenarios.alarmAll();
 *   2. по кнопке на панели (data-scenario="alarmAll");
 *   3. из другого сценария.
 *
 * Ядро сценариев не знает про Canvas — только про состояние игры,
 * поэтому их можно тестировать и переиспользовать.
 */

import { SoundWave } from '../../js_sound_spy/js/sound_wave.js';
import { GUARD_STATES } from '../../js_sound_spy/js/constants.js';

/**
 * @param {object} widget — экземпляр Widget (даёт доступ к игре и состоянию)
 * @returns {object} реестр сценариев
 */
export function createScenarios(widget) {

    /** Громкая волна в точке (x, y) — «крик» агента. */
    function loudWave(x = 400, y = 300, radius = 80) {
        widget.game.waves.push(new SoundWave(x, y, radius));
        return `Громкая волна (${x}, ${y}), радиус ${radius}`;
    }

    /** Тревога у всех охранников: переход в Investigating к агенту. */
    function alarmAll() {
        for (const guard of widget.guards) {
            guard._startInvestigating(widget.agent.rect.centerx, widget.agent.rect.centery);
        }
        return 'Все охранники переведены в тревогу';
    }

    /** Штиль: все охранники возвращаются к патрулированию. */
    function calm() {
        for (const guard of widget.guards) {
            guard.state = GUARD_STATES.PATROL;
            guard.alertTarget = null;
            guard.hearingAlert = 0;
        }
        return 'Охранники вернулись к патрулированию';
    }

    /** Туман видимости вкл/выкл. */
    function toggleFog() {
        widget.showFog = !widget.showFog;
        return widget.showFog ? 'Туман включён' : 'Туман выключен';
    }

    /** Замедление симуляции (множитель времени). */
    function slowMotion(factor = 0.35) {
        widget.timeScale = factor;
        return `Замедление ×${factor}`;
    }

    /** Ускорение симуляции. */
    function speedUp(factor = 2.5) {
        widget.timeScale = factor;
        return `Ускорение ×${factor}`;
    }

    /** Пауза / продолжение. */
    function pause() {
        widget.paused = !widget.paused;
        return widget.paused ? 'Пауза' : 'Продолжаем';
    }

    /** Рестарт партии. */
    function restart() {
        widget.restart();
        return 'Новая партия';
    }

    return {
        loudWave,
        alarmAll,
        calm,
        toggleFog,
        slowMotion,
        speedUp,
        pause,
        restart,
    };
}
