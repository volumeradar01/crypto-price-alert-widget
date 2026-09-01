"""Live price feed.

Runs on its own QThread. Binance spot/futures prices arrive over WebSocket
(`<symbol>@bookTicker` combined streams -> best bid/ask mid price, re-subscribed
when the alert set changes); CoinGecko is polled over REST on a timer, which also
acts as a fallback for any Binance symbol whose socket is down or stale.
Threshold crossings are evaluated on every update and latched until the user
re-arms or dismisses.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtWebSockets import QWebSocket

from .config import MAX_INTERVAL, MIN_INTERVAL
from .sources import BinanceSource, CoinGeckoSource, SourceError

log = logging.getLogger(__name__)

_WS_BASE = {
    "spot": "wss://stream.binance.com:9443/stream?streams=",
    "futures": "wss://fstream.binance.com/stream?streams=",
}
_RECONNECT_MS = 3000
_FLUSH_MS = 700


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _mid_price(bid, ask):
    b, a = _to_float(bid), _to_float(ask)
    if b is not None and a is not None and b > 0 and a > 0:
        return (b + a) / 2.0
    return b if b else a


class PriceFeed(QObject):
    pricesUpdated = Signal(dict)          # {alert_id: price}
    alertTriggered = Signal(str, float)   # alert_id, price
    feedStatus = Signal(str, bool)        # short label, ok?

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._paused = bool(config.polling_paused)

        self._rest_timer: QTimer | None = None
        self._flush_timer: QTimer | None = None
        self._ws: dict[str, QWebSocket] = {}
        self._ws_ready: dict[str, bool] = {}
        self._want: dict[str, set[str]] = {}       # market -> subscribed symbols
        self._reconnect: dict[str, QTimer] = {}
        self._ws_prices: dict[tuple[str, str], tuple[float, float]] = {}  # (mkt,sym)->(price,ts)
        self._rest_prices: dict[str, float] = {}   # alert_id -> price
        self._dirty = False

    # ----- lifecycle (all runs on the feed thread) ------------------
    @Slot()
    def start(self):
        self._flush_timer = QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.timeout.connect(self._flush)

        self._rest_timer = QTimer(self)
        self._rest_timer.timeout.connect(self._poll_rest)
        self._rest_timer.start(self._interval_ms())

        if not self._paused:
            self.resubscribe()
            QTimer.singleShot(0, self._poll_rest)
        else:
            self.feedStatus.emit("paused", False)

    @Slot()
    def stop(self):
        for ws in list(self._ws.values()):
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass
        self._ws.clear()

    @Slot(int)
    def set_interval(self, seconds: int):
        seconds = max(MIN_INTERVAL, min(MAX_INTERVAL, int(seconds)))
        self.config.poll_interval_seconds = seconds
        if self._rest_timer is not None:
            self._rest_timer.setInterval(seconds * 1000)

    @Slot()
    def pause(self):
        self._paused = True
        for market in list(self._ws):
            self._close_ws(market)
        self._want.clear()
        self.feedStatus.emit("paused", False)

    @Slot()
    def resume(self):
        self._paused = False
        self.resubscribe()
        QTimer.singleShot(0, self._poll_rest)

    @Slot()
    def resubscribe(self):
        """Recompute Binance WebSocket subscriptions from the current alerts."""
        if self._paused:
            return
        desired: dict[str, set[str]] = {"spot": set(), "futures": set()}
        for a in self.config.alerts:
            if a.enabled and a.source == "binance" and a.symbol.strip():
                desired[a.stream_market()].add(a.symbol.strip().upper())

        for market, syms in desired.items():
            if syms and syms != self._want.get(market):
                self._open_ws(market, syms)
            elif not syms and market in self._ws:
                self._close_ws(market)

    # ----- websocket plumbing -------------------------------------
    def _interval_ms(self) -> int:
        return max(MIN_INTERVAL, int(self.config.poll_interval_seconds)) * 1000

    def _open_ws(self, market: str, symbols: set[str]):
        self._close_ws(market)
        self._want[market] = set(symbols)
        self._ws_ready[market] = False
        streams = "/".join(f"{s.lower()}@bookTicker" for s in sorted(symbols))
        url = QUrl(_WS_BASE[market] + streams)

        ws = QWebSocket()
        ws.connected.connect(lambda m=market: self._on_ws_connected(m))
        ws.disconnected.connect(lambda m=market: self._on_ws_disconnected(m))
        ws.textMessageReceived.connect(lambda msg, m=market: self._on_ws_message(m, msg))
        try:
            ws.errorOccurred.connect(lambda _e, m=market: self._on_ws_disconnected(m))
        except (AttributeError, TypeError):  # older Qt
            pass
        self._ws[market] = ws
        ws.open(url)
        log.info("WS %s subscribing: %s", market, ", ".join(sorted(symbols)))

    def _close_ws(self, market: str):
        ws = self._ws.pop(market, None)
        self._ws_ready.pop(market, None)
        self._want.pop(market, None)
        if ws is not None:
            try:
                ws.textMessageReceived.disconnect()
                ws.disconnected.disconnect()
                ws.connected.disconnect()
            except (RuntimeError, TypeError):
                pass
            ws.close()
            ws.deleteLater()

    def _on_ws_connected(self, market: str):
        self._ws_ready[market] = True
        log.info("WS %s connected", market)
        self._mark_dirty()

    def _on_ws_disconnected(self, market: str):
        self._ws_ready[market] = False
        if self._paused or not self._want.get(market):
            return
        timer = self._reconnect.get(market)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(
                lambda m=market: self._open_ws(m, self._want.get(m, set()))
                if self._want.get(m) and not self._paused else None
            )
            self._reconnect[market] = timer
        if not timer.isActive():
            timer.start(_RECONNECT_MS)

    def _on_ws_message(self, market: str, message: str):
        try:
            payload = json.loads(message)
        except ValueError:
            return
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return
        symbol = data.get("s")
        if not symbol:
            return
        price = _mid_price(data.get("b"), data.get("a")) or _to_float(data.get("p"))
        if price is None:
            return
        self._ws_prices[(market, symbol.upper())] = (price, time.monotonic())
        self._mark_dirty()

    # ----- REST polling / fallback -------------------------------
    @Slot()
    def _poll_rest(self):
        if self._paused:
            return
        alerts = [a for a in self.config.alerts if a.enabled]
        if not alerts:
            self._rest_prices.clear()
            return

        prices: dict[str, float] = {}
        errors: list[str] = []

        cg = [a for a in alerts if a.source == "coingecko"]
        if cg:
            try:
                prices.update(CoinGeckoSource().get_prices(cg))
            except SourceError as e:
                errors.append(f"coingecko: {e}")

        for market in ("spot", "futures"):
            grp = [
                a for a in alerts
                if a.source == "binance" and a.stream_market() == market
                and not self._ws_fresh(market, a.symbol)
            ]
            if not grp:
                continue
            try:
                prices.update(BinanceSource(market).get_prices(grp))
            except SourceError as e:
                errors.append(f"binance/{market}: {e}")
            except Exception as e:  # noqa: BLE001
                log.exception("binance %s poll failed", market)
                errors.append(f"binance/{market}: {e}")

        self._rest_prices.update(prices)
        self._flush()
        if errors and not self._any_price():
            self.feedStatus.emit("offline", False)

    # ----- evaluation / emit ------------------------------------
    def _mark_dirty(self):
        self._dirty = True
        if self._flush_timer is not None and not self._flush_timer.isActive():
            self._flush_timer.start(_FLUSH_MS)

    def _ws_fresh(self, market: str, symbol: str) -> bool:
        entry = self._ws_prices.get((market, symbol.strip().upper()))
        if not entry or not self._ws_ready.get(market):
            return False
        max_age = max(20.0, 3 * self.config.poll_interval_seconds)
        return (time.monotonic() - entry[1]) <= max_age

    def _price_for(self, alert) -> float | None:
        if alert.source == "binance":
            entry = self._ws_prices.get((alert.stream_market(), alert.symbol.strip().upper()))
            if entry and self._ws_fresh(alert.stream_market(), alert.symbol):
                return entry[0]
        return self._rest_prices.get(alert.id)

    def _any_price(self) -> bool:
        return bool(self._rest_prices) or bool(self._ws_prices)

    @Slot()
    def _flush(self):
        self._dirty = False
        out: dict[str, float] = {}
        for a in self.config.alerts:
            if not a.enabled:
                continue
            price = self._price_for(a)
            if price is not None:
                a.last_price = price
                out[a.id] = price
        if out:
            self.pricesUpdated.emit(out)
        self._evaluate()

        if self._paused:
            return
        live = any(self._ws_ready.values())
        if out:
            self.feedStatus.emit("live" if live else "polling", True)
        elif not self._any_price():
            self.feedStatus.emit("connecting", False)

    def _evaluate(self):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for a in self.config.alerts:
            if not a.enabled or not a.armed:
                continue
            price = self._price_for(a)
            if price is None:
                continue
            crossed = (
                (a.direction == "above" and price >= a.threshold)
                or (a.direction == "below" and price <= a.threshold)
            )
            if crossed and a.triggered_state != a.direction:
                a.armed = False
                a.triggered_state = a.direction
                a.last_triggered_at = now
                self.alertTriggered.emit(a.id, float(price))
