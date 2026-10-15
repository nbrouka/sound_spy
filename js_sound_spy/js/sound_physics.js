/**
 * Физика распространения звука.
 *
 * Вычисление интенсивности звука, дошедшего до охранника,
 * по экспоненциальной формуле затухания в зависимости от расстояния
 * (вычисляемого по теореме Пифагора) между точкой зацепа/шага и охранником».
 *
 * Формула:  I(d) = I0 * exp(-k * d)
 *   I0 — громкость в эпицентре (1.0),
 *   k  — коэффициент затухания среды (0.02 — «бетонные стены»),
 *   d  — расстояние от эпицентра до слушателя (пиксели).
 *
 * Почему экспонента: в вязкой среде энергия волны убывает пропорционально
 * пройденному пути, а не линейно — каждые следующие N пикселей «съедают»
 * одинаковую долю оставшейся энергии.
 */

export const SOUND_INTENSITY_0 = 1.0;
export const SOUND_DECAY_COEFFICIENT = 0.02;

/** Порог слышимости охранника: тише — значит «не слышно». */
export const GUARD_HEARING_THRESHOLD = 0.15;

/** Расстояние между точками по теореме Пифагора. */
export function distance(x1, y1, x2, y2) {
    return Math.hypot(x2 - x1, y2 - y1);
}

/** Интенсивность звука на расстоянии d от эпицентра. */
export function intensityAt(d) {
    return SOUND_INTENSITY_0 * Math.exp(-SOUND_DECAY_COEFFICIENT * d);
}

/** Громкость источника, с которой его слышно в точке (listenerX, listenerY). */
export function loudness(sourceX, sourceY, listenerX, listenerY) {
    return intensityAt(distance(sourceX, sourceY, listenerX, listenerY));
}

/**
 * Обратная задача: на каком максимальном расстоянии звук ещё слышен.
 * Из I(d) = threshold находим d = ln(I0 / threshold) / k.
 */
export function audibleRadius(threshold = GUARD_HEARING_THRESHOLD) {
    return Math.log(SOUND_INTENSITY_0 / threshold) / SOUND_DECAY_COEFFICIENT;
}
