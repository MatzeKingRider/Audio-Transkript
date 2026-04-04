"""Einstiegspunkt — Menu Bar Icon + Floating Panel."""

import threading
import time as _time
import rumps
import objc
from AppKit import (
    NSApplication,
    NSObject,
    NSPanel,
    NSView,
    NSButton,
    NSTextField,
    NSTextView,
    NSScrollView,
    NSPasteboard,
    NSPasteboardTypeString,
    NSFont,
    NSMakeRect,
    NSFloatingWindowLevel,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskUtilityWindow,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSColor,
    NSScreen,
)
from PyObjCTools import AppHelper
from src.config import APP_NAME, ICON_PATH, PANEL_WIDTH, PANEL_HEIGHT, PANEL_TITLE
from src.recorder import Recorder
from src.transcriber import Transcriber
from src.ocr import capture_screenshot, ocr_image
from src.text_input import type_text, get_frontmost_app, activate_app
from src.hotkeys import HotkeyManager


def _on_main(fn):
    """Führt fn auf dem Main-Thread aus (sicher von Hintergrund-Threads)."""
    AppHelper.callAfter(fn)


class TranscriptPanel(NSObject):
    """Floating NSPanel mit Buttons, Textfeld und Status-Anzeige."""

    @objc.python_method
    def setup(self):
        self.on_mic_click = None
        self.on_ocr_click = None
        self.on_copy_click = None
        self.on_insert_click = None
        self.on_clear_click = None
        self.on_text_edited = None
        self._programmatic_text_change = False
        self._build_panel()
        return self

    @objc.python_method
    def _build_panel(self):
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskUtilityWindow
        )
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, PANEL_WIDTH, PANEL_HEIGHT),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self.panel.setTitle_(PANEL_TITLE)
        self.panel.setLevel_(NSFloatingWindowLevel)
        self.panel.setHidesOnDeactivate_(False)
        self.panel.setFloatingPanel_(True)

        screen = NSScreen.mainScreen().frame()
        x = (screen.size.width - PANEL_WIDTH) / 2
        y = (screen.size.height - PANEL_HEIGHT) / 2
        self.panel.setFrameOrigin_((x, y))

        content = self.panel.contentView()
        pad = 20
        inner_w = PANEL_WIDTH - 2 * pad

        # --- Zeile oben: Mikrofon + Screenshot Buttons (y=340) ---
        self.mic_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(pad, 340, inner_w // 2 - 5, 40)
        )
        self.mic_btn.setTitle_("Mikrofon")
        self.mic_btn.setBezelStyle_(NSBezelStyleRounded)
        self.mic_btn.setTarget_(self)
        self.mic_btn.setAction_("micClicked:")
        content.addSubview_(self.mic_btn)

        self.ocr_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(pad + inner_w // 2 + 5, 340, inner_w // 2 - 5, 40)
        )
        self.ocr_btn.setTitle_("Screenshot")
        self.ocr_btn.setBezelStyle_(NSBezelStyleRounded)
        self.ocr_btn.setTarget_(self)
        self.ocr_btn.setAction_("ocrClicked:")
        content.addSubview_(self.ocr_btn)

        # --- Editierbares Textfeld mit Scrollbar (y=100, h=230) ---
        scroll_frame = NSMakeRect(pad, 100, inner_w, 230)
        self.scroll_view = NSScrollView.alloc().initWithFrame_(scroll_frame)
        self.scroll_view.setHasVerticalScroller_(True)
        self.scroll_view.setBorderType_(1)  # NSBezelBorder

        text_frame = NSMakeRect(0, 0, inner_w - 2, 230)
        self.text_view = NSTextView.alloc().initWithFrame_(text_frame)
        self.text_view.setEditable_(True)
        self.text_view.setSelectable_(True)
        self.text_view.setRichText_(False)
        self.text_view.setFont_(NSFont.systemFontOfSize_(14))
        self.text_view.textContainer().setWidthTracksTextView_(True)
        self.text_view.setDelegate_(self)

        self.scroll_view.setDocumentView_(self.text_view)
        content.addSubview_(self.scroll_view)

        # --- Untere Buttons: Kopieren, Einfügen, Leeren (y=55) ---
        btn_w = (inner_w - 20) // 3
        self.copy_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(pad, 55, btn_w, 32)
        )
        self.copy_btn.setTitle_("Kopieren")
        self.copy_btn.setBezelStyle_(NSBezelStyleRounded)
        self.copy_btn.setTarget_(self)
        self.copy_btn.setAction_("copyClicked:")
        content.addSubview_(self.copy_btn)

        self.insert_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(pad + btn_w + 10, 55, btn_w, 32)
        )
        self.insert_btn.setTitle_("Einfügen")
        self.insert_btn.setBezelStyle_(NSBezelStyleRounded)
        self.insert_btn.setTarget_(self)
        self.insert_btn.setAction_("insertClicked:")
        content.addSubview_(self.insert_btn)

        self.clear_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(pad + 2 * (btn_w + 10), 55, btn_w, 32)
        )
        self.clear_btn.setTitle_("Leeren")
        self.clear_btn.setBezelStyle_(NSBezelStyleRounded)
        self.clear_btn.setTarget_(self)
        self.clear_btn.setAction_("clearClicked:")
        content.addSubview_(self.clear_btn)

        # --- Status-Label (y=15) ---
        self.status_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(pad, 15, inner_w, 30)
        )
        self.status_label.setStringValue_("Bereit")
        self.status_label.setEditable_(False)
        self.status_label.setBezeled_(False)
        self.status_label.setDrawsBackground_(False)
        self.status_label.setFont_(NSFont.systemFontOfSize_(13))
        self.status_label.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(self.status_label)

    @objc.python_method
    def set_status(self, text):
        self.status_label.setStringValue_(text)

    @objc.python_method
    def set_text(self, text):
        self._programmatic_text_change = True
        self.text_view.setString_(text)
        self._programmatic_text_change = False

    @objc.python_method
    def get_text(self):
        return str(self.text_view.string())

    @objc.python_method
    def append_text(self, text):
        self._programmatic_text_change = True
        current = self.get_text()
        if current and not current.endswith("\n"):
            text = "\n" + text
        self.text_view.setString_(current + text)
        # Scroll zum Ende
        length = self.text_view.string().length()
        self.text_view.scrollRangeToVisible_((length, 0))
        self._programmatic_text_change = False

    @objc.python_method
    def show(self):
        self.panel.makeKeyAndOrderFront_(None)

    @objc.python_method
    def hide(self):
        self.panel.orderOut_(None)

    @objc.python_method
    def toggle(self):
        if self.panel.isVisible():
            self.hide()
        else:
            self.show()

    @objc.python_method
    def is_visible(self):
        return self.panel.isVisible()

    def textDidChange_(self, notification):
        if not self._programmatic_text_change and self.on_text_edited:
            self.on_text_edited()

    @objc.IBAction
    def micClicked_(self, sender):
        if self.on_mic_click:
            self.on_mic_click()

    @objc.IBAction
    def ocrClicked_(self, sender):
        if self.on_ocr_click:
            self.on_ocr_click()

    @objc.IBAction
    def copyClicked_(self, sender):
        if self.on_copy_click:
            self.on_copy_click()

    @objc.IBAction
    def insertClicked_(self, sender):
        if self.on_insert_click:
            self.on_insert_click()

    @objc.IBAction
    def clearClicked_(self, sender):
        if self.on_clear_click:
            self.on_clear_click()


