"""Generate packaging/app.ico from the app's drawn icon (run by build.ps1)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QGuiApplication, QIcon  # noqa: E402

_app = QGuiApplication([])

from crypto_price_alert.resources import _icon_pixmap  # noqa: E402

out = pathlib.Path(__file__).with_name("app.ico")
icon = QIcon()
for size in (16, 24, 32, 48, 64, 128, 256):
    icon.addPixmap(_icon_pixmap(size))

if not icon.pixmap(256, 256).save(str(out), "ICO"):
    _icon_pixmap(256).save(str(out), "ICO")

print("wrote", out, "ok" if out.exists() else "FAILED")
