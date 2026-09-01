"""Persistent configuration stored as JSON in %APPDATA%\\CryptoPriceAlert."""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .models import Alert

log = logging.getLogger(__name__)

APP_DIR_NAME = "CryptoPriceAlert"
DEFAULT_INTERVAL = 60
MIN_INTERVAL = 15
MAX_INTERVAL = 3600

_save_lock = threading.Lock()


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = Path(base) / APP_DIR_NAME
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as e:  # pragma: no cover - unusual
        log.warning("Could not create %s: %s", d, e)
    return d


def config_path() -> Path:
    return app_data_dir() / "config.json"


def _clamp(value, lo, hi, default):
    try:
        return min(hi, max(lo, type(default)(value)))
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    alerts: list[Alert] = field(default_factory=list)
    window: dict = field(default_factory=lambda: {"x": 140, "y": 140, "w": 330, "h": 420})
    poll_interval_seconds: int = DEFAULT_INTERVAL
    global_sound_path: str = ""
    default_source: str = "binance"
    always_on_top: bool = False
    opacity: float = 0.97
    autostart: bool = False
    polling_paused: bool = False
    theme: str = "light"  # "light" | "dark" | "system"

    # ----- serialization ---------------------------------------------
    def to_dict(self) -> dict:
        return {
            "alerts": [a.to_dict() for a in self.alerts],
            "window": self.window,
            "poll_interval_seconds": self.poll_interval_seconds,
            "global_sound_path": self.global_sound_path,
            "default_source": self.default_source,
            "always_on_top": self.always_on_top,
            "opacity": self.opacity,
            "autostart": self.autostart,
            "polling_paused": self.polling_paused,
            "theme": self.theme,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        c = cls()
        d = d or {}
        c.alerts = [Alert.from_dict(x) for x in d.get("alerts", []) if isinstance(x, dict)]
        w = d.get("window")
        if isinstance(w, dict):
            for k in ("x", "y", "w", "h"):
                if k in w:
                    try:
                        c.window[k] = int(w[k])
                    except (TypeError, ValueError):
                        pass
        c.poll_interval_seconds = _clamp(
            d.get("poll_interval_seconds", DEFAULT_INTERVAL), MIN_INTERVAL, MAX_INTERVAL, DEFAULT_INTERVAL
        )
        c.global_sound_path = str(d.get("global_sound_path", "") or "")
        c.default_source = d.get("default_source", "binance")
        if c.default_source not in ("coingecko", "binance"):
            c.default_source = "binance"
        c.always_on_top = bool(d.get("always_on_top", False))
        c.opacity = _clamp(d.get("opacity", 0.97), 0.5, 1.0, 0.97)
        c.autostart = bool(d.get("autostart", False))
        c.polling_paused = bool(d.get("polling_paused", False))
        c.theme = d.get("theme", "light")
        if c.theme not in ("dark", "light", "system"):
            c.theme = "light"
        return c

    # ----- disk ------------------------------------------------------
    def save(self) -> None:
        path = config_path()
        tmp = path.with_name(f"config.{os.getpid()}.{threading.get_ident()}.tmp")
        with _save_lock:
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.to_dict(), f, indent=2)
                os.replace(tmp, path)
            except OSError as e:
                log.warning("Failed to save config: %s", e)
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass

    @classmethod
    def load(cls) -> "Config":
        path = config_path()
        if not path.exists():
            return cls()
        try:
            # utf-8-sig tolerates a BOM (e.g. if edited in Notepad)
            with open(path, "r", encoding="utf-8-sig") as f:
                return cls.from_dict(json.load(f))
        except (OSError, ValueError) as e:
            log.warning("Config unreadable (%s); starting fresh. Backup -> config.json.bak", e)
            try:
                os.replace(path, path.with_name(path.name + ".bak"))
            except OSError:
                pass
            return cls()
