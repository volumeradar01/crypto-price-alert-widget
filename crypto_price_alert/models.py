"""Alert data model and (de)serialization."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field, fields
from typing import Optional

DIRECTIONS = ("above", "below")
SOURCES = ("coingecko", "binance")
MARKETS = ("spot", "futures")

# Common Binance quote assets, longest first so e.g. BTCUSDT -> USDT not USD.
_QUOTE_ASSETS = (
    "USDT", "USDC", "FDUSD", "TUSD", "BUSD", "DAI",
    "BTC", "ETH", "BNB", "EUR", "GBP", "TRY", "BRL", "AUD",
)


def _quote_asset(symbol: str) -> str:
    s = (symbol or "").upper()
    for q in _QUOTE_ASSETS:
        if s.endswith(q) and len(s) > len(q):
            return q
    return ""


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Alert:
    """A single price alert.

    ``armed`` gates whether the alert can fire. ``triggered_state`` latches the
    last direction that fired ("above"/"below") so the widget can colour the row
    and so we don't re-notify every poll. The user clears it with **Re-arm**.
    """

    threshold: float
    direction: str = "above"          # "above" | "below"
    source: str = "coingecko"         # "coingecko" | "binance"
    coin_id: str = "bitcoin"          # CoinGecko id
    symbol: str = "BTCUSDT"           # Binance trading pair
    market: str = "spot"              # Binance market: "spot" | "futures"
    vs_currency: str = "usd"          # CoinGecko quote currency
    label: str = ""                   # optional friendly name
    sound_path: Optional[str] = None  # per-alert sound override
    enabled: bool = True
    armed: bool = True
    triggered_state: str = "none"     # "none" | "above" | "below"
    last_price: Optional[float] = None
    last_triggered_at: Optional[str] = None
    id: str = field(default_factory=_new_id)

    # ----- helpers -------------------------------------------------------
    def display_label(self) -> str:
        if self.label.strip():
            return self.label.strip()
        return self.coin_id.upper() if self.source == "coingecko" else self.symbol.upper()

    def query_key(self) -> str:
        """Identifier used when calling the price source."""
        if self.source == "coingecko":
            return self.coin_id.strip().lower()
        return self.symbol.strip().upper()

    def unit(self) -> str:
        if self.source == "coingecko":
            return (self.vs_currency or "").upper()
        return _quote_asset(self.symbol)

    def source_label(self) -> str:
        if self.source == "coingecko":
            return "CoinGecko"
        return "Binance Futures" if self.market == "futures" else "Binance Spot"

    def stream_market(self) -> str:
        """Binance market key ('spot' or 'futures'); 'spot' for non-Binance."""
        return self.market if self.source == "binance" and self.market in MARKETS else "spot"

    def rearm(self) -> None:
        """Start watching again from a clean state."""
        self.armed = True
        self.triggered_state = "none"

    def dismiss(self) -> None:
        """Acknowledge a fired alert: clear the highlight, leave it disarmed."""
        self.armed = False
        self.triggered_state = "none"

    def is_triggered(self) -> bool:
        return self.triggered_state in ("above", "below")

    # ----- persistence -------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Alert":
        allowed = {f.name for f in fields(cls)}
        clean = {k: v for k, v in (data or {}).items() if k in allowed}
        if "threshold" not in clean:
            clean["threshold"] = 0.0
        alert = cls(**clean)
        if alert.direction not in DIRECTIONS:
            alert.direction = "above"
        if alert.source not in SOURCES:
            alert.source = "coingecko"
        if alert.market not in MARKETS:
            alert.market = "spot"
        if alert.triggered_state not in ("none", "above", "below"):
            alert.triggered_state = "none"
        try:
            alert.threshold = float(alert.threshold)
        except (TypeError, ValueError):
            alert.threshold = 0.0
        return alert
