"""Windows 'start on sign-in' via the per-user Run registry key.

Uses only the stdlib (`winreg`), so it works the same in a source checkout and in
the frozen/installed build (no COM, no pywin32). The value is visible and
toggleable in Task Manager -> Startup.
"""

from __future__ import annotations

import logging
import os
import sys
import winreg
from pathlib import Path

log = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "CryptoPriceAlert"
_LEGACY_LNK = "CryptoPriceAlert.lnk"


def _startup_dir() -> Path:
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _run_command() -> str:
    """The command Windows should run at sign-in (properly quoted)."""
    if getattr(sys, "frozen", False):  # installed / PyInstaller build
        return f'"{sys.executable}"'

    # dev checkout: a tiny .pyw shim so we don't depend on the working directory
    root = str(Path(__file__).resolve().parent.parent)
    try:
        from .config import app_data_dir

        shim = app_data_dir() / "autostart_launch.pyw"
        shim.write_text(
            "import sys\n"
            f"sys.path.insert(0, {root!r})\n"
            "from crypto_price_alert.__main__ import main\n"
            "raise SystemExit(main())\n",
            encoding="utf-8",
        )
        target = str(shim)
    except Exception:  # noqa: BLE001
        target = "-m crypto_price_alert"

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" "{target}"' if target.endswith(".pyw") else f'"{exe}" {target}'


def _open(access):
    return winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, access)


def _remove_legacy_shortcut() -> None:
    try:
        (_startup_dir() / _LEGACY_LNK).unlink(missing_ok=True)
    except OSError:
        pass


def is_enabled() -> bool:
    try:
        with _open(winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def target_ok() -> bool:
    """True if enabled and (for the frozen build) the exe it points at exists."""
    try:
        with _open(winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
    except OSError:
        return False
    if not value:
        return False
    if getattr(sys, "frozen", False):
        exe = value.strip().strip('"')
        return os.path.exists(exe)
    return True


def enable() -> bool:
    try:
        with _open(winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _run_command())
        _remove_legacy_shortcut()  # supersede any old Startup-folder .lnk
        return is_enabled()
    except OSError as e:
        log.error("Could not enable autostart (registry write failed): %s", e)
        return False


def disable() -> bool:
    _remove_legacy_shortcut()
    try:
        with _open(winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning("Could not remove autostart registry value: %s", e)
        return False
    return True


def sync(desired: bool) -> bool:
    return enable() if desired else disable()


# Back-compat for callers/tests that referenced the old shortcut path.
def shortcut_path() -> Path:
    return _startup_dir() / _LEGACY_LNK
