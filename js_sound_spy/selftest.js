/**
 * Самопроверка ядра — аналог py_bot/selftest.py, но для JS-версии.
 * Запуск:  node selftest.js
 *
 * Проверяются три требования варианта 31:
 *   1. ООП-структура: Agent, BlindGuard, SoundWave, LabyrinthField
 *   2. Экспоненциальное затухание звука (теорема Пифагора)
 *   3. Конечный автомат охранника: Patrol → Investigating → Returning
 */

import { Rect } from './js/rect.js';
import { distance, intensityAt, loudness, audibleRadius } from './js/sound_physics.js';
import { SoundWave } from './js/sound_wave.js';
import { Agent } from './js/agent.js';
import { BlindGuard } from './js/blind_guard.js';
import { LabyrinthField } from './js/labyrinth_field.js';
import { Game } from './js/game.js';
import { GUARD_STATES, WALK_RADIUS, RUN_RADIUS, WAVE_COOLDOWN_MS } from './js/constants.js';

let passed = 0;
let failed = 0;
const failures = [];

function check(name, condition) {
    if (condition) {
        passed += 1;
        console.log(`  ✅ ${name}`);
    } else {
        failed += 1;
        failures.push(name);
        console.log(`  ❌ ${name}`);
    }
}

function approx(a, b, eps = 1e-9) {
    return Math.abs(a - b) < eps;
}

// ============================================================
console.log('1. Rect (порт pygame.Rect)');
// ============================================================
const r1 = new Rect(0, 0, 20, 20);
const r2 = new Rect(10, 10, 20, 20);
const r3 = new Rect(100, 100, 20, 20);

check('colliderect: пересечение есть', r1.colliderect(r2) === true);
check('colliderect: далеко — нет пересечения', r1.colliderect(r3) === false);
check('collidepoint: центр внутри', r1.collidepoint(10, 10) === true);
check('collidepoint: 20 не внутри (полуоткрытый интервал)', r1.collidepoint(20, 10) === false);
check('center: (10, 10)', r1.center[0] === 10 && r1.center[1] === 10);
const moved = r1.move(5, 0);
check('move возвращает НОВЫЙ объект', moved !== r1 && moved.x === 5 && r1.x === 0);

// ============================================================
console.log('2. Физика звука: Пифагор и экспоненциальное затухание');
// ============================================================
check('distance: 3-4-5 = 5', approx(distance(0, 0, 3, 4), 5));
check('distance: одинарные точки = 0', approx(distance(7, 7, 7, 7), 0));
check('intensityAt(0) = 1.0', approx(intensityAt(0), 1.0));
check('intensityAt(50) = exp(-1)', approx(intensityAt(50), Math.exp(-1)));
check('затухание монотонно убывает', intensityAt(10) > intensityAt(20) && intensityAt(20) > intensityAt(40));
check('на расстоянии 100 громкость < 0.2', intensityAt(100) < 0.2);
check('loudness совпадает с intensityAt(distance)',
    approx(loudness(0, 0, 30, 40), intensityAt(distance(0, 0, 30, 40))));
check('радиус слышимости ~95 px', audibleRadius() > 90 && audibleRadius() < 100);

// ============================================================
console.log('3. SoundWave');
// ============================================================
const wave = new SoundWave(100, 100, 50);
check('стартовый радиус = 1', wave.radius === 1);
check('изначально активна', wave.active === true);
for (let i = 0; i < 40; i++) wave.update();
check('расширяется со скоростью 2.5', wave.radius > 40);
check('достигнув максимум, деактивируется', (() => { while (wave.active) wave.update(); return wave.active === false; })());
const reachWave = new SoundWave(0, 0, 50);
reachWave.radius = 30;
check('reaches: точка внутри текущего радиуса', reachWave.reaches(10, 10) === true);
check('reaches: далеко — вне радиуса', reachWave.reaches(400, 400) === false);
check('alpha убывает с расширением', new SoundWave(0, 0, 100).alpha > (() => { const w = new SoundWave(0, 0, 100); w.radius = 50; return w.alpha; })());

// ============================================================
console.log('4. Agent: движение, коллизии, волны');
// ============================================================
const walls = [new Rect(0, 0, 100, 600)]; // стена слева
const agent = new Agent(100, 100);        // агент справа от стены
check('move в свободную сторону → true', agent.move(0, 1, walls) === true);
check('позиция изменилась', agent.rect.y === 103);
check('move в стену → false', agent.move(-1, 0, walls) === false);
check('позиция НЕ изменилась при коллизии', agent.rect.x === 100);
check('скорость ходьбы = 3', agent.move(1, 0, walls) === true && agent.rect.x === 103);
check('режим бега ускоряет', (() => { agent.running = true; const y0 = agent.rect.y; agent.move(0, 1, walls); return agent.rect.y - y0 === 6; })());
agent.running = false;
check('maxRadiusFor: бетон ходьба = 20', agent.maxRadiusFor(0) === WALK_RADIUS);
check('maxRadiusFor: бетон бег = 80', (() => { agent.running = true; return agent.maxRadiusFor(0) === RUN_RADIUS; })());
check('maxRadiusFor: металл удваивает', (() => { agent.running = false; return agent.maxRadiusFor(1) === WALK_RADIUS * 2; })());
const agent2 = new Agent(10, 10);
const w1 = agent2.makeWave(1000, 0);
check('makeWave создаёт волну', w1 instanceof SoundWave);
check('кулдаун: сразу вторую — null', agent2.makeWave(10, 0) === null);
check('кулдаун: после 180 мс — снова можно', agent2.makeWave(1000 + WAVE_COOLDOWN_MS + 1, 0) instanceof SoundWave);

