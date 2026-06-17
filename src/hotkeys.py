"""Globale Tastenkuerzel via CGEventTap auf dem Main-Thread.

Frueher lief das ueber pynput. Dessen keyboard.Listener arbeitet aber in einem
Hintergrund-Thread und uebersetzt dort jeden Tastendruck in ein Zeichen — dazu
fragt er via ctypes die Tastatur-Eingabequelle (Text Input Source Manager) ab.
Neuere macOS-Versionen erzwingen per dispatch_assert_queue(main), dass diese
Input-Source-Abfragen NUR auf dem Main-Thread passieren. pynput verletzt das ->
EXC_BREAKPOINT/SIGTRAP -> harter Absturz (siehe Crash-Reports Juni 2026).

Loesung: gleiches Muster wie F19EventTap (src/f19_tap.py) — ein CGEventTap, der
auf dem Main-Run-Loop liegt und NUR Keycodes auswertet (keine Zeichen-
Uebersetzung -> keine Input-Source-Abfrage -> kein Trap).
"""

import logging

from PyObjCTools import AppHelper
from Quartz import (
    CGEventTapCreate,
    CGEventTapEnable,
    CGEventTapIsEnabled,
    CGEventGetIntegerValueField,
    CGEventGetFlags,
    CFMachPortCreateRunLoopSource,
    CFMachPortInvalidate,
    CFRunLoopAddSource,
    CFRunLoopRemoveSource,
    CFRunLoopGetCurrent,
    kCGSessionEventTap,
    kCGHeadInsertEventTap,
    kCGEventTapOptionDefault,
    kCGEventKeyDown,
    kCGEventKeyUp,
    kCGEventTapDisabledByTimeout,
    kCGEventTapDisabledByUserInput,
    kCGKeyboardEventKeycode,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskShift,
    kCFRunLoopCommonModes,
)

log = logging.getLogger("AT")

# macOS Virtual Keycodes
F17_KEYCODE = 64
F18_KEYCODE = 79
O_KEYCODE = 31


class HotkeyManager:
    """F17 = OCR, F18 = Toggle-Aufnahme, Cmd+Shift+O = OCR.

    (F19 = PTT laeuft ueber F19EventTap, nicht hier.)

    Realisiert ueber einen CGEventTap auf dem Main-Thread. Die oeffentliche
    Schnittstelle (start/stop/is_listener_alive) bleibt identisch zur frueheren
    pynput-Variante, damit Watchdog und Recovery in app.py unveraendert bleiben.

    Events werden NICHT konsumiert (return event) — F17/F18/Cmd+Shift+O erreichen
    weiterhin die aktive App, wie es mit pynput auch der Fall war.
    """

    def __init__(self, on_mic_toggle=None, on_ocr_trigger=None):
        self._on_mic_toggle = on_mic_toggle
        self._on_ocr_trigger = on_ocr_trigger
        self._tap = None
        self._source = None
        self._pressed = set()  # gedrueckte Hotkey-Keycodes -> Auto-Repeat filtern

    def start(self):
        """Tap erzeugen, in den Main-Run-Loop einhaengen, aktivieren.
        Gibt True zurueck wenn der Tap lebt, sonst False."""
        if self._tap is not None:
            return True
        mask = (1 << kCGEventKeyDown) | (1 << kCGEventKeyUp)
        self._tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            mask,
            self._callback,
            None,
        )
        if self._tap is None:
            log.error("Hotkey-EventTap konnte nicht erstellt werden "
                      "(Accessibility-Berechtigung fehlt?)")
            return False
        self._source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
        CFRunLoopAddSource(
            CFRunLoopGetCurrent(), self._source, kCFRunLoopCommonModes)
        CGEventTapEnable(self._tap, True)
        log.info("Hotkeys aktiv (EventTap): F17=OCR, F18=Toggle, Cmd+Shift+O=OCR")
        return True

    def stop(self):
        """Tap deaktivieren, aus dem Run-Loop entfernen, Mach-Port invalidieren."""
        if self._tap is not None:
            try:
                CGEventTapEnable(self._tap, False)
            except Exception:
                pass
        if self._source is not None:
            try:
                CFRunLoopRemoveSource(
                    CFRunLoopGetCurrent(), self._source, kCFRunLoopCommonModes)
            except Exception:
                pass
        # WICHTIG: Mach-Port invalidieren, sonst leakt der Tap im Kernel.
        # macOS limitiert die Anzahl gleichzeitiger Taps pro Prozess — ohne
        # Invalidate kapituliert das System nach ein paar Recoveries
        # (gleicher Bug wie in f19_tap.py gefixt).
        if self._tap is not None:
            try:
                CFMachPortInvalidate(self._tap)
            except Exception:
                pass
        self._tap = None
        self._source = None
        self._pressed = set()

    def is_listener_alive(self):
        """True nur wenn der Tap existiert UND noch enabled ist. macOS kann den
        Tap nach KVM-Switch / Wake intern deaktivieren, ohne dass wir das Handle
        verlieren — daher zusaetzlich CGEventTapIsEnabled pruefen.
        (Methodenname bleibt 'is_listener_alive' fuer den Watchdog in app.py.)"""
        if self._tap is None:
            return False
        try:
            return bool(CGEventTapIsEnabled(self._tap))
        except Exception:
            return False

    def _callback(self, proxy, type_, event, refcon):
        # macOS deaktiviert den Tap bei Timeout/UserInput-Bursts -> reaktivieren
        if type_ in (kCGEventTapDisabledByTimeout,
                     kCGEventTapDisabledByUserInput):
            log.warning("Hotkey-EventTap disabled (type=%s) -> reaktiviere", type_)
            try:
                CGEventTapEnable(self._tap, True)
            except Exception:
                log.exception("Hotkey-EventTap konnte nicht reaktiviert werden")
            return event
        try:
            keycode = CGEventGetIntegerValueField(
                event, kCGKeyboardEventKeycode)

            if type_ == kCGEventKeyUp:
                self._pressed.discard(keycode)
                return event

            if type_ != kCGEventKeyDown:
                return event

            # KeyDown: nur auf der Down-Flanke feuern (Auto-Repeat filtern)
            if keycode == F18_KEYCODE:
                if keycode not in self._pressed:
                    self._pressed.add(keycode)
                    self._fire(self._on_mic_toggle)
            elif keycode == F17_KEYCODE:
                if keycode not in self._pressed:
                    self._pressed.add(keycode)
                    self._fire(self._on_ocr_trigger)
            elif keycode == O_KEYCODE and self._is_cmd_shift(event):
                if keycode not in self._pressed:
                    self._pressed.add(keycode)
                    self._fire(self._on_ocr_trigger)

            return event  # nie konsumieren -> Verhaltens-Paritaet mit pynput
        except Exception:
            log.exception("Hotkey-EventTap callback Fehler")
            return event

    @staticmethod
    def _is_cmd_shift(event):
        try:
            flags = CGEventGetFlags(event)
        except Exception:
            return False
        return bool(flags & kCGEventFlagMaskCommand) and \
            bool(flags & kCGEventFlagMaskShift)

    def _fire(self, callback):
        """Callback auf den Main-Thread dispatchen."""
        if not callback:
            return
        try:
            AppHelper.callAfter(callback)
        except Exception as e:
            log.exception("Hotkey-Dispatch Fehler: %s", e)
