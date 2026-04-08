"""Globale Tastenkuerzel mit pynput — ein einzelner Listener fuer alles."""

import logging
from pynput import keyboard
from PyObjCTools import AppHelper

log = logging.getLogger("AT")


class HotkeyManager:
    """F17 = OCR, F18 = Toggle-Aufnahme, F19 = Push-to-Talk.

    Nutzt einen einzelnen keyboard.Listener (nicht GlobalHotKeys),
    weil zwei separate pynput-Listener auf macOS/Darwin crashen.
    """

    def __init__(self, on_mic_toggle=None, on_mic_ptt_start=None,
                 on_mic_ptt_stop=None, on_ocr_trigger=None):
        self._on_mic_toggle = on_mic_toggle
        self._on_mic_ptt_start = on_mic_ptt_start
        self._on_mic_ptt_stop = on_mic_ptt_stop
        self._on_ocr_trigger = on_ocr_trigger
        self._listener = None
        self._ptt_active = False

    def start(self):
        """Einzelnen Listener starten fuer alle Hotkeys."""
        self._listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._listener.daemon = True
        self._listener.start()
        log.info("Hotkeys: F17=OCR, F18=Toggle, F19=PTT")

    def stop(self):
        """Listener stoppen."""
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_key_press(self, key):
        try:
            if key == keyboard.Key.f19:
                if not self._ptt_active and self._on_mic_ptt_start:
                    self._ptt_active = True
                    self._dispatch(self._on_mic_ptt_start)
            elif key == keyboard.Key.f18:
                if self._on_mic_toggle:
                    self._dispatch(self._on_mic_toggle)
            elif key == keyboard.Key.f17:
                if self._on_ocr_trigger:
                    self._dispatch(self._on_ocr_trigger)
        except Exception as e:
            log.exception("Hotkey press Fehler: %s", e)

    def _on_key_release(self, key):
        try:
            if key == keyboard.Key.f19:
                if self._ptt_active and self._on_mic_ptt_stop:
                    self._ptt_active = False
                    self._dispatch(self._on_mic_ptt_stop)
        except Exception as e:
            log.exception("Hotkey release Fehler: %s", e)

    def _dispatch(self, callback):
        """Callback auf den Main-Thread dispatchen."""
        try:
            AppHelper.callAfter(callback)
        except Exception as e:
            log.exception("Hotkey-Dispatch Fehler: %s", e)
