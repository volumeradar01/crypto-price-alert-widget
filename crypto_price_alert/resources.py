"""Runtime-generated assets: the app icon and a default alert sound.

Keeping these generated (rather than shipping binaries) makes the repo plain
text and guarantees a working default beep even on a fresh checkout.
"""

from __future__ import annotations

import logging
import math
import struct
import wave
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

from .config import app_data_dir

log = logging.getLogger(__name__)

_ASSETS = Path(__file__).parent / "assets"


def _icon_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0.0, QColor("#26406b"))
    grad.setColorAt(1.0, QColor("#0d1220"))
    body = QPainterPath()
    body.addRoundedRect(QRectF(size * 0.05, size * 0.05, size * 0.9, size * 0.9),
                        size * 0.22, size * 0.22)
    p.fillPath(body, QBrush(grad))

    up = QPen(QColor("#29d366"), max(1.0, size * 0.09))
    up.setCapStyle(Qt.RoundCap)
    up.setJoinStyle(Qt.RoundJoin)
    p.setPen(up)
    p.drawPolyline(QPolygonF([
        QPointF(size * 0.27, size * 0.53),
        QPointF(size * 0.46, size * 0.29),
        QPointF(size * 0.65, size * 0.53),
    ]))

    down = QPen(QColor("#ff4d5e"), max(1.0, size * 0.09))
    down.setCapStyle(Qt.RoundCap)
    down.setJoinStyle(Qt.RoundJoin)
    p.setPen(down)
    p.drawPolyline(QPolygonF([
        QPointF(size * 0.35, size * 0.49),
        QPointF(size * 0.54, size * 0.73),
        QPointF(size * 0.73, size * 0.49),
    ]))
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_icon_pixmap(s))
    return icon


def ensure_ico_file() -> str:
    """Write a .ico into the app data dir (used for the Startup shortcut)."""
    path = app_data_dir() / "app_icon.ico"
    if not path.exists():
        try:
            _icon_pixmap(256).save(str(path), "ICO")
        except Exception as e:  # noqa: BLE001 - best effort
            log.warning("Could not write .ico: %s", e)
            return ""
    return str(path) if path.exists() else ""


def default_sound_path() -> str:
    bundled = _ASSETS / "default_alert.wav"
    if bundled.exists():
        return str(bundled)
    generated = app_data_dir() / "default_alert_v2.wav"
    if not generated.exists():
        _generate_beep(generated)
    return str(generated) if generated.exists() else ""


def _generate_beep(path: Path) -> None:
    """A short pleasant two-note chime, 16-bit mono PCM WAV."""
    try:
        rate = 44100
        amp = 18000
        # A5 - rest - D6 - long rest, so an infinite loop beeps with a gap
        notes = [(880.0, 0.13), (0.0, 0.03), (1174.7, 0.20), (0.0, 0.55)]
        data = bytearray()
        for freq, dur in notes:
            n = int(rate * dur)
            for i in range(n):
                if freq <= 0:
                    sample = 0
                else:
                    fade = min(1.0, (n - i) / (rate * 0.04))  # 40ms release
                    sample = int(amp * fade * math.sin(2 * math.pi * freq * i / rate))
                data += struct.pack("<h", sample)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(data))
    except Exception as e:  # noqa: BLE001 - best effort
        log.warning("Failed to generate default beep: %s", e)
