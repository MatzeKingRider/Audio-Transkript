"""Text ins aktive Eingabefeld einfuegen via Clipboard + Cmd+V."""

import logging
import threading
import time
import objc
from AppKit import NSPasteboard, NSPasteboardTypeString, NSWorkspace
from Foundation import NSObject, NSThread
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventSetFlags,
    CGEventPost,
    kCGEventFlagMaskCommand,
    kCGHIDEventTap,
)

log = logging.getLogger("AT")

# Serialisiert alle Einfuege-Vorgaenge. Beim Live-Einfuegen waehrend der
# Aufnahme starten mehrere Hintergrund-Threads gleichzeitig; ohne Lock
# ueberschreiben sie sich gegenseitig die Clipboard-Sicherung -> dann landet
# der falsche (alte) Inhalt im Ziel.
_paste_lock = threading.Lock()


def _post_cmd_v():
    """Cmd+V (Keycode 9) als Tastatur-Event erzeugen und zustellen.

    MUSS auf dem Main-Thread laufen: CGEventCreateKeyboardEvent/CGEventPost
    koennen intern die Tastatur-Eingabequelle (HIToolbox/TSM) abfragen, und
    macOS erzwingt das per dispatch_assert_queue(main). Aus einem Hintergrund-
    Thread -> SIGTRAP/Absturz (gleiche Bug-Klasse wie der fruehere pynput-Crash).
    """
    key_down = CGEventCreateKeyboardEvent(None, 9, True)
    key_up = CGEventCreateKeyboardEvent(None, 9, False)
    if key_down is None:
        log.error("type_text: CGEvent=None, keine Berechtigung")
        return
    CGEventSetFlags(key_down, kCGEventFlagMaskCommand)
    CGEventSetFlags(key_up, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, key_down)
    CGEventPost(kCGHIDEventTap, key_up)


class _MainThreadPaster(NSObject):
    """Winziger Helfer, um _post_cmd_v synchron auf den Main-Thread zu bringen."""

    def doPaste_(self, _):
        _post_cmd_v()


_paster = _MainThreadPaster.alloc().init()


def _paste_on_main_thread():
    """_post_cmd_v auf dem Main-Thread ausfuehren — synchron (waitUntilDone),
    damit die Reihenfolge (Clipboard setzen -> Paste -> Clipboard restore)
    erhalten bleibt."""
    if NSThread.isMainThread():
        _post_cmd_v()
    else:
        _paster.performSelectorOnMainThread_withObject_waitUntilDone_(
            objc.selector(_paster.doPaste_, signature=b"v@:@"), None, True)


def get_frontmost_app():
    """Gibt die aktuell aktive App zurueck."""
    return NSWorkspace.sharedWorkspace().frontmostApplication()


def activate_app(app):
    """Aktiviert die gegebene App. Sicher gegen stale/tote Referenzen."""
    if app:
        try:
            app.activateWithOptions_(1 << 1)
        except Exception:
            log.warning("activate_app fehlgeschlagen (App beendet?)")


def type_text(text):
    """Text einfuegen: Clipboard sichern, Text setzen, Cmd+V, Clipboard wiederherstellen.

    Serialisiert per _paste_lock, damit parallele Einfuegungen sich nicht die
    Clipboard-Sicherung zerstoeren.
    """
    if not text or not text.strip():
        return

    from ApplicationServices import AXIsProcessTrusted
    if not AXIsProcessTrusted():
        log.warning("type_text: Keine Accessibility-Berechtigung")
        return

    with _paste_lock:
        pb = NSPasteboard.generalPasteboard()

        # Clipboard sichern
        old_data = {}
        try:
            old_types = pb.types()
            if old_types:
                for t in old_types:
                    data = pb.dataForType_(t)
                    if data:
                        old_data[t] = data
        except Exception:
            pass

        try:
            # Text auf Clipboard setzen
            pb.clearContents()
            pb.setString_forType_(text, NSPasteboardTypeString)
            time.sleep(0.05)

            # Cmd+V simulieren (V = Keycode 9) — auf dem Main-Thread, sonst
            # riskiert die HIToolbox-Input-Source-Abfrage einen SIGTRAP-Absturz.
            _paste_on_main_thread()
            # Grosszuegig warten, BEVOR der alte Inhalt zurueckgeschrieben wird:
            # die Ziel-App liest das Clipboard erst, wenn sie den Cmd+V-Event
            # verarbeitet — passiert das nach dem Restore, wuerde der ALTE
            # Inhalt eingefuegt.
            time.sleep(0.3)
        finally:
            # Clipboard immer wiederherstellen
            if old_data:
                try:
                    pb.clearContents()
                    for t, data in old_data.items():
                        pb.setData_forType_(data, t)
                except Exception:
                    pass
