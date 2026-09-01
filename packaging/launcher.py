"""Frozen-app entry point. Imports the package properly so relative imports work,
and records any fatal startup error where a user (or we) can find it."""

import multiprocessing
import os
import sys
import traceback


def _crash(exc: BaseException) -> None:
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "CryptoPriceAlert", "crash.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    except Exception:
        pass
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication([])
        QMessageBox.critical(None, "Crypto Price Alerts — startup error", text[-3000:])
    except Exception:
        sys.stderr.write(text)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        from crypto_price_alert.__main__ import main

        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001
        _crash(exc)
        raise SystemExit(1)
