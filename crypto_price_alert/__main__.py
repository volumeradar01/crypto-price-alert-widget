"""Entry point: single-instance guard, tray + widget + background price feed."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QMetaObject, QObject, Qt, QThread, Signal, Slot
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import autostart, theme
from .config import Config
from .feed import PriceFeed
from .notifier import Notifier
from .resources import app_icon
from .sound import Alarm, get_player
from .tray import Tray
from .widget import DesktopWidget

log = logging.getLogger(__name__)

_IPC_NAME = "CryptoPriceAlert.singleton.v1"


class Controller(QObject):
    """GUI-thread bridge between the feed and the widget/sound/notify/persist,
    and forwards control requests to the feed thread via queued signals."""

    requestPause = Signal()
    requestResume = Signal()
    requestInterval = Signal(int)
    requestResubscribe = Signal()

    def __init__(self, config, widget, tray, notifier, player):
        super().__init__()
        self.config = config
        self.widget = widget
        self.tray = tray
        self.notifier = notifier
        self.player = player
        self.alarm = Alarm()
        self._autostart_state = config.autostart

    @Slot(dict)
    def on_prices(self, prices):
        self.widget.on_prices(prices)

    @Slot(str, float)
    def on_triggered(self, alert_id, price):
        alert = next((a for a in self.config.alerts if a.id == alert_id), None)
        if alert is None:
            return
        self.widget.on_triggered(alert_id)
        arrow = "▲" if alert.direction == "above" else "▼"
        unit = alert.unit()
        self.notifier.notify(
            f"{alert.display_label()} {arrow} {alert.direction} {alert.threshold:g}",
            f"Now {price:g} {unit} — via {alert.source_label()}".strip(),
        )
        self.refresh_alarm()
        self.config.save()

    @Slot()
    def refresh_alarm(self):
        """Keep the alert sound looping while any alert stays triggered."""
        triggered = [a for a in self.config.alerts if a.enabled and a.is_triggered()]
        if not triggered:
            self.alarm.stop()
            return
        latest = max(triggered, key=lambda a: a.last_triggered_at or "")
        self.alarm.start(latest.sound_path or self.config.global_sound_path or None)

    @Slot(str, bool)
    def on_feed_status(self, text, ok):
        self.widget.on_feed_status(text, ok)

    @Slot()
    def persist(self):
        self.config.save()

    @Slot(bool)
    def on_pause_changed(self, paused):
        (self.requestPause if paused else self.requestResume).emit()
        self.tray.reflect_pause(paused)

    @Slot()
    def on_alerts_changed(self):
        self.requestResubscribe.emit()
        self.config.save()

    @Slot()
    def on_settings_changed(self):
        self.requestInterval.emit(self.config.poll_interval_seconds)
        if self.config.autostart != self._autostart_state:
            if self.config.autostart:
                if autostart.enable():
                    QMessageBox.information(
                        self.widget, "Start on sign-in",
                        "Crypto Price Alerts will now open automatically when you "
                        "sign in to Windows.\n\nYou can turn this off here again, or in "
                        "Task Manager → Startup apps.",
                    )
                else:
                    self.config.autostart = False
                    QMessageBox.warning(
                        self.widget, "Couldn't enable auto-start",
                        "Windows blocked the change to the startup list. Try running "
                        "the app once as administrator, or add it manually in "
                        "Task Manager → Startup apps.",
                    )
            else:
                autostart.disable()
            self._autostart_state = self.config.autostart
        self.config.save()


def _ping_existing_instance() -> bool:
    sock = QLocalSocket()
    sock.connectToServer(_IPC_NAME)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def _setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        from logging.handlers import RotatingFileHandler

        from .config import app_data_dir

        handlers.append(
            RotatingFileHandler(
                str(app_data_dir() / "app.log"),
                maxBytes=512_000,
                backupCount=2,
                encoding="utf-8",
            )
        )
    except Exception:  # noqa: BLE001 - console logging is enough
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,  # win over any handler a bootstrap/runtime hook already added
    )


def main() -> int:
    _setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("Crypto Price Alerts")
    app.setOrganizationName("CryptoPriceAlert")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())

    if _ping_existing_instance():
        log.info("Another instance is already running; asked it to show. Exiting.")
        return 0

    QLocalServer.removeServer(_IPC_NAME)
    server = QLocalServer()
    server.listen(_IPC_NAME)

    config = Config.load()
    theme.apply_theme(app, config.theme)
    player = get_player()
    widget = DesktopWidget(config)

    tray = Tray(
        widget,
        on_add=widget.add_alert_dialog,
        on_settings=widget.open_settings_dialog,
        on_toggle_pause=widget._toggle_pause,
        on_quit=app.quit,
    )
    notifier = Notifier(tray)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.information(
            widget, "Crypto Price Alerts",
            "The system tray is not available on this system.\n"
            "The widget still works; close it from the ✕ button and quit via Task Manager.",
        )
    tray.show()
    tray.reflect_pause(config.polling_paused)

    controller = Controller(config, widget, tray, notifier, player)

    thread = QThread()
    thread.setObjectName("price-feed")
    feed = PriceFeed(config)
    feed.moveToThread(thread)
    thread.started.connect(feed.start)

    feed.pricesUpdated.connect(controller.on_prices)
    feed.alertTriggered.connect(controller.on_triggered)
    feed.feedStatus.connect(controller.on_feed_status)

    controller.requestPause.connect(feed.pause)
    controller.requestResume.connect(feed.resume)
    controller.requestInterval.connect(feed.set_interval)
    controller.requestResubscribe.connect(feed.resubscribe)

    widget.configChanged.connect(controller.persist)
    widget.alertsChanged.connect(controller.on_alerts_changed)
    widget.alertsChanged.connect(controller.refresh_alarm)
    widget.acknowledged.connect(controller.refresh_alarm)
    widget.pauseChanged.connect(controller.on_pause_changed)
    widget.settingsChanged.connect(controller.on_settings_changed)

    server.newConnection.connect(lambda: _handle_ipc(server, widget))

    # self-heal: recreate the Startup shortcut if it's missing or points nowhere
    # (e.g. the app was moved, or reinstalled to a new path)
    if config.autostart and not autostart.target_ok():
        autostart.enable()

    thread.start()
    widget.show()
    controller.refresh_alarm()  # resume beeping if an alert was left triggered

    def _shutdown():
        controller.alarm.stop()
        config.save()
        try:
            QMetaObject.invokeMethod(feed, "stop", Qt.BlockingQueuedConnection)
        except Exception:  # noqa: BLE001
            pass
        thread.quit()
        thread.wait(2000)

    app.aboutToQuit.connect(_shutdown)
    return app.exec()


def _handle_ipc(server: QLocalServer, widget: DesktopWidget):
    conn = server.nextPendingConnection()
    if conn is not None:
        conn.waitForReadyRead(200)
        conn.readAll()
        conn.disconnectFromServer()
    widget.show()
    widget.raise_()
    widget.activateWindow()


if __name__ == "__main__":
    raise SystemExit(main())
