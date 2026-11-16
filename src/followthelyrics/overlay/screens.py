MAX_LABEL = 24


def _base_key(screen):
    return screen.serialNumber() or screen.name()


def keys(screens):
    out: list[str] = []
    seen: dict[str, int] = {}
    for s in screens:
        k = _base_key(s)
        n = seen.get(k, 0)
        seen[k] = n + 1
        out.append(f"{k}#{n + 1}" if n else k)
    return out


def label(screen):
    text = (screen.model() or screen.name() or "").strip()
    if len(text) > MAX_LABEL:
        text = text[: MAX_LABEL - 1].rstrip() + "…"
    return text


def choices(screens):
    names = [label(s) for s in screens]
    out = {}
    for i, (k, name) in enumerate(zip(keys(screens), names, strict=True)):
        twin = not name or names.count(name) > 1
        out[k] = f"{name} {i + 1}".strip() if twin else name
    return out


def pick(screens, primary, wanted):
    if wanted:
        for k, s in zip(keys(screens), screens, strict=True):
            if k == wanted:
                return s
    return primary


def key_of(screens, screen):
    for k, s in zip(keys(screens), screens, strict=True):
        if s is screen:
            return k
    return ""
