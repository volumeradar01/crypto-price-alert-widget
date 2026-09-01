"""Vector toolbar icons drawn with QPainter — no icon-font dependency."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF


def _stroke(p: QPainter, size: int, color: QColor):
    pen = QPen(color, max(1.8, size * 0.10))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)


def _d_plus(p, s, c):
    _stroke(p, s, c)
    p.drawLine(QPointF(s * 0.5, s * 0.24), QPointF(s * 0.5, s * 0.76))
    p.drawLine(QPointF(s * 0.24, s * 0.5), QPointF(s * 0.76, s * 0.5))


def _d_pause(p, s, c):
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    w = s * 0.13
    p.drawRoundedRect(QRectF(s * 0.32, s * 0.26, w, s * 0.48), w * 0.4, w * 0.4)
    p.drawRoundedRect(QRectF(s * 0.55, s * 0.26, w, s * 0.48), w * 0.4, w * 0.4)


def _d_play(p, s, c):
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    path = QPainterPath()
    path.moveTo(s * 0.34, s * 0.26)
    path.lineTo(s * 0.34, s * 0.74)
    path.lineTo(s * 0.76, s * 0.50)
    path.closeSubpath()
    p.drawPath(path)


def _d_settings(p, s, c):
    """Slider faders — the common 'settings / adjustments' icon."""
    rows = ((0.29, 0.62), (0.50, 0.34), (0.71, 0.58))
    _stroke(p, s, c)
    for y, _knob in rows:
        p.drawLine(QPointF(s * 0.20, s * y), QPointF(s * 0.80, s * y))
    r = s * 0.12
    for y, knob in rows:
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawEllipse(QPointF(s * knob, s * y), r, r)


def _d_close(p, s, c):
    _stroke(p, s, c)
    p.drawLine(QPointF(s * 0.28, s * 0.28), QPointF(s * 0.72, s * 0.72))
    p.drawLine(QPointF(s * 0.72, s * 0.28), QPointF(s * 0.28, s * 0.72))


def _d_moon(p, s, c):
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    outer = QPainterPath()
    outer.addEllipse(QRectF(s * 0.22, s * 0.20, s * 0.58, s * 0.58))
    cut = QPainterPath()
    cut.addEllipse(QRectF(s * 0.36, s * 0.12, s * 0.56, s * 0.56))
    p.drawPath(outer.subtracted(cut))


def _d_sun(p, s, c):
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    r = s * 0.15
    p.drawEllipse(QPointF(s * 0.5, s * 0.5), r, r)
    _stroke(p, s, c)
    for k in range(8):
        ang = k * math.pi / 4
        p.drawLine(
            QPointF(s * 0.5 + math.cos(ang) * s * 0.28, s * 0.5 + math.sin(ang) * s * 0.28),
            QPointF(s * 0.5 + math.cos(ang) * s * 0.37, s * 0.5 + math.sin(ang) * s * 0.37),
        )


def _d_half(p, s, c):
    _stroke(p, s, c)
    rect = QRectF(s * 0.24, s * 0.24, s * 0.52, s * 0.52)
    p.drawEllipse(rect)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawChord(rect, 90 * 16, 180 * 16)


def _d_copy(p, s, c):
    _stroke(p, s, c)
    p.drawRoundedRect(QRectF(s * 0.24, s * 0.24, s * 0.40, s * 0.40), s * 0.07, s * 0.07)
    p.drawRoundedRect(QRectF(s * 0.38, s * 0.38, s * 0.40, s * 0.40), s * 0.07, s * 0.07)


def _d_external(p, s, c):
    _stroke(p, s, c)
    p.drawPolyline(QPolygonF([
        QPointF(s * 0.46, s * 0.28), QPointF(s * 0.28, s * 0.28),
        QPointF(s * 0.28, s * 0.72), QPointF(s * 0.72, s * 0.72),
        QPointF(s * 0.72, s * 0.54),
    ]))
    p.drawLine(QPointF(s * 0.50, s * 0.50), QPointF(s * 0.74, s * 0.26))
    p.drawPolyline(QPolygonF([
        QPointF(s * 0.56, s * 0.26), QPointF(s * 0.74, s * 0.26), QPointF(s * 0.74, s * 0.44),
    ]))


def _d_check(p, s, c):
    _stroke(p, s, c)
    p.drawPolyline(QPolygonF([
        QPointF(s * 0.26, s * 0.52), QPointF(s * 0.44, s * 0.70), QPointF(s * 0.76, s * 0.32),
    ]))


_DRAW = {
    "plus": _d_plus,
    "pause": _d_pause,
    "play": _d_play,
    "settings": _d_settings,
    "close": _d_close,
    "moon": _d_moon,
    "sun": _d_sun,
    "half": _d_half,
    "copy": _d_copy,
    "external": _d_external,
    "check": _d_check,
}


def make_icon(name: str, color) -> QIcon:
    col = color if isinstance(color, QColor) else QColor(color)
    draw = _DRAW[name]
    icon = QIcon()
    for size in (16, 20, 24, 32, 40):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        draw(p, size, col)
        p.end()
        icon.addPixmap(pm)
    return icon
