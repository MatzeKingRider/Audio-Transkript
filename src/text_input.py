"""Text ins aktive Eingabefeld einfuegen via Clipboard + Cmd+V."""

import logging
import time
from AppKit import NSPasteboard, NSPasteboardTypeString, NSWorkspace
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventSetFlags,
    CGEventPost,
    kCGEventFlagMaskCommand,
    kCGHIDEventTap,
)

log = logging.getLogger("AT")


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
    """Text einfuegen: Clipboard sichern, Text setzen, Cmd+V, Clipboard wiederherstellen."""
    from ApplicationServices import AXIsProcessTrusted
    if not AXIsProcessTrusted():
        log.warning("type_text: Keine Accessibility-Berechtigung")
        return

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

        # Cmd+V simulieren (V = Keycode 9)
        key_down = CGEventCreateKeyboardEvent(None, 9, True)
        key_up = CGEventCreateKeyboardEvent(None, 9, False)
        if key_down is None:
            log.error("type_text: CGEvent=None, keine Berechtigung")
            return
        CGEventSetFlags(key_down, kCGEventFlagMaskCommand)
        CGEventSetFlags(key_up, kCGEventFlagMaskCommand)
        CGEventPost(kCGHIDEventTap, key_down)
        CGEventPost(kCGHIDEventTap, key_up)
        time.sleep(0.1)
    finally:
        # Clipboard immer wiederherstellen
        if old_data:
            try:
                pb.clearContents()
                for t, data in old_data.items():
                    pb.setData_forType_(data, t)
            except Exception:
                pass
