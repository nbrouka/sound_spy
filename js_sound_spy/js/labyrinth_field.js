/**
 * LabyrinthField — игровое поле: тайлы и стены.
 *
 * Порт py_sound_spy/level.py + загрузка/валидация конфигурации
 * из data_io.load_level_config: уровень можно описать JSON-строкой.
 */
import { Rect } from './rect.js';
import {
    WALL_DATA,
    TILE_SIZE,
    GRID_COLUMNS,
    GRID_ROWS,
    LEVEL_MATRIX,
} from './constants.js';

export class LabyrinthField {
    /**
     * @param {number[][]} matrix — матрица тайлов (0 бетон, 1 металл, 2 финиш)
     * @param {{x,y,w,h}[]} wallData — описания стен
     */
    constructor(matrix = LEVEL_MATRIX, wallData = WALL_DATA) {
        this.matrix = matrix;
        this.walls = wallData.map((w) => new Rect(w.x, w.y, w.w, w.h));
    }

    get rows() {
        return this.matrix.length;
    }

    get columns() {
        return this.matrix[0].length;
    }

    /** Тип плитки по пиксельным координатам. */
    getTileAt(px, py) {
        const gx = Math.floor(px / TILE_SIZE);
        const gy = Math.floor(py / TILE_SIZE);
        if (gx >= 0 && gx < this.columns && gy >= 0 && gy < this.rows) {
            return this.matrix[gy][gx];
        }
        return 0; // за пределами поля считаем бетоном
    }

    /**
     * Создаёт поле из JSON-строки (как load_level_config в Python).
     * Ожидаемая структура: {"level": [[...]], "walls": [...], "guards": [...]}
     * @throws {Error} если структура повреждена
     */
    static fromJSON(text) {
        let config;
        try {
            config = JSON.parse(text);
        } catch (e) {
            throw new Error(`Ошибка парсинга JSON: ${e.message}`);
        }
        LabyrinthField._validate(config);

        const field = new LabyrinthField(config.level, config.walls ?? WALL_DATA);
        field.guards = config.guards ?? [];
        return field;
    }

    /** Валидация обязательных полей (аналог _validate_config). */
    static _validate(config) {
        if (typeof config !== 'object' || config === null) {
            throw new Error('Конфигурация уровня должна быть объектом');
        }
        if (!Array.isArray(config.level) || config.level.length === 0) {
            throw new Error('Отсутствует или пусто поле "level"');
        }
        for (const row of config.level) {
            if (!Array.isArray(row) || row.some((t) => ![0, 1, 2].includes(t))) {
                throw new Error('Строка уровня должна содержать только 0, 1 или 2');
            }
        }
        if (config.walls !== undefined) {
            if (!Array.isArray(config.walls)) {
                throw new Error('Поле "walls" должно быть массивом');
            }
            for (const w of config.walls) {
                if (![w.x, w.y, w.w, w.h].every((v) => Number.isFinite(v))) {
                    throw new Error('Стена должна иметь числовые x, y, w, h');
                }
            }
        }
        if (config.guards !== undefined && !Array.isArray(config.guards)) {
            throw new Error('Поле "guards" должно быть массивом');
        }
    }
}
