"""Globale Tastenkürzel mit pynput."""

import threading
from pynput import keyboard
from AppKit import NSObject, NSApplication
from PyObjCTools import AppHelper
from src.config import HOTKEY_MIC, HOTKEY_OCR


class HotkeyManager:
    """Registriert globale Hotkeys und dispatcht Callbacks auf den Main-Thread."""

    def __init__(self, on_mic_toggle=None, on_ocr_trigger=None):
        self._on_mic_toggle = on_mic_toggle
        self._on_ocr_trigger = on_ocr_trigger
        self._listener = None

    def start(self):
        """Hotkey-Listener im Hintergrund starten."""
        hotkeys = {}
        if self._on_mic_toggle:
            hotkeys[HOTKEY_MIC] = lambda: self._dispatch(self._on_mic_toggle)
        if self._on_ocr_trigger:
            hotkeys[HOTKEY_OCR] = lambda: self._dispatch(self._on_ocr_trigger)

        self._listener = keyboard.GlobalHotKeys(hotkeys)
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        """Listener stoppen."""
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _dispatch(self, callback):
        """Callback auf den Main-Thread dispatchen (AppKit-Anforderung)."""
        AppHelper.callAfter(callback)
