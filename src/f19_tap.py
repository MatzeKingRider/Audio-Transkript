"""F19-EventTap — fängt F19 auf System-Ebene ab und konsumiert es,
damit macOS keinen 'ungültige Taste'-Warnton (NSBeep) ausgibt.

Pynput's Accessibility-Listener konsumiert das Event nicht; F19 hat in macOS
keine Default-Aktion -> Beep. CGEventTap auf kCGSessionEventTap fängt das
Event vor allen Apps ab und gibt None zurück -> Event verschwindet.
"""

import logging

from PyObjCTools import AppHelper
from Quartz import (
    CGEventTapCreate,
    CGEventTapEnable,
    CGEventTapIsEnabled,
    CGEventGetIntegerValueField,
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
    kCFRunLoopCommonModes,
)

log = logging.getLogger("AT")

F19_KEYCODE = 80


class F19EventTap:
    """Konsumiert F19-KeyDown/KeyUp vor macOS und ruft PTT-Callbacks
    im Main-Thread auf."""

    def __init__(self, on_press=None, on_release=None):
        self._on_press = on_press
        self._on_release = on_release
        self._tap = None
        self._source = None
        self._is_pressed = False  # filtert macOS-Auto-Repeat

    def start(self):
        """Tap erzeugen, in RunLoop einhaengen, aktivieren.
        Gibt True zurueck wenn Tap lebt, sonst False."""
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
            log.error("F19-EventTap konnte nicht erstellt werden "
                      "(Accessibility-Berechtigung fehlt?)")
            return False
        self._source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
        CFRunLoopAddSource(
            CFRunLoopGetCurrent(), self._source, kCFRunLoopCommonModes)
        CGEventTapEnable(self._tap, True)
        log.info("F19-EventTap aktiv (Keycode %d)", F19_KEYCODE)
        return True

    def stop(self):
        """Tap deaktivieren und aus RunLoop entfernen."""
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
        # macOS limitiert die Anzahl gleichzeitiger Taps pro Prozess —
        # ohne Invalidate kapituliert das System nach ein paar Recoveries.
        if self._tap is not None:
            try:
                CFMachPortInvalidate(self._tap)
            except Exception:
                pass
        self._tap = None
        self._source = None
        self._is_pressed = False

    def is_alive(self):
        """True nur wenn der Tap existiert UND noch enabled ist. macOS
        kann den Tap nach KVM-Switch / Wake intern deaktivieren, ohne dass
        wir das Python-Handle verlieren — daher zusaetzlich CGEventTapIsEnabled
        pruefen."""
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
            log.warning("F19-EventTap disabled (type=%s) -> reaktiviere", type_)
            try:
                CGEventTapEnable(self._tap, True)
            except Exception:
                log.exception("F19-EventTap konnte nicht reaktiviert werden")
            return event
        try:
            keycode = CGEventGetIntegerValueField(
                event, kCGKeyboardEventKeycode)
            if keycode != F19_KEYCODE:
                return event  # andere Tasten unveraendert weiterleiten
            if type_ == kCGEventKeyDown:
                if not self._is_pressed:
                    self._is_pressed = True
                    if self._on_press:
                        AppHelper.callAfter(self._on_press)
            elif type_ == kCGEventKeyUp:
                if self._is_pressed:
                    self._is_pressed = False
                    if self._on_release:
                        AppHelper.callAfter(self._on_release)
            return None  # F19 konsumiert -> kein Beep
        except Exception:
            log.exception("F19-EventTap callback Fehler")
            return event
