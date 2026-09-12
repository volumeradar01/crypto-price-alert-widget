"""Validated symbol / coin lists for the searchable pickers, cached on disk."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

import requests

from .config import app_data_dir

log = logging.getLogger(__name__)

_TTL = 24 * 3600
_TIMEOUT = 12
_mem: dict[str, list] = {}
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(name: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(name, threading.Lock())


def _cache_file(name: str) -> Path:
    return app_data_dir() / f"symcache_{name}.json"


def _read_cache(name: str):
    try:
        d = json.loads(_cache_file(name).read_text("utf-8"))
        if time.time() - float(d.get("ts", 0)) < _TTL and d.get("items"):
            return d["items"]
    except (OSError, ValueError, TypeError):
        pass
    return None


def _write_cache(name: str, items: list) -> None:
    try:
        _cache_file(name).write_text(
            json.dumps({"ts": time.time(), "items": items}), "utf-8"
        )
    except OSError as e:  # pragma: no cover
        log.warning("symbol cache write failed: %s", e)


def _fetch_binance(market: str) -> list[str]:
    url = (
        "https://fapi.binance.com/fapi/v1/exchangeInfo"
        if market == "futures"
        else "https://api.binance.com/api/v3/exchangeInfo"
    )
    r = requests.get(url, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    out = [
        s["symbol"]
        for s in data.get("symbols", [])
        if s.get("status") == "TRADING" and s.get("symbol")
    ]
    return sorted(set(out))


def _fetch_coingecko_coins() -> list[list[str]]:
    r = requests.get("https://api.coingecko.com/api/v3/coins/list", timeout=_TIMEOUT)
    r.raise_for_status()
    rows = r.json()
    out = [
        [x["id"], (x.get("symbol") or "").upper(), x.get("name") or x["id"]]
        for x in rows
        if x.get("id")
    ]
    out.sort(key=lambda t: t[2].lower())
    return out


_FETCHERS = {
    "binance_spot": lambda: _fetch_binance("spot"),
    "binance_futures": lambda: _fetch_binance("futures"),
    "coingecko_coins": _fetch_coingecko_coins,
}


def get(name: str, force: bool = False) -> list:
    """Blocking: return the cached list, refreshing from the network if stale.
    ``name`` is one of the keys in ``_FETCHERS``. Returns [] on total failure."""
    if not force and name in _mem:
        return _mem[name]
    with _lock_for(name):  # only serialises fetches of the *same* list
        if not force and name in _mem:
            return _mem[name]
        if not force:
            cached = _read_cache(name)
            if cached is not None:
                _mem[name] = cached
                return cached
        try:
            items = _FETCHERS[name]()
            _mem[name] = items
            _write_cache(name, items)
            return items
        except (requests.RequestException, ValueError, KeyError) as e:
            log.warning("symbol list '%s' fetch failed: %s", name, e)
            stale = _read_cache(name) or _mem.get(name) or []
            return stale


def get_async(name: str, callback) -> None:
    """Fetch on a daemon thread; call ``callback(name, list)`` when done."""
    def _run():
        callback(name, get(name))

    threading.Thread(target=_run, name=f"symbols:{name}", daemon=True).start()


def binance_key(market: str) -> str:
    return "binance_futures" if market == "futures" else "binance_spot"


def is_valid_binance(market: str, symbol: str) -> bool:
    items = _mem.get(binance_key(market))
    if not items:  # unknown / not loaded yet -> don't block the user
        return True
    return symbol.strip().upper() in items
