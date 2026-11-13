import os

REPO = "War3l/FollowTheLyrics"
VERSION_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "VERSION"
)


def current() -> str:
    fake = os.environ.get("FTL_FAKE_VERSION")
    if fake:
        return fake
    try:
        with open(VERSION_PATH, encoding="utf-8") as f:
            return f.read().strip() or "0"
    except OSError:
        return "0"
