"""System-tray icon and its context menu."""

from __future__ import annotations

from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .resources import app_icon


class Tray(QSystemTrayIcon):
    def __init__(self, widget, on_add, on_settings, on_toggle_pause, on_quit, parent=None):
        super().__init__(app_icon(), parent)
        self.setToolTip("Crypto Price Alerts")
        self._widget = widget

        menu = QMenu()
        menu.addAction("Show / hide widget", self.toggle_widget)
        menu.addSeparator()
        menu.addAction("Add alert…", lambda: (self._reveal(), on_add()))
        menu.addAction("Settings…", lambda: (self._reveal(), on_settings()))
        self.act_pause = menu.addAction("Pause checking", on_toggle_pause)
        menu.addSeparator()
        menu.addAction("Quit", on_quit)
        self.setContextMenu(menu)

        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.toggle_widget()

    def _reveal(self):
        self._widget.show()
        self._widget.raise_()
        self._widget.activateWindow()

    def toggle_widget(self):
        if self._widget.isVisible():
            self._widget.hide()
        else:
            self._reveal()

    def reflect_pause(self, paused: bool):
        self.act_pause.setText("Resume checking" if paused else "Pause checking")
