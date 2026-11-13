import math
from functools import lru_cache

import numpy as np

K = 8
CHROMA_MIN = 0.032
SHARE_MIN = 0.012
HUE_GAP = 28.0
TEXT_L = (0.64, 0.88)
TEXT_C = (0.11, 0.25)


def srgb_to_oklab(rgb):
    rgb = np.asarray(rgb, dtype=np.float64)
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    r, g, b = lin[..., 0], lin[..., 1], lin[..., 2]
    l_ = np.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m_ = np.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s_ = np.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return np.stack([
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    ], axis=-1)


def _oklab_to_linear(lab):
    L, a, b = lab
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
            -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
            -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)


def lch_to_rgb(L, C, h):
    hr = math.radians(h)
    for _ in range(40):
        lin = _oklab_to_linear((L, C * math.cos(hr), C * math.sin(hr)))
        if all(-0.0005 <= v <= 1.0005 for v in lin):
            break
        C *= 0.95
    out = []
    for v in lin:
        v = min(1.0, max(0.0, v))
        v = v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
        out.append(int(round(min(1.0, max(0.0, v)) * 255)))
    return tuple(out)


def rgb_to_lch(rgb):
    L, a, b = srgb_to_oklab(np.array(rgb, dtype=np.float64) / 255.0)
    return float(L), float(math.hypot(a, b)), float(math.degrees(math.atan2(b, a)) % 360)


def hue_diff(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _kmeans(pts, k, iters=14):
    rng = np.random.default_rng(7)
    centers = [pts[rng.integers(len(pts))]]
    d2 = np.full(len(pts), np.inf)
    for _ in range(k - 1):
        d2 = np.minimum(d2, ((pts - centers[-1]) ** 2).sum(1))
        total = d2.sum()
        if total <= 1e-12:
            break
        centers.append(pts[rng.choice(len(pts), p=d2 / total)])
    centers = np.array(centers)
    labels = np.zeros(len(pts), dtype=np.int64)
    for _ in range(iters):
        dist = ((pts[:, None, :] - centers[None, :, :]) ** 2).sum(2)
        labels = dist.argmin(1)
        for j in range(len(centers)):
            sel = pts[labels == j]
            if len(sel):
                centers[j] = sel.mean(0)
    return labels, len(centers)


def _families(rgb):
    lab = srgb_to_oklab(rgb.reshape(-1, 3) / 255.0)
    pts = lab * np.array([0.6, 1.0, 1.0])
    labels, k = _kmeans(pts, K)
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    fams = []
    for j in range(k):
        idx = np.nonzero(labels == j)[0]
        if not len(idx):
            continue
        top = idx[np.argsort(chroma[idx])[len(idx) // 2:]]
        L, a, b = lab[top].mean(0)
        fams.append({"share": len(idx) / len(lab), "L": float(L), "C": float(math.hypot(a, b)),
                     "h": float(math.degrees(math.atan2(b, a)) % 360)})
    return fams


def _score(f):
    s = (f["share"] ** 0.55) * (f["C"] ** 1.15)
    if f["L"] < 0.28:
        s *= 0.45
    if 35 <= f["h"] <= 80 and f["C"] < 0.11:
        s *= 0.55
    return s


def _in_gamut(L, C, h):
    hr = math.radians(h)
    return all(-0.0005 <= v <= 1.0005 for v in _oklab_to_linear((L, C * math.cos(hr), C * math.sin(hr))))


@lru_cache(maxsize=4096)
def max_chroma(L, h):
    lo, hi = 0.0, 0.4
    for _ in range(18):
        mid = (lo + hi) / 2
        if _in_gamut(L, mid, h):
            lo = mid
        else:
            hi = mid
    return lo


_TEXT_LS = tuple(round(TEXT_L[0] + (TEXT_L[1] - TEXT_L[0]) * i / 11, 4) for i in range(12))


def _text_color(L, C, h):
    h = round(h) % 360
    lo, hi = TEXT_L
    pref = lo + (hi - lo) * min(1.0, max(0.0, (L - 0.25) / 0.6))
    want = min(TEXT_C[1], max(TEXT_C[0], C * 1.35))
    ok = [l for l in _TEXT_LS if max_chroma(l, h) >= want]
    if ok:
        L2 = min(ok, key=lambda l: abs(l - pref))
    else:
        L2 = max(_TEXT_LS, key=lambda l: max_chroma(l, h))
        want = max_chroma(L2, h)
    return lch_to_rgb(L2, want, h)


def palette_rgb(rgb):
    if rgb is None or rgb.size == 0:
        return None
    fams = _families(np.asarray(rgb, dtype=np.float64))
    colored = [f for f in fams if f["C"] >= CHROMA_MIN and f["share"] >= SHARE_MIN]
    if not colored:
        return [(244, 247, 255), (255, 255, 255), (255, 246, 236)]
    colored.sort(key=_score, reverse=True)
    main = colored[0]
    chosen = [main]
    for _ in range(2):
        best, best_s = None, 0.0
        for f in colored:
            gap = min(hue_diff(f["h"], c["h"]) for c in chosen)
            if gap < HUE_GAP:
                continue
            s = _score(f) * min(1.0, gap / 90.0) ** 0.5
            if s > best_s and _score(f) >= 0.22 * _score(main):
                best, best_s = f, s
        if best is None:
            break
        chosen.append(best)

    out = [(c["L"], c["C"], c["h"]) for c in chosen]
    L, C, h = out[0]
    if len(out) == 1:
        out += [(L + 0.14, C * 0.8, h + 14), (L - 0.04, C, h - 14)]
    elif len(out) == 2:
        out.append((min(1.0, L + 0.3), C * 0.55, h))
    rest = sorted(out[1:], key=lambda c: hue_diff(c[2], h))
    return [_text_color(*c) for c in [out[0]] + rest]


@lru_cache(maxsize=64)
def ramp(colors, steps=5):
    lchs = [rgb_to_lch(c) for c in colors]
    stops = []
    n = len(lchs) - 1
    for i in range(n):
        (L0, C0, h0), (L1, C1, h1) = lchs[i], lchs[i + 1]
        if C0 < 0.02:
            h0 = h1
        if C1 < 0.02:
            h1 = h0
        dh = ((h1 - h0 + 180) % 360) - 180
        for s in range(steps):
            t = s / steps
            stops.append(((i + t) / n, lch_to_rgb(L0 + (L1 - L0) * t, C0 + (C1 - C0) * t, (h0 + dh * t) % 360)))
    stops.append((1.0, tuple(colors[-1])))
    return stops
