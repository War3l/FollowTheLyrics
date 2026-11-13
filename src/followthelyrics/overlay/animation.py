import math


def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def ease_out(x):
    return 1 - (1 - x) ** 3


def ease_out_back(x):
    c = 1.9
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def lerp(a, b, k):
    return a + (b - a) * k


def held_fx(meta, pos):
    none = (1.0, 0.0, 0.0, 0.0, 1.0)
    if not meta:
        return none
    start, end, inten = meta
    if inten <= 0 or pos < start:
        return none
    amp = 0.10 + 0.24 * inten
    if pos <= end:
        k = ease_out(clamp((pos - start) / max(0.25, end - start)))
        shake = (0.8 + 2.8 * inten) * k if (end - start) > 0.8 else 0.0
        dx = shake * math.sin(pos * 61 + start * 13)
        dy = shake * math.sin(pos * 47 + start * 7 + 1.3)
        return 1 + amp * k, dx, dy, k, 1 + 0.07 * inten * k
    after = pos - end
    if after > 0.5:
        return none
    sc = 1 + amp * math.exp(-after * 9) * math.cos(after * 22)
    return sc, 0.0, 0.0, max(0.0, 1 - after * 3), 1.0
