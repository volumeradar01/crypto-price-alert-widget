"""Add/edit-alert dialog (with searchable symbol picker + live price) and settings."""

from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QStringListModel, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import symbols
from .config import MAX_INTERVAL, MIN_INTERVAL
from .models import Alert, _quote_asset
from .sound import get_player
from .sources import probe_price

_SOUND_FILTER = "Audio files (*.wav *.mp3 *.ogg *.flac);;All files (*)"


def _row(*widgets: QWidget) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    for x in widgets:
        lay.addWidget(x)
    return w


def _fmt(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    if v >= 1000:
        return f"{v:,.2f}"
    if v >= 1:
        return f"{v:,.4f}"
    return f"{v:.8f}".rstrip("0").rstrip(".")


class AlertDialog(QDialog):
    """Create or edit one alert. On accept, ``result_alert`` holds it."""

    _symbolsLoaded = Signal(str, list)
    _priceProbed = Signal(str, object)

    def __init__(self, config, alert: Alert | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit alert" if alert else "New alert")
        self.setModal(True)
        self.setMinimumWidth(380)
        self._config = config
        self._alert = alert
        self.result_alert: Alert | None = None

        self._cg_display_to_id: dict[str, str] = {}
        self._cg_ids: set[str] = set()
        self._bn_symbols: set[str] = set()

        self.source = QComboBox()
        self.source.addItem("CoinGecko", "coingecko")
        self.source.addItem("Binance", "binance")

        self.market = QComboBox()
        self.market.addItem("Spot", "spot")
        self.market.addItem("Futures", "futures")
        self.market_label = QLabel("Market")

        self.ident = QLineEdit()
        self.ident_label = QLabel()
        self._completer_model = QStringListModel(self)
        completer = QCompleter(self._completer_model, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setMaxVisibleItems(12)
        self.ident.setCompleter(completer)

        self.ident_hint = QLabel("type to search")
        self.ident_hint.setProperty("role", "hint")
        self.current_lbl = QLabel("Current: —")
        self.current_lbl.setProperty("role", "current")

        self.vs = QLineEdit("usd")
        self.vs_label = QLabel("Vs currency")

        self.name = QLineEdit()

        self.threshold = QDoubleSpinBox()
        self.threshold.setDecimals(8)
        self.threshold.setRange(0.0, 1e12)
        self.threshold.setGroupSeparatorShown(True)
        self.threshold.setButtonSymbols(QDoubleSpinBox.NoButtons)

        self.dir_above = QRadioButton("Rises above")
        self.dir_below = QRadioButton("Falls below")
        self.dir_above.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.dir_above)
        grp.addButton(self.dir_below)

        self.sound = QLineEdit()
        self.sound.setPlaceholderText("(use the global sound)")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        test = QPushButton("Test")
        test.clicked.connect(self._test)

        self._form = form = QFormLayout()
        form.addRow("Source", self.source)
        form.addRow(self.market_label, self.market)
        form.addRow(self.ident_label, _row(self.ident))
        form.addRow("", _row(self.ident_hint, self.current_lbl))
        form.addRow(self.vs_label, self.vs)
        form.addRow("Name (optional)", self.name)
        form.addRow("Threshold", self.threshold)
        form.addRow("Direction", _row(self.dir_above, self.dir_below))
        form.addRow("Alert sound", _row(self.sound, browse, test))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self._probe_timer = QTimer(self)
        self._probe_timer.setSingleShot(True)
        self._probe_timer.timeout.connect(self._probe_now)

        self._symbolsLoaded.connect(self._on_symbols_loaded)
        self._priceProbed.connect(self._on_price_probed)

        self.source.currentIndexChanged.connect(self._on_target_changed)
        self.market.currentIndexChanged.connect(self._on_target_changed)
        self.ident.textEdited.connect(lambda _t: self._probe_timer.start(450))
        self.vs.textEdited.connect(lambda _t: self._probe_timer.start(600))

        # a fresh alert defaults to the user's source, Futures market, and an
        # empty symbol box (the "BTCUSDT" placeholder is the hint)
        self._load(alert or Alert(
            threshold=0.0, source=config.default_source,
            market="futures", symbol="", coin_id="",
        ))
        self._on_target_changed()

    # ----- reactive plumbing -------------------------------------
    def _is_coingecko(self) -> bool:
        return self.source.currentData() == "coingecko"

    def _set_row_visible(self, field_widget, visible: bool):
        try:
            self._form.setRowVisible(field_widget, visible)
        except (AttributeError, TypeError):  # Qt < 6.4
            field_widget.setVisible(visible)

    def _on_target_changed(self):
        cg = self._is_coingecko()
        self.ident_label.setText("CoinGecko coin" if cg else "Binance symbol")
        self.ident.setPlaceholderText("bitcoin" if cg else "BTCUSDT")
        self._set_row_visible(self.market, not cg)
        self._set_row_visible(self.vs, cg)
        self._reload_symbols()
        self._probe_timer.start(150)

    def _reload_symbols(self):
        kind = "coingecko_coins" if self._is_coingecko() else symbols.binance_key(self.market.currentData())
        self._completer_model.setStringList([])
        symbols.get_async(kind, lambda k, items: self._symbolsLoaded.emit(k, items))

    @Slot(str, list)
    def _on_symbols_loaded(self, kind: str, items: list):
        cur_kind = "coingecko_coins" if self._is_coingecko() else symbols.binance_key(self.market.currentData())
        if kind != cur_kind:
            return
        if kind == "coingecko_coins":
            self._cg_display_to_id.clear()
            self._cg_ids.clear()
            display = []
            for cid, sym, name in items:
                d = f"{name}  ·  {sym}  ·  {cid}"
                display.append(d)
                self._cg_display_to_id[d] = cid
                self._cg_ids.add(cid)
            self._completer_model.setStringList(display)
        else:
            self._bn_symbols = set(items)
            self._completer_model.setStringList(list(items))

    def _probe_target(self) -> Alert | None:
        ident = self.ident.text().strip()
        if not ident:
            return None
        a = Alert(threshold=0.0)
        a.source = self.source.currentData()
        if a.source == "coingecko":
            a.coin_id = self._resolve_identifier()[0]
            a.vs_currency = (self.vs.text().strip() or "usd").lower()
        else:
            a.market = self.market.currentData()
            a.symbol = ident.upper()
        return a

    def _probe_now(self):
        target = self._probe_target()
        if target is None:
            self.current_lbl.setText("Current: —")
            return
        token = f"{target.source}|{getattr(target, 'market', '')}|{target.query_key()}|{target.vs_currency}"
        self._probe_token = token
        self.current_lbl.setText("Current: …")

        def work():
            price = probe_price(target)
            self._priceProbed.emit(token, price)

        threading.Thread(target=work, name="price-probe", daemon=True).start()

    @Slot(str, object)
    def _on_price_probed(self, token: str, price):
        if token != getattr(self, "_probe_token", None):
            return
        if price is None:
            self.current_lbl.setText("Current: unavailable")
            return
        unit = (self.vs.text().strip().upper() if self._is_coingecko()
                else _quote_asset(self.ident.text()))
        self.current_lbl.setText(f"Current: {_fmt(price)} {unit}".rstrip())
        self._last_probe_price = float(price)

    # ----- load / resolve / accept -----------------------------
    def _load(self, a: Alert):
        self.source.setCurrentIndex(max(0, self.source.findData(a.source)))
        self.market.setCurrentIndex(max(0, self.market.findData(a.market)))
        self.ident.setText(a.coin_id if a.source == "coingecko" else a.symbol)
        self.vs.setText(a.vs_currency or "usd")
        self.name.setText(a.label)
        self.threshold.setValue(a.threshold)
        (self.dir_above if a.direction == "above" else self.dir_below).setChecked(True)
        self.sound.setText(a.sound_path or "")

    def _resolve_identifier(self) -> tuple[str, str | None]:
        text = self.ident.text().strip()
        if not self._is_coingecko():
            return text.upper(), None
        if text in self._cg_display_to_id:
            return self._cg_display_to_id[text], None
        low = text.lower()
        if not self._cg_ids or low in self._cg_ids:
            return low, None
        return low, "unknown"

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose alert sound", "", _SOUND_FILTER)
        if path:
            self.sound.setText(path)

    def _test(self):
        get_player().test(self.sound.text().strip() or self._config.global_sound_path or None)

    def _accept(self):
        ident = self.ident.text().strip()
        if not ident:
            QMessageBox.warning(self, "Missing value", "Enter a coin or trading symbol.")
            return
        if self.threshold.value() <= 0:
            QMessageBox.warning(self, "Invalid threshold", "Threshold must be greater than zero.")
            return

        source = self.source.currentData()
        market = self.market.currentData()
        if source == "binance":
            sym = ident.upper()
            if self._bn_symbols and sym not in self._bn_symbols:
                QMessageBox.warning(
                    self, "Unknown symbol",
                    f"'{sym}' is not a tradable Binance {market} symbol.\n"
                    "Pick one from the search list.",
                )
                return
            coin_id = "bitcoin"
        else:
            coin_id, status = self._resolve_identifier()
            if status == "unknown" and QMessageBox.question(
                self, "Unrecognised coin",
                f"'{coin_id}' isn't in the CoinGecko list. Use it anyway?",
            ) != QMessageBox.Yes:
                return

        a = self._alert or Alert(threshold=0.0)
        a.source = source
        a.market = market
        if source == "coingecko":
            a.coin_id = coin_id
            a.vs_currency = (self.vs.text().strip() or "usd").lower()
        else:
            a.symbol = ident.upper()
        a.label = self.name.text().strip()
        a.threshold = float(self.threshold.value())
        a.direction = "above" if self.dir_above.isChecked() else "below"
        a.sound_path = self.sound.text().strip() or None
        a.enabled = True
        a.rearm()
        self.result_alert = a
        self.accept()


class SettingsDialog(QDialog):
    """Global settings. Call ``apply_to(config)`` after ``exec()`` returns truthy."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(360)
        self._config = config

        self.interval = QSpinBox()
        self.interval.setRange(MIN_INTERVAL, MAX_INTERVAL)
        self.interval.setSuffix(" s")
        self.interval.setValue(config.poll_interval_seconds)

        self.default_source = QComboBox()
        self.default_source.addItem("CoinGecko", "coingecko")
        self.default_source.addItem("Binance", "binance")
        self.default_source.setCurrentIndex(
            max(0, self.default_source.findData(config.default_source))
        )

        self.appearance = QComboBox()
        for label, val in (("Dark", "dark"), ("Light", "light"), ("Follow system", "system")):
            self.appearance.addItem(label, val)
        self.appearance.setCurrentIndex(max(0, self.appearance.findData(config.theme)))

        self.sound = QLineEdit(config.global_sound_path)
        self.sound.setPlaceholderText("(built-in chime)")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        test = QPushButton("Test")
        test.clicked.connect(self._test)

        self.on_top = QCheckBox("Keep widget above other windows")
        self.on_top.setChecked(config.always_on_top)
        self.autostart = QCheckBox("Start automatically when I log in")
        self.autostart.setChecked(config.autostart)

        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(50, 100)
        self.opacity.setValue(int(round(config.opacity * 100)))
        self.opacity_value = QLabel(f"{self.opacity.value()}%")
        self.opacity.valueChanged.connect(lambda v: self.opacity_value.setText(f"{v}%"))

        form = QFormLayout()
        form.addRow("Check prices every", self.interval)
        form.addRow("Default source for new alerts", self.default_source)
        form.addRow("Appearance", self.appearance)
        form.addRow("Global alert sound", _row(self.sound, browse, test))
        form.addRow("Widget opacity", _row(self.opacity, self.opacity_value))
        form.addRow("", self.on_top)
        form.addRow("", self.autostart)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose global alert sound", "", _SOUND_FILTER)
        if path:
            self.sound.setText(path)

    def _test(self):
        get_player().test(self.sound.text().strip() or None)

    def apply_to(self, config) -> None:
        config.poll_interval_seconds = int(self.interval.value())
        config.default_source = self.default_source.currentData()
        config.theme = self.appearance.currentData()
        config.global_sound_path = self.sound.text().strip()
        config.always_on_top = self.on_top.isChecked()
        config.opacity = self.opacity.value() / 100.0
        config.autostart = self.autostart.isChecked()