class AudioTranskriptApp(rumps.App):
    """Menu-Bar-App mit Floating Panel."""

    def __init__(self):
        super().__init__(APP_NAME, icon=ICON_PATH, template=True)
        self.panel = TranscriptPanel.alloc().init().setup()
        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self._previous_app = None
        self._text_was_edited = False
        self.panel.on_mic_click = self._toggle_recording
        self.panel.on_ocr_click = self._do_screenshot_ocr
        self.panel.on_copy_click = self._copy_text
        self.panel.on_insert_click = self._insert_panel_text
        self.panel.on_clear_click = self._clear_text
        self.panel.on_text_edited = self._on_text_edited
        self._recording_start = None
        self._recording_timer = None
        self.menu = [
            rumps.MenuItem("Öffnen/Schließen", callback=self._toggle_panel),
            None,
            rumps.MenuItem("Beenden", callback=self._quit),
        ]

        # Globale Hotkeys starten
        self.hotkeys = HotkeyManager(
            on_mic_toggle=self._toggle_recording,
            on_ocr_trigger=self._do_screenshot_ocr,
        )
        self.hotkeys.start()

        # Whisper-Modell im Hintergrund laden
        self.panel.mic_btn.setEnabled_(False)
        self.transcriber.load_model(
            on_progress=lambda msg: _on_main(lambda: self.panel.set_status(msg)),
            on_done=lambda: _on_main(self._on_model_loaded),
        )

    def _toggle_panel(self, _):
        self.panel.toggle()

    def _quit(self, _):
        self.hotkeys.stop()
        rumps.quit_application()

    @rumps.clicked(APP_NAME)
    def on_icon_click(self, _):
        self.panel.toggle()

    def _on_text_edited(self):
        self._text_was_edited = True

    def _copy_text(self):
        text = self.panel.get_text()
        if not text.strip():
            self.panel.set_status("Kein Text zum Kopieren")
            return
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSPasteboardTypeString)
        self.panel.set_status("In Zwischenablage kopiert")

    def _insert_panel_text(self):
        text = self.panel.get_text()
        if not text.strip():
            self.panel.set_status("Kein Text zum Einfügen")
            return
        if self._previous_app:
            activate_app(self._previous_app)
            _time.sleep(0.15)
        type_text(text)
        self.panel.set_status("Text eingefügt")

    def _clear_text(self):
        self.panel.set_text("")
        self._text_was_edited = False
        self.panel.set_status("Bereit")

    def _toggle_recording(self):
        self._previous_app = get_frontmost_app()
        if self.recorder.is_recording:
            if self._recording_timer:
                self._recording_timer.stop()
                self._recording_timer = None
            self.panel.set_status("Verarbeite...")
            self.panel.mic_btn.setTitle_("Mikrofon")
            audio = self.recorder.stop()
            if len(audio) > 0:
                duration = len(audio) / 16000
                self.panel.set_status(f"Aufnahme: {duration:.1f}s — Transkribiere...")
                self._process_audio(audio)
            else:
                self.panel.set_status("Keine Aufnahme erkannt")
        else:
            if not self._text_was_edited:
                self.panel.set_text("")
            self.recorder.start()
            self._recording_start = _time.time()
            self.panel.mic_btn.setTitle_("Stopp")
            self.panel.set_status("Aufnahme läuft...")
            self._recording_timer = rumps.Timer(self._update_recording_time, 1)
            self._recording_timer.start()

    def _update_recording_time(self, _):
        if self._recording_start and self.recorder.is_recording:
            elapsed = _time.time() - self._recording_start
            mins, secs = divmod(int(elapsed), 60)
            self.panel.set_status(f"Aufnahme läuft... {mins:02d}:{secs:02d}")

    def _on_model_loaded(self):
        self.panel.mic_btn.setEnabled_(True)
        self.panel.set_status("Bereit")

    def _process_audio(self, audio):
        """Audio im Hintergrund transkribieren."""
        def _run():
            text = self.transcriber.transcribe(audio)
            _on_main(lambda: self._on_transcription_done(text))

        threading.Thread(target=_run, daemon=True).start()

    def _on_transcription_done(self, text):
        if text:
            if self._previous_app:
                self.panel.set_text(text)
                self._text_was_edited = False
                self.panel.set_status("Text eingefügt")
                activate_app(self._previous_app)
                _time.sleep(0.15)
                type_text(text)
            else:
                self.panel.append_text(text)
                self._text_was_edited = False
                self.panel.set_status("Text im Panel angehängt")
        else:
            self.panel.set_status("Kein Text erkannt")

    def _do_screenshot_ocr(self):
        """Screenshot aufnehmen und OCR durchführen."""
        self._previous_app = get_frontmost_app()
        was_visible = self.panel.is_visible()
        if was_visible:
            self.panel.hide()

        def _run():
            _time.sleep(0.3)
            image = capture_screenshot()

            if was_visible:
                _on_main(lambda: self.panel.show())

            if image is None:
                _on_main(lambda: self.panel.set_status("Screenshot abgebrochen"))
                return

            _on_main(lambda: self.panel.set_status("OCR läuft..."))
            text = ocr_image(image)
            _on_main(lambda: self._on_ocr_done(text))

        threading.Thread(target=_run, daemon=True).start()

    def _on_ocr_done(self, text):
        if text:
            if self._previous_app:
                self.panel.set_text(text)
                self._text_was_edited = False
                self.panel.set_status("Text eingefügt")
                activate_app(self._previous_app)
                _time.sleep(0.15)
                type_text(text)
            else:
                self.panel.append_text(text)
                self._text_was_edited = False
                self.panel.set_status("Text im Panel angehängt")
        else:
            self.panel.set_status("Kein Text erkannt")


def _check_accessibility():
    """Prüft Accessibility-Berechtigung und zeigt Hinweis."""
    from ApplicationServices import AXIsProcessTrustedWithOptions
    from CoreFoundation import kCFBooleanTrue

    options = {
        "AXTrustedCheckOptionPrompt": kCFBooleanTrue
    }
    trusted = AXIsProcessTrustedWithOptions(options)
    if not trusted:
        rumps.alert(
            title="Berechtigung erforderlich",
            message=(
                "Audio Transkript benötigt Zugriff auf Bedienungshilfen "
                "(Accessibility) für Hotkeys und Text-Einfügung.\n\n"
                "Bitte erteile die Berechtigung unter:\n"
                "Systemeinstellungen → Datenschutz & Sicherheit → Bedienungshilfen"
            ),
        )
    return trusted


def main():
    _check_accessibility()
    app = AudioTranskriptApp()
    app.run()


if __name__ == "__main__":
    main()