// ============================================================
console.log('5. BlindGuard: конечный автомат (FSM)');
// ============================================================
// Уровень без стен: охранник патрулирует между двумя точками
const guard = new BlindGuard([[100, 100], [300, 100]], 0, []);
check('стартовое состояние Patrol', guard.state === GUARD_STATES.PATROL);

// Охранник слышит волну рядом → Investigating
const loudWave = new SoundWave(120, 100, 300); // эпицентр в 20 px от guard (100,100)
const agentNear = new Agent(120, 100);
guard.update([loudWave], agentNear);
check('услышал шум → Investigating', guard.state === GUARD_STATES.INVESTIGATING);
check('hearingAlert поднят', guard.hearingAlert > 0.9);

// Расследование: идёт к эпицентру, доходя → Returning
let frames = 0;
while (guard.state === GUARD_STATES.INVESTIGATING && frames < 200) {
    guard.update([loudWave], agentNear);
    frames += 1;
}
check('дойдя до эпицентра → Returning', guard.state === GUARD_STATES.RETURNING);
check('alertTarget сброшен', guard.alertTarget === null);

// Возврат к маршруту → Patrol
frames = 0;
while (guard.state === GUARD_STATES.RETURNING && frames < 400) {
    guard.update([loudWave], agentNear);
    frames += 1;
}
check('вернувшись к маршруту → Patrol', guard.state === GUARD_STATES.PATROL);

// Тихий далёкий шум не слышен (экспоненциальное затухание)
const quietGuard = new BlindGuard([[100, 100]], 0, []);
const farWave = new SoundWave(100 + 400, 100, 50); // 400 px, за краем волны
quietGuard.update([farWave], new Agent(500, 100));
check('далёкий шум за краем волны → остался Patrol', quietGuard.state === GUARD_STATES.PATROL);

// Порог слышимости работает
const edgeGuard = new BlindGuard([[100, 100]], 0, []);
const farLoudWave = new SoundWave(500, 100, 1000); // внутри радиуса, но затухший
edgeGuard.update([farLoudWave], new Agent(500, 100));
check('внутри радиуса, но тише порога → Patrol (затухание!)', edgeGuard.state === GUARD_STATES.PATROL);

// Зрение: агент рядом без стен → поимка
const seeing = new BlindGuard([[200, 200]], 0, []);
const prey = new Agent(240, 200); // 20 px — в радиусе зрения 90
let caught = false;
for (let i = 0; i < 60 && !caught; i++) caught = seeing.update([], prey);
check('увидел агента → update() вернул true (поимка)', caught === true);

// Застревание: охрана у стены не падает
const stuckWalls = [new Rect(0, 0, 800, 600), new Rect(150, 0, 10, 130)];
const stuckGuard = new BlindGuard([[100, 50]], 0, stuckWalls);
for (let i = 0; i < 120; i++) stuckGuard.update([], new Agent(400, 400));
check('120 кадров у стены — исключений нет, состояние определено', typeof stuckGuard.state === 'string');

// Защита уровня: точка маршрута внутри стены сдвигается
const shifted = new BlindGuard([[405, 50]], 0, stuckWalls);
check('точка маршрута в стене сдвинута', shifted.patrolPoints[0][0] !== 405);

// ============================================================
console.log('6. LabyrinthField и валидация JSON');
// ============================================================
const field = new LabyrinthField();
check('getTileAt: металл на (100, 80)', field.getTileAt(100, 80) === 1);
check('getTileAt: финиш в центре плитки', field.getTileAt(220, 420) === 2);
check('getTileAt: бетон в углу', field.getTileAt(30, 30) === 0);
check('getTileAt: за пределами → 0', field.getTileAt(-50, -50) === 0);
check('стены построены как Rect', field.walls[0] instanceof Rect);

try {
    LabyrinthField.fromJSON('{не JSON');
    check('битый JSON бросает ошибку', false);
} catch {
    check('битый JSON бросает ошибку', true);
}
try {
    LabyrinthField.fromJSON('{"level": []}');
    check('пустой уровень бросает ошибку', false);
} catch {
    check('пустой уровень бросает ошибку', true);
}
try {
    LabyrinthField.fromJSON('{"level": [[5, 0, 0]]}');
    check('недопустимый тайл 5 бросает ошибку', false);
} catch {
    check('недопустимый тайл 5 бросает ошибку', true);
}
const okField = LabyrinthField.fromJSON('{"level": [[0, 0], [0, 2]], "guards": []}');
check('корректный JSON парсится', okField.getTileAt(40, 40) === 2);

// ============================================================
console.log('7. Game: сквозной сценарий');
// ============================================================
const g = new Game(field, { x: 80, y: 80 }, [
    { route: [[200, 160], [400, 160]] },
]);
g.update({ right: true }, 1000);
check('игра считает шаги', g.stats.steps === 1);
check('волна создана', g.stats.waves === 1 && g.waves.length === 1);
g.update({}, 1100);
check('волна расширилась', g.waves[0].radius > 1);

// Победа: агент на финише
const w = new Game(field, { x: 220, y: 410 }, []); // плитка финиша: col 5, row 10
w.update({}, 1000);
check('агент на финише → победа', w.over === true && w.result === 'win');

// ============================================================
console.log('\n================ ИТОГ ================');
console.log(`Пройдено: ${passed}, провалено: ${failed}`);
if (failed > 0) {
    console.log('Провалившиеся проверки:');
    for (const f of failures) console.log(`  - ${f}`);
    process.exit(1);
}
console.log('Все проверки ядра пройдены ✅');
