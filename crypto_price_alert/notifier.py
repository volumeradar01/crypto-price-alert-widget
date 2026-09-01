"""Desktop notifications via the system-tray balloon message."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QSystemTrayIcon

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, tray_icon: QSystemTrayIcon):
        self._tray = tray_icon

    def notify(self, title: str, body: str, seconds: int = 8):
        try:
            self._tray.showMessage(
                title, body, QSystemTrayIcon.MessageIcon.Information, seconds * 1000
            )
        except Exception as e:  # noqa: BLE001 - notifications are best effort
            log.warning("Notification failed: %s", e)
