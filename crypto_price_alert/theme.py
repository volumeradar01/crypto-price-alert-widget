"""Light / dark palettes and the application stylesheet built from them."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

THEMES = ("dark", "light", "system")

_DARK = {
    "bg": "#0f1420",
    "surface": "#161c28",
    "surface2": "#1d2533",
    "raised": "#212b3b",
    "border": "#2b3344",
    "border_soft": "#242c3a",
    "text": "#eef1f6",
    "text_dim": "#9aa3b2",
    "text_faint": "#6b7484",
    "accent": "#5b9dff",
    "accent_text": "#ffffff",
    "up_bg": "#0f2a1c",
    "up_border": "#1f7a46",
    "up_line": "#2bd66e",
    "up_text": "#54e08c",
    "dn_bg": "#2c1519",
    "dn_border": "#7d2733",
    "dn_line": "#ff5061",
    "dn_text": "#ff8189",
    "armed_line": "#4a5568",
    "shadow": "#00000090",
}

_LIGHT = {
    "bg": "#eef1f6",
    "surface": "#ffffff",
    "surface2": "#f4f6fa",
    "raised": "#eaeef5",
    "border": "#d3d9e3",
    "border_soft": "#e4e8ef",
    "text": "#182030",
    "text_dim": "#5a6473",
    "text_faint": "#98a2b2",
    "accent": "#2f6fed",
    "accent_text": "#ffffff",
    "up_bg": "#e6f6ec",
    "up_border": "#8fd6a8",
    "up_line": "#1faa5a",
    "up_text": "#137a3f",
    "dn_bg": "#fdeaec",
    "dn_border": "#f0b3ba",
    "dn_line": "#e23b4d",
    "dn_text": "#b3202f",
    "armed_line": "#b8c0cd",
    "shadow": "#00000030",
}

PALETTES = {"dark": _DARK, "light": _LIGHT}


def effective_theme(name: str) -> str:
    """Resolve 'system' to 'light' or 'dark'; pass others through."""
    if name in ("dark", "light"):
        return name
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication

        scheme = QGuiApplication.styleHints().colorScheme()
        return "light" if scheme == Qt.ColorScheme.Light else "dark"
    except Exception:  # noqa: BLE001 - older Qt or no app yet
        return "dark"


def palette(name: str) -> dict:
    return PALETTES.get(effective_theme(name), _DARK)


_QSS_TEMPLATE = """
* { font-family: "Segoe UI", "Segoe UI Symbol", "Segoe UI Emoji", "Inter", system-ui, sans-serif; }

QWidget#card {
    background: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 16px;
}
QLabel#title { color: %(text)s; font-size: 13px; font-weight: 700; letter-spacing: .2px; }
QLabel#status { color: %(text_dim)s; font-size: 10px; font-weight: 600; }
QLabel#status[tone="bad"]  { color: %(dn_text)s; }
QLabel#status[tone="live"] { color: %(up_text)s; }
QLabel#empty { color: %(text_faint)s; font-size: 12px; padding: 30px 14px; }

QPushButton#tool {
    background: %(surface2)s; color: %(text_dim)s;
    border: 1px solid %(border_soft)s; border-radius: 9px; font-size: 13px;
}
QPushButton#tool:hover { background: %(raised)s; color: %(text)s; }
QPushButton#tool:pressed { background: %(accent)s; color: %(accent_text)s; }

QScrollArea#scroll { background: transparent; border: none; }
QWidget#holder { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: %(border)s; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: %(text_faint)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

QFrame#row {
    background: %(surface2)s;
    border: 1px solid %(border_soft)s;
    border-left: 3px solid %(armed_line)s;
    border-radius: 12px;
}
QFrame#row[state="armed"]    { border-left-color: %(armed_line)s; }
QFrame#row[state="above"]    { background: %(up_bg)s; border-color: %(up_border)s; border-left-color: %(up_line)s; }
QFrame#row[state="below"]    { background: %(dn_bg)s; border-color: %(dn_border)s; border-left-color: %(dn_line)s; }
QFrame#row[state="disabled"] { border-left-color: %(border)s; }

QLabel#name  { color: %(text)s; font-size: 13px; font-weight: 700; }
QLabel#sub   { color: %(text_faint)s; font-size: 10px; font-weight: 600; }
QLabel#cond  { color: %(text_dim)s; font-size: 11px; }
QLabel#price { color: %(text)s; font-size: 15px; font-weight: 800; }
QFrame#row[state="disabled"] QLabel#name,
QFrame#row[state="disabled"] QLabel#price { color: %(text_faint)s; }
QFrame#row[state="above"] QLabel#price { color: %(up_text)s; }
QFrame#row[state="below"] QLabel#price { color: %(dn_text)s; }

QPushButton#rearm, QPushButton#dismiss {
    background: %(raised)s; color: %(text)s;
    border: 1px solid %(border)s; border-radius: 8px;
    padding: 3px 10px; font-size: 10px; font-weight: 700;
}
QPushButton#rearm:hover { background: %(accent)s; color: %(accent_text)s; border-color: %(accent)s; }
QPushButton#dismiss:hover { background: %(dn_line)s; color: #fff; border-color: %(dn_line)s; }

QFrame#sep { background: %(border_soft)s; border: none; }
QLabel#footcap {
    color: %(text_faint)s; font-size: 9px; font-weight: 800; letter-spacing: 1.4px;
    padding: 2px 0 1px 0;
}
QPushButton#link {
    background: transparent; border: none; color: %(accent)s;
    text-align: left; padding: 2px 0; font-size: 11px; font-weight: 600;
}
QPushButton#link:hover { color: %(text)s; }
QPushButton#linkcopy { background: transparent; border: none; border-radius: 6px; }
QPushButton#linkcopy:hover { background: %(raised)s; }

/* dialogs & controls */
QDialog { background: %(surface)s; color: %(text)s; }
QLabel { color: %(text)s; }
QLabel[role="hint"] { color: %(text_faint)s; font-size: 10px; }
QLabel[role="current"] { color: %(up_text)s; font-size: 12px; font-weight: 700; }
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {
    background: %(surface2)s; color: %(text)s;
    border: 1px solid %(border)s; border-radius: 8px; padding: 5px 8px; min-height: 18px;
}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus { border-color: %(accent)s; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: %(surface)s; color: %(text)s;
    border: 1px solid %(border)s; selection-background-color: %(accent)s; selection-color: %(accent_text)s;
    outline: none;
}
QPushButton {
    background: %(surface2)s; color: %(text)s;
    border: 1px solid %(border)s; border-radius: 8px; padding: 5px 12px;
}
QPushButton:hover { background: %(raised)s; }
QPushButton:default { background: %(accent)s; color: %(accent_text)s; border-color: %(accent)s; }
QRadioButton, QCheckBox { color: %(text)s; spacing: 6px; }
QMenu { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; }
QMenu::item:selected { background: %(accent)s; color: %(accent_text)s; }
QToolTip { background: %(surface2)s; color: %(text)s; border: 1px solid %(border)s; }
"""


def build_qss(theme_name: str) -> str:
    return _QSS_TEMPLATE % palette(theme_name)


def apply_theme(app, theme_name: str) -> str:
    """Apply the stylesheet app-wide. Returns the effective theme ('dark'/'light')."""
    eff = effective_theme(theme_name)
    try:
        app.setStyleSheet(build_qss(theme_name))
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to apply theme: %s", e)
    return eff
