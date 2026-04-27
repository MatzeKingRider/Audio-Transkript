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
        self._pressed_keys = set()

    def start(self):
        """Einzelnen Listener starten fuer alle Hotkeys."""
        self._listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._listener.daemon = True
        self._listener.start()
        log.info("Hotkeys: F17=OCR, F18=Toggle, F19=PTT, Cmd+Shift+T/O/M, Ctrl+S=OCR, Ctrl+P=PTT")

    def stop(self):
        """Listener stoppen."""
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_key_press(self, key):
        try:
            self._pressed_keys.add(key)
            if key == keyboard.Key.f19 or self._is_ptt_combo(key) or self._is_ctrl_p(key):
                if not self._ptt_active and self._on_mic_ptt_start:
                    self._ptt_active = True
                    self._dispatch(self._on_mic_ptt_start)
            elif key == keyboard.Key.f18 or self._is_toggle_combo(key):
                if self._on_mic_toggle:
                    self._dispatch(self._on_mic_toggle)
            elif key == keyboard.Key.f17 or self._is_ocr_combo(key) or self._is_ctrl_s(key):
                if self._on_ocr_trigger:
                    self._dispatch(self._on_ocr_trigger)
        except Exception as e:
            log.exception("Hotkey press Fehler: %s", e)

    def _on_key_release(self, key):
        try:
            if key == keyboard.Key.f19 or self._is_ptt_combo_key(key) or self._is_ctrl_p_release(key):
                if self._ptt_active and self._on_mic_ptt_stop:
                    self._ptt_active = False
                    self._dispatch(self._on_mic_ptt_stop)
        except Exception as e:
            log.exception("Hotkey release Fehler: %s", e)
        finally:
            if key in self._pressed_keys:
                self._pressed_keys.remove(key)

    def _is_ctrl_pressed(self):
        return any(k in self._pressed_keys for k in (
            keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r))

    def _is_ctrl_p(self, key):
        return getattr(key, "char", None) == "p" and self._is_ctrl_pressed()

    def _is_ctrl_s(self, key):
        return getattr(key, "char", None) == "s" and self._is_ctrl_pressed()

    def _is_ctrl_p_release(self, key):
        return getattr(key, "char", None) == "p" or key in (
            keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)

    def _is_cmd_shift_pressed(self):
        has_cmd = any(k in self._pressed_keys for k in (
            keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r))
        has_shift = any(k in self._pressed_keys for k in (
            keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r))
        return has_cmd and has_shift

    def _has_char(self, char):
        return any(getattr(k, "char", None) == char for k in self._pressed_keys)

    def _is_ptt_combo(self, key):
        return getattr(key, "char", None) == "m" and self._is_cmd_shift_pressed()

    def _is_toggle_combo(self, key):
        return getattr(key, "char", None) == "t" and self._is_cmd_shift_pressed()

    def _is_ocr_combo(self, key):
        return getattr(key, "char", None) == "o" and self._is_cmd_shift_pressed()

    def _is_ptt_combo_key(self, key):
        return getattr(key, "char", None) == "m" or key in (
            keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r,
            keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r)

    def _dispatch(self, callback):
        """Callback auf den Main-Thread dispatchen."""
        try:
            AppHelper.callAfter(callback)
        except Exception as e:
            log.exception("Hotkey-Dispatch Fehler: %s", e)
