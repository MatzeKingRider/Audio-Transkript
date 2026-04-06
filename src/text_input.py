"""Text ins aktive Eingabefeld einfügen via Clipboard + Cmd+V."""

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
    """Gibt die aktuell aktive App zurück."""
    return NSWorkspace.sharedWorkspace().frontmostApplication()


def activate_app(app):
    """Aktiviert die gegebene App."""
    if app:
        app.activateWithOptions_(1 << 1)  # NSApplicationActivateIgnoringOtherApps


def type_text(text):
    """Text ins aktive Feld einfügen: Clipboard sichern → Text setzen → Cmd+V → Clipboard wiederherstellen."""
    from ApplicationServices import AXIsProcessTrusted
    trusted = AXIsProcessTrusted()
    log.info("type_text: AXIsProcessTrusted=%s, text_len=%d", trusted, len(text))

    if not trusted:
        log.warning("KEINE Accessibility-Berechtigung! Cmd+V wird nicht funktionieren.")

    pb = NSPasteboard.generalPasteboard()

    # Alten Clipboard-Inhalt sichern
    old_types = pb.types()
    old_data = {}
    if old_types:
        for t in old_types:
            data = pb.dataForType_(t)
            if data:
                old_data[t] = data

    # Text auf Clipboard setzen
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)
    log.info("type_text: Clipboard gesetzt")

    time.sleep(0.05)

    # Cmd+V simulieren (V = Keycode 9)
    key_down = CGEventCreateKeyboardEvent(None, 9, True)
    key_up = CGEventCreateKeyboardEvent(None, 9, False)
    if key_down is None:
        log.error("type_text: CGEventCreateKeyboardEvent gab None zurueck! Keine Berechtigung.")
        return
    CGEventSetFlags(key_down, kCGEventFlagMaskCommand)
    CGEventSetFlags(key_up, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, key_down)
    CGEventPost(kCGHIDEventTap, key_up)
    log.info("type_text: Cmd+V gesendet")

    time.sleep(0.1)

    # Clipboard wiederherstellen
    if old_data:
        pb.clearContents()
        for t, data in old_data.items():
            pb.setData_forType_(data, t)
