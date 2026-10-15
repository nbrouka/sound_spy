/**
 * Rect — прямоугольник с областью ответственности «геометрия».
 *
 * Порт возможностей pygame.Rect, которые использует игра:
 *   new Rect(x, y, w, h)
 *   rect.centerx / rect.centery / rect.center
 *   rect.move(dx, dy)      → НОВЫЙ Rect (сдвинутая копия)
 *   rect.moveInPlace(dx, dy) → мутирует rect
 *   rect.colliderect(other) → пересечение с другим Rect
 *   rect.collidepoint(x, y) → точка внутри прямоугольника
 *
 * Ключевое отличие от pygame: move() возвращает копию, а не мутирует
 * объект — как и в Python (это защита от случайного изменения состояния).
 */

export class Rect {
    constructor(x, y, w, h) {
        this.x = x;
        this.y = y;
        this.w = w;
        this.h = h;
    }

    get centerx() {
        return this.x + this.w / 2;
    }

    get centery() {
        return this.y + this.h / 2;
    }

    get center() {
        return [this.centerx, this.centery];
    }

    /** Возвращает НОВЫЙ Rect, сдвинутый на (dx, dy). Оригинал не меняется. */
    move(dx, dy) {
        return new Rect(this.x + dx, this.y + dy, this.w, this.h);
    }

    /** Мутирует текущий Rect (аналог pygame move_ip). */
    moveInPlace(dx, dy) {
        this.x += dx;
        this.y += dy;
    }

    colliderect(other) {
        return (
            this.x < other.x + other.w &&
            this.x + this.w > other.x &&
            this.y < other.y + other.h &&
            this.y + this.h > other.y
        );
    }

    collidepoint(px, py) {
        return px >= this.x && px < this.x + this.w &&
               py >= this.y && py < this.y + this.h;
    }

    /** Расстояние между центрами двух прямоугольников (теорема Пифагора). */
    distanceTo(other) {
        return Math.hypot(other.centerx - this.centerx, other.centery - this.centery);
    }
}
