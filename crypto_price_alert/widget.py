"""The always-on-top desktop widget: a draggable card listing alerts."""

from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .dialogs import AlertDialog, SettingsDialog
from .icons import make_icon
from .models import Alert

log = logging.getLogger(__name__)

_THEME_NEXT = {"dark": "light", "light": "system", "system": "dark"}
_THEME_ICON = {"dark": "moon", "light": "sun", "system": "half"}

_SCANNERS = (
    ("Relative Volume Scanner", "https://volumeradar.com/volume-scanner"),
    ("Market Structure Scanner", "https://volumeradar.com/market-structure-scanner"),
)


def _fmt_price(value) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v >= 1000:
        return f"{v:,.2f}"
    if v >= 1:
        return f"{v:,.4f}"
    return f"{v:.8f}".rstrip("0").rstrip(".")


def _tool_button(icon_name: str, tip: str) -> QPushButton:
    b = QPushButton()
    b.setObjectName("tool")
    b.setToolTip(tip)
    b.setFixedSize(28, 28)
    b.setIconSize(QSize(15, 15))
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.NoFocus)
    b.setProperty("iconName", icon_name)
    return b


class _DragBar(QWidget):
    """Header strip that drags the whole frameless window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._offset = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._offset is not None and event.buttons() & Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._offset is not None:
            self._offset = None
            win = self.window()
            if isinstance(win, DesktopWidget):
                win._save_geometry()
            event.accept()


class _LinkRow(QWidget):
    """A clickable external link + a copy-to-clipboard button."""

    def __init__(self, label: str, url: str, parent=None):
        super().__init__(parent)
        self.url = url
        self._color = QColor("#5b9dff")

        self.open_btn = QPushButton(label)
        self.open_btn.setObjectName("link")
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.setFocusPolicy(Qt.NoFocus)
        self.open_btn.setToolTip(f"Open {url}")
        self.open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))

        self.copy_btn = QPushButton()
        self.copy_btn.setObjectName("linkcopy")
        self.copy_btn.setFixedSize(22, 22)
        self.copy_btn.setIconSize(QSize(12, 12))
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setFocusPolicy(Qt.NoFocus)
        self.copy_btn.setToolTip("Copy link")
        self.copy_btn.clicked.connect(self._copy)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self.open_btn, 1)
        lay.addWidget(self.copy_btn, 0)

        self._reset = QTimer(self)
        self._reset.setSingleShot(True)
        self._reset.timeout.connect(lambda: self.set_icon_color(self._color))

    def set_icon_color(self, color):
        self._color = color
        self.open_btn.setIcon(make_icon("external", color))
        self.copy_btn.setIcon(make_icon("copy", color))
        self.copy_btn.setToolTip("Copy link")

    def _copy(self):
        QApplication.clipboard().setText(self.url)
        self.copy_btn.setIcon(make_icon("check", QColor("#2bd66e")))
        self.copy_btn.setToolTip("Copied!")
        self._reset.start(1200)


class AlertRow(QFrame):
    reArm = Signal(str)
    dismissed = Signal(str)
    editRequested = Signal(str)
    toggleRequested = Signal(str)
    removeRequested = Signal(str)

    def __init__(self, alert: Alert, parent=None):
        super().__init__(parent)
        self.setObjectName("row")
        self.alert = alert
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

        self.name = QLabel()
        self.name.setObjectName("name")
        self.sub = QLabel()
        self.sub.setObjectName("sub")
        self.cond = QLabel()
        self.cond.setObjectName("cond")
        self.price = QLabel("—")
        self.price.setObjectName("price")

        self.rearm_btn = QPushButton("Re-arm")
        self.rearm_btn.setObjectName("rearm")
        self.dismiss_btn = QPushButton()
        self.dismiss_btn.setObjectName("dismiss")
        self.dismiss_btn.setToolTip("Dismiss — clear this alert")
        self.dismiss_btn.setFixedSize(26, 24)
        self.dismiss_btn.setIconSize(QSize(12, 12))
        self.dismiss_btn.setIcon(make_icon("close", "#9aa3b2"))
        for b in (self.rearm_btn, self.dismiss_btn):
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
        self.rearm_btn.clicked.connect(lambda: self.reArm.emit(self.alert.id))
        self.dismiss_btn.clicked.connect(lambda: self.dismissed.emit(self.alert.id))

        left = QVBoxLayout()
        left.setSpacing(2)
        left.addWidget(self.name)
        left.addWidget(self.sub)
        left.addWidget(self.cond)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        actions.addWidget(self.rearm_btn)
        actions.addWidget(self.dismiss_btn)

        right = QVBoxLayout()
        right.setSpacing(4)
        right.addWidget(self.price, 0, Qt.AlignRight)
        right.addLayout(actions)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(11, 9, 11, 9)
        outer.addLayout(left, 1)
        outer.addLayout(right, 0)
        self.refresh()

    def _context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("Edit…", lambda: self.editRequested.emit(self.alert.id))
        menu.addAction(
            "Disable" if self.alert.enabled else "Enable",
            lambda: self.toggleRequested.emit(self.alert.id),
        )
        menu.addSeparator()
        menu.addAction("Delete", lambda: self.removeRequested.emit(self.alert.id))
        menu.exec(self.mapToGlobal(pos))

    def _state(self) -> str:
        a = self.alert
        if not a.enabled:
            return "disabled"
        if a.triggered_state in ("above", "below"):
            return a.triggered_state
        return "armed"

    def refresh(self):
        a = self.alert
        self.name.setText(a.display_label())
        unit = a.unit()
        self.sub.setText(f"{a.source_label()} · {unit}" if unit else a.source_label())
        arrow = "▲" if a.direction == "above" else "▼"
        self.cond.setText(f"{arrow} {a.direction} {_fmt_price(a.threshold)}")
        self.price.setText(_fmt_price(a.last_price))
        triggered = a.triggered_state in ("above", "below")
        self.rearm_btn.setVisible(triggered)
        self.dismiss_btn.setVisible(triggered)
        self.setProperty("state", self._state())
        self.style().unpolish(self)
        self.style().polish(self)

    def update_price(self, price):
        self.alert.last_price = price
        self.price.setText(_fmt_price(price))

    def set_icon_color(self, color):
        self.dismiss_btn.setIcon(make_icon("close", color))


class DesktopWidget(QWidget):
    configChanged = Signal()
    settingsChanged = Signal()
    alertsChanged = Signal()      # add / edit / delete / enable-disable
    acknowledged = Signal()       # a triggered alert was re-armed or dismissed
    pauseChanged = Signal(bool)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._rows: dict[str, AlertRow] = {}

        self.setWindowTitle("Crypto Price Alerts")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._apply_window_flags()
        self.setWindowOpacity(config.opacity)
        self.setMinimumWidth(300)

        self.card = QFrame()
        self.card.setObjectName("card")
        shell = QVBoxLayout(self)
        shell.setContentsMargins(3, 3, 3, 3)  # just enough not to clip the rounded corners
        shell.addWidget(self.card)

        self.title = QLabel("₿  Price Alerts")
        self.title.setObjectName("title")
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.btn_add = _tool_button("plus", "Add alert")
        self.btn_pause = _tool_button("pause", "Pause checking")
        self.btn_theme = _tool_button("moon", "Theme")
        self.btn_settings = _tool_button("settings", "Settings")
        self.btn_hide = _tool_button("close", "Hide to tray")
        self._icon_color = QColor("#9aa3b2")

        header = _DragBar()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(2, 0, 2, 0)
        hl.setSpacing(4)
        hl.addWidget(self.title)
        hl.addStretch(1)
        hl.addWidget(self.status)
        hl.addSpacing(4)
        for b in (self.btn_add, self.btn_pause, self.btn_theme, self.btn_settings, self.btn_hide):
            hl.addWidget(b)

        self.empty = QLabel("No alerts yet.\nClick + to add one.")
        self.empty.setObjectName("empty")
        self.empty.setAlignment(Qt.AlignCenter)

        self._list_layout = QVBoxLayout()
        self._list_layout.setSpacing(7)
        self._list_layout.addStretch(1)
        holder = QWidget()
        holder.setObjectName("holder")
        holder.setLayout(self._list_layout)
        self._scroll = QScrollArea()
        self._scroll.setObjectName("scroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(holder)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.viewport().setStyleSheet("background: transparent;")

        self._footer = QWidget()
        fl = QVBoxLayout(self._footer)
        fl.setContentsMargins(0, 2, 0, 0)
        fl.setSpacing(2)
        sep = QFrame()
        sep.setObjectName("sep")
        sep.setFixedHeight(1)
        cap = QLabel("SCANNERS")
        cap.setObjectName("footcap")
        fl.addWidget(sep)
        fl.addWidget(cap)
        self._link_rows: list[_LinkRow] = []
        for name, url in _SCANNERS:
            lr = _LinkRow(name, url)
            self._link_rows.append(lr)
            fl.addWidget(lr)

        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(13, 11, 13, 13)
        cl.setSpacing(9)
        cl.addWidget(header)
        cl.addWidget(self.empty)
        cl.addWidget(self._scroll, 1)
        cl.addWidget(self._footer)

        self.btn_add.clicked.connect(self.add_alert_dialog)
        self.btn_settings.clicked.connect(self.open_settings_dialog)
        self.btn_hide.clicked.connect(self.hide)
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_theme.clicked.connect(self._cycle_theme)

        try:
            QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_system_scheme)
        except Exception:  # noqa: BLE001
            pass

        self.apply_theme()
        self._restore_geometry()
        self.rebuild()
        self._reflect_pause()

    # ----- theme --------------------------------------------------
    def apply_theme(self):
        app = QApplication.instance()
        if app is not None:
            theme.apply_theme(app, self.config.theme)
        pal = theme.palette(self.config.theme)
        self._icon_color = QColor(pal["text"])

        self.btn_theme.setProperty("iconName", _THEME_ICON.get(self.config.theme, "moon"))
        self.btn_theme.setToolTip(f"Theme: {self.config.theme} — click to change")
        for b in (self.btn_add, self.btn_pause, self.btn_theme, self.btn_settings, self.btn_hide):
            self._reicon(b)
        for row in self._rows.values():
            row.set_icon_color(self._icon_color)
        for lr in getattr(self, "_link_rows", []):
            lr.set_icon_color(QColor(pal["accent"]))

        for w in self.findChildren(QWidget):
            w.style().unpolish(w)
            w.style().polish(w)
        self.update()

    def _reicon(self, button):
        name = button.property("iconName")
        if name:
            button.setIcon(make_icon(name, self._icon_color))

    def _cycle_theme(self):
        self.config.theme = _THEME_NEXT.get(self.config.theme, "dark")
        self.apply_theme()
        self.configChanged.emit()

    def _on_system_scheme(self, _scheme):
        if self.config.theme == "system":
            self.apply_theme()

    # ----- window plumbing --------------------------------------
    def _apply_window_flags(self):
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self.config.always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def _restore_geometry(self):
        w = self.config.window
        self.resize(int(w.get("w", 330)), int(w.get("h", 420)))
        x, y = int(w.get("x", 140)), int(w.get("y", 140))
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            vg = screen.virtualGeometry()
            x = min(max(x, vg.left()), vg.right() - 80)
            y = min(max(y, vg.top()), vg.bottom() - 60)
        self.move(x, y)

    def _save_geometry(self):
        g = self.frameGeometry()
        self.config.window = {"x": g.x(), "y": g.y(), "w": self.width(), "h": self.height()}
        self.configChanged.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        off = getattr(self, "_offset", None)
        if off is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - off)
            event.accept()

    def mouseReleaseEvent(self, event):
        if getattr(self, "_offset", None) is not None:
            self._offset = None
            self._save_geometry()
            event.accept()

    def closeEvent(self, event):
        self._save_geometry()
        event.ignore()
        self.hide()

    def hideEvent(self, event):
        self._save_geometry()
        super().hideEvent(event)

    # ----- list management ------------------------------------
    def rebuild(self):
        for row in list(self._rows.values()):
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        for alert in self.config.alerts:
            self._add_row(alert)
        self._update_empty()

    def _add_row(self, alert: Alert):
        row = AlertRow(alert)
        row.set_icon_color(self._icon_color)
        row.reArm.connect(self._on_rearm)
        row.dismissed.connect(self._on_dismiss)
        row.editRequested.connect(self._on_edit)
        row.toggleRequested.connect(self._on_toggle)
        row.removeRequested.connect(self._on_remove)
        self._list_layout.insertWidget(self._list_layout.count() - 1, row)
        self._rows[alert.id] = row

    def _update_empty(self):
        has = bool(self.config.alerts)
        self.empty.setVisible(not has)
        self._scroll.setVisible(has)

    def _find(self, alert_id: str) -> Alert | None:
        return next((a for a in self.config.alerts if a.id == alert_id), None)

    # ----- row callbacks ------------------------------------
    def _on_rearm(self, alert_id: str):
        alert = self._find(alert_id)
        if alert is None:
            return
        alert.rearm()
        self._rows[alert_id].refresh()
        self.acknowledged.emit()
        self.configChanged.emit()

    def _on_dismiss(self, alert_id: str):
        alert = self._find(alert_id)
        if alert is None:
            return
        alert.dismiss()
        self._rows[alert_id].refresh()
        self.acknowledged.emit()
        self.configChanged.emit()

    def _on_edit(self, alert_id: str):
        alert = self._find(alert_id)
        if alert is None:
            return
        if AlertDialog(self.config, alert, self).exec():
            self._rows[alert_id].refresh()
            self.alertsChanged.emit()
            self.configChanged.emit()

    def _on_toggle(self, alert_id: str):
        alert = self._find(alert_id)
        if alert is None:
            return
        alert.enabled = not alert.enabled
        if alert.enabled:
            alert.rearm()
        else:
            alert.triggered_state = "none"
        self._rows[alert_id].refresh()
        self.alertsChanged.emit()
        self.configChanged.emit()

    def _on_remove(self, alert_id: str):
        alert = self._find(alert_id)
        if alert is None:
            return
        self.config.alerts.remove(alert)
        row = self._rows.pop(alert_id, None)
        if row is not None:
            row.setParent(None)
            row.deleteLater()
        self._update_empty()
        self.alertsChanged.emit()
        self.configChanged.emit()

    # ----- toolbar -------------------------------------------
    def add_alert_dialog(self):
        dialog = AlertDialog(self.config, None, self)
        if dialog.exec() and dialog.result_alert is not None:
            self.config.alerts.append(dialog.result_alert)
            self._add_row(dialog.result_alert)
            self._update_empty()
            self.alertsChanged.emit()
            self.configChanged.emit()

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.config, self)
        if not dialog.exec():
            return
        was_visible = self.isVisible()
        dialog.apply_to(self.config)
        self._apply_window_flags()
        self.setWindowOpacity(self.config.opacity)
        self.apply_theme()
        if was_visible:
            self.show()
        self.settingsChanged.emit()
        self.configChanged.emit()

    def _toggle_pause(self):
        self.config.polling_paused = not self.config.polling_paused
        self._reflect_pause()
        self.pauseChanged.emit(self.config.polling_paused)
        self.configChanged.emit()

    def _reflect_pause(self):
        paused = self.config.polling_paused
        self.btn_pause.setProperty("iconName", "play" if paused else "pause")
        self.btn_pause.setToolTip("Resume checking" if paused else "Pause checking")
        self._reicon(self.btn_pause)
        self.set_status("paused" if paused else "", "bad" if paused else "ok")

    # ----- feed-driven slots (GUI thread) -------------------
    def on_prices(self, prices: dict):
        for alert_id, price in prices.items():
            row = self._rows.get(alert_id)
            if row is not None:
                row.update_price(price)

    def on_triggered(self, alert_id: str):
        row = self._rows.get(alert_id)
        if row is not None:
            row.refresh()
        if self.config.always_on_top:
            self.raise_()

    def on_feed_status(self, text: str, ok: bool):
        if self.config.polling_paused:
            return
        tone = "live" if text == "live" else ("ok" if ok else "bad")
        self.set_status(text, tone)

    def set_status(self, text: str, tone: str = "ok"):
        self.status.setText(text)
        self.status.setProperty("tone", tone)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
