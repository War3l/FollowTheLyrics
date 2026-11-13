import importlib

from followthelyrics import bootstrap


def main():
    bootstrap.prepare()
    try:
        importlib.import_module("PyQt6.QtCore")
    except ImportError as error:
        bootstrap.report(error)
        raise SystemExit(1) from error
    from followthelyrics import app

    app.main()


if __name__ == "__main__":
    main()
