import importlib

from followthelyrics import desktop


def main():
    boot = desktop.boot()
    boot.prepare()
    try:
        importlib.import_module("PyQt6.QtCore")
    except ImportError as error:
        boot.report(error)
        raise SystemExit(1) from error
    from followthelyrics import app

    app.main()


if __name__ == "__main__":
    main()
