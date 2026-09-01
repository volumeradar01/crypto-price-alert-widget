"""Alert-sound playback. WAV via QSoundEffect (low latency), other formats
(MP3, OGG, ...) via QMediaPlayer. Falls back to a generated default beep."""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QSoundEffect

from .resources import default_sound_path

log = logging.getLogger(__name__)

try:
    _EFFECT_INFINITE = int(QSoundEffect.Infinite)
except (AttributeError, TypeError, ValueError):
    _EFFECT_INFINITE = -2
try:
    _PLAYER_INFINITE = int(getattr(QMediaPlayer, "Loops", QMediaPlayer).Infinite)
except (AttributeError, TypeError, ValueError):
    _PLAYER_INFINITE = -1


class SoundPlayer:
    def __init__(self):
        self._effect = QSoundEffect()
        self._effect.setVolume(0.9)
        self._audio = QAudioOutput()
        self._audio.setVolume(0.9)
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio)

    def play(self, path: str | None = None, loop: bool = False):
        target = path if path and os.path.isfile(path) else default_sound_path()
        if not target or not os.path.isfile(target):
            log.warning("No sound file available to play")
            return
        ext = os.path.splitext(target)[1].lower()
        try:
            self.stop()
            if ext == ".wav":
                self._effect.setSource(QUrl.fromLocalFile(target))
                self._effect.setLoopCount(_EFFECT_INFINITE if loop else 1)
                self._effect.play()
            else:
                try:
                    self._player.setLoops(_PLAYER_INFINITE if loop else 1)
                except (AttributeError, TypeError):
                    pass
                self._player.setSource(QUrl.fromLocalFile(target))
                self._player.setPosition(0)
                self._player.play()
        except Exception as e:  # noqa: BLE001 - playback must never crash the app
            log.warning("Sound playback failed for %s: %s", target, e)

    def stop(self):
        try:
            self._effect.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._player.stop()
        except Exception:  # noqa: BLE001
            pass

    def test(self, path: str | None = None):
        self.play(path, loop=False)


class Alarm:
    """A looping alert sound that keeps playing until explicitly stopped."""

    def __init__(self, player: SoundPlayer | None = None):
        self._player = player or SoundPlayer()
        self._active = False
        self._path: str | None = None

    def start(self, sound_path: str | None):
        if self._active and self._path == sound_path:
            return
        self._path = sound_path
        self._active = True
        self._player.play(sound_path, loop=True)

    def stop(self):
        if not self._active:
            return
        self._active = False
        self._path = None
        self._player.stop()

    @property
    def active(self) -> bool:
        return self._active


_singleton: SoundPlayer | None = None


def get_player() -> SoundPlayer:
    """Shared player so transient dialogs don't get their sound GC'd mid-play."""
    global _singleton
    if _singleton is None:
        _singleton = SoundPlayer()
    return _singleton
