"""REST price sources: CoinGecko, Binance spot + USDⓈ-M futures, and Yahoo Finance
(US + Indian equities).

These provide the batch fallback for the WebSocket feed and the one-off price
probe used by the alert dialog. No API key required for any of them.
"""

from __future__ import annotations

import json
import logging

import requests

log = logging.getLogger(__name__)

_TIMEOUT = 8
_HEADERS = {"Accept": "application/json", "User-Agent": "CryptoPriceAlert/1.1"}


class SourceError(RuntimeError):
    """Raised when a source cannot be reached or returns garbage."""


class CoinGeckoSource:
    name = "coingecko"
    URL = "https://api.coingecko.com/api/v3/simple/price"

    def get_prices(self, alerts) -> dict[str, float]:
        alerts = [a for a in alerts if a.coin_id.strip()]
        if not alerts:
            return {}
        ids = sorted({a.coin_id.strip().lower() for a in alerts})
        currencies = sorted({(a.vs_currency or "usd").strip().lower() for a in alerts})
        try:
            resp = requests.get(
                self.URL,
                params={"ids": ",".join(ids), "vs_currencies": ",".join(currencies)},
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            raise SourceError(str(e)) from e

        out: dict[str, float] = {}
        for a in alerts:
            cid = a.coin_id.strip().lower()
            cur = (a.vs_currency or "usd").strip().lower()
            price = (data.get(cid) or {}).get(cur)
            if price is not None:
                try:
                    out[a.id] = float(price)
                except (TypeError, ValueError):
                    pass
        return out

    def probe(self, coin_id: str, vs_currency: str = "usd") -> float | None:
        try:
            resp = requests.get(
                self.URL,
                params={"ids": coin_id.strip().lower(),
                        "vs_currencies": (vs_currency or "usd").strip().lower()},
                headers=_HEADERS, timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            v = (resp.json().get(coin_id.strip().lower()) or {}).get(
                (vs_currency or "usd").strip().lower()
            )
            return float(v) if v is not None else None
        except (requests.RequestException, ValueError, TypeError):
            return None


class BinanceSource:
    name = "binance"
    _BASE = {
        "spot": "https://api.binance.com/api/v3/ticker/price",
        "futures": "https://fapi.binance.com/fapi/v1/ticker/price",
    }

    def __init__(self, market: str = "spot"):
        self.market = "futures" if market == "futures" else "spot"
        self.url = self._BASE[self.market]

    def get_prices(self, alerts) -> dict[str, float]:
        alerts = [a for a in alerts if a.symbol.strip()]
        if not alerts:
            return {}
        symbols = sorted({a.symbol.strip().upper() for a in alerts})
        by_symbol = self._fetch(symbols)
        return {
            a.id: by_symbol[a.symbol.strip().upper()]
            for a in alerts
            if a.symbol.strip().upper() in by_symbol
        }

    def probe(self, symbol: str) -> float | None:
        got = self._fetch([symbol.strip().upper()])
        return got.get(symbol.strip().upper())

    def _fetch(self, symbols: list[str]) -> dict[str, float]:
        """Targeted query first; on failure (one bad symbol 400s the batch) fall
        back to the full ticker list and filter locally."""
        try:
            if len(symbols) == 1:
                resp = requests.get(self.url, params={"symbol": symbols[0]},
                                    headers=_HEADERS, timeout=_TIMEOUT)
                resp.raise_for_status()
                return self._index([resp.json()])
            resp = requests.get(
                self.url,
                params={"symbols": json.dumps(symbols, separators=(",", ":"))},
                headers=_HEADERS, timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            return self._index(resp.json())
        except (requests.RequestException, ValueError) as first_error:
            try:
                resp = requests.get(self.url, headers=_HEADERS, timeout=_TIMEOUT)
                resp.raise_for_status()
                return self._index(resp.json())
            except (requests.RequestException, ValueError):
                raise SourceError(str(first_error)) from first_error

    @staticmethod
    def _index(rows) -> dict[str, float]:
        out: dict[str, float] = {}
        for row in rows if isinstance(rows, list) else []:
            try:
                out[row["symbol"]] = float(row["price"])
            except (KeyError, TypeError, ValueError):
                continue
        return out


class StockSource:
    """US + Indian equities via Yahoo Finance's public chart endpoint.

    Indian tickers use Yahoo's exchange suffixes: ``.NS`` (NSE) or ``.BO`` (BSE),
    e.g. ``RELIANCE.NS``, ``TCS.BO``. US tickers are plain, e.g. ``AAPL``.

    Yahoo's anonymous quote-batch endpoint (``v7/finance/quote``) now requires an
    auth cookie/crumb, so this fetches one request per unique symbol via the
    still-open ``v8/finance/chart`` endpoint. A bad/delisted ticker 404s on its
    own request and is simply skipped -- it never blanks the other symbols.
    """

    name = "stock"
    URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    def get_prices(self, alerts) -> dict[str, float]:
        alerts = [a for a in alerts if a.symbol.strip()]
        if not alerts:
            return {}
        by_symbol: dict[str, float] = {}
        errors = 0
        for symbol in sorted({a.symbol.strip().upper() for a in alerts}):
            price = self._fetch_one(symbol)
            if price is not None:
                by_symbol[symbol] = price
            else:
                errors += 1
        if errors and not by_symbol:
            raise SourceError(f"no price data for {errors} stock symbol(s)")
        return {
            a.id: by_symbol[a.symbol.strip().upper()]
            for a in alerts
            if a.symbol.strip().upper() in by_symbol
        }

    def probe(self, symbol: str) -> float | None:
        return self._fetch_one(symbol.strip().upper())

    def _fetch_one(self, symbol: str) -> float | None:
        try:
            resp = requests.get(
                self.URL.format(symbol=symbol), headers=_HEADERS, timeout=_TIMEOUT
            )
            if resp.status_code == 404:
                return None  # unknown/delisted ticker -- not a feed-wide failure
            resp.raise_for_status()
            meta = resp.json()["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            return float(price) if price is not None else None
        except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
            return None


def probe_price(alert) -> float | None:
    """Best-effort current price for an Alert-like object (blocking)."""
    try:
        if alert.source == "coingecko":
            return CoinGeckoSource().probe(alert.coin_id, alert.vs_currency)
        if alert.source == "stock":
            return StockSource().probe(alert.symbol)
        return BinanceSource(alert.stream_market()).probe(alert.symbol)
    except Exception:  # noqa: BLE001
        return None


if __name__ == "__main__":  # python -m crypto_price_alert.sources
    logging.basicConfig(level=logging.INFO)
    from .models import Alert

    cg = Alert(threshold=0, source="coingecko", coin_id="bitcoin", vs_currency="usd")
    sp = Alert(threshold=0, source="binance", market="spot", symbol="BTCUSDT")
    fu = Alert(threshold=0, source="binance", market="futures", symbol="BTCUSDT")
    us = Alert(threshold=0, source="stock", market="US", symbol="AAPL")
    inr = Alert(threshold=0, source="stock", market="IN", symbol="RELIANCE.NS")
    print("CoinGecko    :", CoinGeckoSource().get_prices([cg]))
    print("Binance spot :", BinanceSource("spot").get_prices([sp]))
    print("Binance fut  :", BinanceSource("futures").get_prices([fu]))
    print("Stock US     :", StockSource().get_prices([us]))
    print("Stock IN     :", StockSource().get_prices([inr]))
