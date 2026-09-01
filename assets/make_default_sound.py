"""Optional: pre-bake a bundled default_alert.wav next to this script.

The app generates the same chime on demand into %APPDATA%\\CryptoPriceAlert
if this file is missing, so running this is purely optional.

    python assets/make_default_sound.py
"""

from pathlib import Path

from crypto_price_alert.resources import _generate_beep  # noqa: PLC2701

if __name__ == "__main__":
    out = Path(__file__).with_name("default_alert.wav")
    _generate_beep(out)
    print("wrote", out if out.exists() else "(failed)")
