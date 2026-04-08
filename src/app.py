"""Einstiegspunkt — Menu Bar Icon + Floating Panel."""

import logging
import os
import threading
import time as _time
import rumps
import objc

log = logging.getLogger("AT")
log.setLevel(logging.INFO)
_log_path = os.path.join(os.environ.get("TMPDIR", "/tmp"), "audiotranskript.log")
_fh = logging.FileHandler(_log_path)
_fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
log.addHandler(_fh)
log.info("=== App gestartet ===")
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
    NSImage,
    NSMakeRect,
    NSMakeSize,
    NSBezierPath,
    NSFloatingWindowLevel,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskUtilityWindow,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSColor,
    NSScreen,
    NSWorkspace,
    NSWorkspaceDidActivateApplicationNotification,
    NSImageScaleProportionallyUpOrDown,
)
from PyObjCTools import AppHelper
from src.config import (
    APP_NAME, ICON_PATH, PANEL_WIDTH, PANEL_HEIGHT, PANEL_TITLE,
    HOTKEY_MIC_TOGGLE, HOTKEY_OCR, SAMPLE_RATE,
)
from src.recorder import Recorder
from src.transcriber import Transcriber
from src.ocr import capture_screenshot, ocr_image
from src.text_input import type_text, activate_app
from src.hotkeys import HotkeyManager


def _on_main(fn):
    """Fuehrt fn auf dem Main-Thread aus (sicher von Hintergrund-Threads)."""
    AppHelper.callAfter(fn)


# --- Icon-Zeichnung ---

def _make_circle_icon(size, bg_color, draw_fn):
    """Erzeugt ein rundes NSImage mit farbigem Hintergrund und Symbol."""
    img = NSImage.alloc().initWithSize_(NSMakeSize(size, size))
    img.lockFocus()
    bg_color.setFill()
    circle = NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(0, 0, size, size))
    circle.fill()
    NSColor.whiteColor().setFill()
    NSColor.whiteColor().setStroke()
    draw_fn(size)
    img.unlockFocus()
    return img


def _draw_mic(size):
    """Mikrofon-Symbol."""
    cx = size / 2
    kw, kh = size * 0.22, size * 0.32
    kapsel = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(cx - kw / 2, size * 0.42, kw, kh), kw / 2, kw / 2)
    kapsel.fill()
    bogen = NSBezierPath.bezierPath()
    bogen.setLineWidth_(size * 0.045)
    bw = size * 0.34
    bogen.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
        (cx, size * 0.46), bw / 2, 210, 330, True)
    bogen.stroke()
    stiel = NSBezierPath.bezierPath()
    stiel.setLineWidth_(size * 0.045)
    stiel.moveToPoint_((cx, size * 0.30))
    stiel.lineToPoint_((cx, size * 0.20))
    stiel.stroke()
    fuss = NSBezierPath.bezierPath()
    fuss.setLineWidth_(size * 0.045)
    fuss.moveToPoint_((cx - size * 0.10, size * 0.20))
    fuss.lineToPoint_((cx + size * 0.10, size * 0.20))
    fuss.stroke()


def _draw_camera(size):
    """Kamera-Symbol."""
    cx, cy = size / 2, size / 2
    bw, bh = size * 0.50, size * 0.34
    body = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(cx - bw / 2, cy - bh / 2 - size * 0.02, bw, bh),
        size * 0.04, size * 0.04)
    body.fill()
    top = NSBezierPath.bezierPath()
    top.moveToPoint_((cx - size * 0.08, cy + bh / 2 - size * 0.02))
    top.lineToPoint_((cx - size * 0.05, cy + bh / 2 + size * 0.06))
    top.lineToPoint_((cx + size * 0.05, cy + bh / 2 + size * 0.06))
    top.lineToPoint_((cx + size * 0.08, cy + bh / 2 - size * 0.02))
    top.closePath()
    top.fill()
    NSColor.whiteColor().setStroke()
    lens_r = size * 0.11
    lens = NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(cx - lens_r, cy - lens_r - size * 0.02,
                   lens_r * 2, lens_r * 2))
    NSColor.systemOrangeColor().setFill()
    lens.fill()
    NSColor.whiteColor().setStroke()
    lens.setLineWidth_(size * 0.03)
    lens.stroke()


def _draw_stop(size):
    """Stopp-Symbol."""
    cx, cy = size / 2, size / 2
    sq = size * 0.28
    stop_rect = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(cx - sq / 2, cy - sq / 2, sq, sq),
        size * 0.04, size * 0.04)
    stop_rect.fill()


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
            | NSWindowStyleMaskResizable
            | NSWindowStyleMaskUtilityWindow
        )
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, PANEL_WIDTH, PANEL_HEIGHT),
            style, NSBackingStoreBuffered, False)
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

        # --- Runde Buttons oben ---
        btn_size = 60
        gap = 40
        total = 2 * btn_size + gap
        x_mic = (PANEL_WIDTH - total) / 2
        x_ocr = x_mic + btn_size + gap
        btn_y = 330

        self.mic_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(x_mic, btn_y, btn_size, btn_size))
        self.mic_btn.setBordered_(False)
        self.mic_btn.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        self.mic_btn.setImage_(
            _make_circle_icon(btn_size, NSColor.systemBlueColor(), _draw_mic))
        self.mic_btn.setTarget_(self)
        self.mic_btn.setAction_("micClicked:")
        content.addSubview_(self.mic_btn)

        mic_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(x_mic - 20, btn_y - 20, btn_size + 40, 16))
        mic_label.setStringValue_("Mikrofon")
        mic_label.setEditable_(False)
        mic_label.setBezeled_(False)
        mic_label.setDrawsBackground_(False)
        mic_label.setAlignment_(1)
        mic_label.setFont_(NSFont.systemFontOfSize_(11))
        mic_label.setTextColor_(NSColor.labelColor())
        content.addSubview_(mic_label)

        mic_hint = NSTextField.alloc().initWithFrame_(
            NSMakeRect(x_mic - 20, btn_y - 34, btn_size + 40, 14))
        mic_hint.setStringValue_("F18 Toggle / F19 Halten")
        mic_hint.setEditable_(False)
        mic_hint.setBezeled_(False)
        mic_hint.setDrawsBackground_(False)
        mic_hint.setAlignment_(1)
        mic_hint.setFont_(NSFont.systemFontOfSize_(10))
        mic_hint.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(mic_hint)

        self.ocr_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(x_ocr, btn_y, btn_size, btn_size))
        self.ocr_btn.setBordered_(False)
        self.ocr_btn.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        self.ocr_btn.setImage_(
            _make_circle_icon(btn_size, NSColor.systemOrangeColor(),
                              _draw_camera))
        self.ocr_btn.setTarget_(self)
        self.ocr_btn.setAction_("ocrClicked:")
        content.addSubview_(self.ocr_btn)

        ocr_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(x_ocr - 20, btn_y - 20, btn_size + 40, 16))
        ocr_label.setStringValue_("Screenshot")
        ocr_label.setEditable_(False)
        ocr_label.setBezeled_(False)
        ocr_label.setDrawsBackground_(False)
        ocr_label.setAlignment_(1)
        ocr_label.setFont_(NSFont.systemFontOfSize_(11))
        ocr_label.setTextColor_(NSColor.labelColor())
        content.addSubview_(ocr_label)

        ocr_hint = NSTextField.alloc().initWithFrame_(
            NSMakeRect(x_ocr - 20, btn_y - 34, btn_size + 40, 14))
        ocr_hint.setStringValue_("F17")
        ocr_hint.setEditable_(False)
        ocr_hint.setBezeled_(False)
        ocr_hint.setDrawsBackground_(False)
        ocr_hint.setAlignment_(1)
        ocr_hint.setFont_(NSFont.systemFontOfSize_(10))
        ocr_hint.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(ocr_hint)

        # --- Textfeld ---
        scroll_frame = NSMakeRect(pad, 100, inner_w, 190)
        self.scroll_view = NSScrollView.alloc().initWithFrame_(scroll_frame)
        self.scroll_view.setHasVerticalScroller_(True)
        self.scroll_view.setBorderType_(1)

        text_frame = NSMakeRect(0, 0, inner_w - 2, 190)
        self.text_view = NSTextView.alloc().initWithFrame_(text_frame)
        self.text_view.setEditable_(True)
        self.text_view.setSelectable_(True)
        self.text_view.setRichText_(False)
        self.text_view.setFont_(NSFont.systemFontOfSize_(14))
        self.text_view.textContainer().setWidthTracksTextView_(True)
        self.text_view.setDelegate_(self)
        self.scroll_view.setDocumentView_(self.text_view)
        content.addSubview_(self.scroll_view)

        # --- Untere Buttons ---
        btn_w = (inner_w - 20) // 3
        self.copy_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(pad, 55, btn_w, 32))
        self.copy_btn.setTitle_("Kopieren")
        self.copy_btn.setBezelStyle_(NSBezelStyleRounded)
        self.copy_btn.setTarget_(self)
        self.copy_btn.setAction_("copyClicked:")
        content.addSubview_(self.copy_btn)

        self.insert_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(pad + btn_w + 10, 55, btn_w, 32))
        self.insert_btn.setTitle_("Einfuegen")
        self.insert_btn.setBezelStyle_(NSBezelStyleRounded)
        self.insert_btn.setTarget_(self)
        self.insert_btn.setAction_("insertClicked:")
        content.addSubview_(self.insert_btn)

        self.clear_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(pad + 2 * (btn_w + 10), 55, btn_w, 32))
        self.clear_btn.setTitle_("Leeren")
        self.clear_btn.setBezelStyle_(NSBezelStyleRounded)
        self.clear_btn.setTarget_(self)
        self.clear_btn.setAction_("clearClicked:")
        content.addSubview_(self.clear_btn)

        # --- Status-Label ---
        self.status_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(pad, 15, inner_w, 30))
        self.status_label.setStringValue_("Bereit")
        self.status_label.setEditable_(False)
        self.status_label.setBezeled_(False)
        self.status_label.setDrawsBackground_(False)
        self.status_label.setFont_(NSFont.systemFontOfSize_(13))
        self.status_label.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(self.status_label)

    @objc.python_method
    def set_mic_icon(self, recording=False):
        if recording:
            self.mic_btn.setImage_(
                _make_circle_icon(60, NSColor.systemRedColor(), _draw_stop))
        else:
            self.mic_btn.setImage_(
                _make_circle_icon(60, NSColor.systemBlueColor(), _draw_mic))

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


class AppActivationObserver(NSObject):
    """Beobachtet App-Wechsel und merkt sich die letzte externe App."""

    @objc.python_method
    def setup(self, own_bundle_id):
        self._own_bundle_id = own_bundle_id
        self._last_external_app = None
        ws = NSWorkspace.sharedWorkspace()
        ws.notificationCenter().addObserver_selector_name_object_(
            self, "appDidActivate:",
            NSWorkspaceDidActivateApplicationNotification, None)
        return self

    def appDidActivate_(self, notification):
        try:
            app = notification.userInfo()["NSWorkspaceApplicationKey"]
            bundle_id = app.bundleIdentifier()
            if bundle_id and bundle_id != self._own_bundle_id:
                self._last_external_app = app
        except Exception:
            pass

    @objc.python_method
    def last_external_app(self):
        return self._last_external_app


class AudioTranskriptApp(rumps.App):
    """Menu-Bar-App mit Floating Panel."""

    def __init__(self):
        log.info("AudioTranskriptApp.__init__ startet")
        super().__init__(APP_NAME, icon=ICON_PATH, template=True)
        self.panel = TranscriptPanel.alloc().init().setup()
        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self._text_was_edited = False
        self.panel.on_mic_click = self._toggle_recording
        self.panel.on_ocr_click = self._do_screenshot_ocr
        self.panel.on_copy_click = self._copy_text
        self.panel.on_insert_click = self._insert_panel_text
        self.panel.on_clear_click = self._clear_text
        self.panel.on_text_edited = self._on_text_edited
        self._recording_start = None
        self._recording_timer = None
        self._chunk_timer = None
        self._is_transcribing_chunk = False
        self.menu = [
            rumps.MenuItem("Oeffnen/Schliessen",
                           callback=self._toggle_panel),
            None,
            rumps.MenuItem("Beenden", callback=self._quit),
        ]

        self._app_observer = AppActivationObserver.alloc().init().setup(
            "com.matze.audio-transkript")

        # Hotkeys: F17=OCR, F18=Toggle, F19=Push-to-Talk
        self.hotkeys = HotkeyManager(
            on_mic_toggle=self._toggle_recording,
            on_mic_ptt_start=self._start_ptt_recording,
            on_mic_ptt_stop=self._stop_ptt_recording,
            on_ocr_trigger=self._do_screenshot_ocr,
        )
        self.hotkeys.start()
        log.info("Hotkeys und Observer eingerichtet")

        self.panel.mic_btn.setEnabled_(False)
        self.transcriber.load_model(
            on_progress=lambda msg: _on_main(
                lambda: self.panel.set_status(msg)),
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

    # --- Hilfsfunktion: Text in Ziel-App einfuegen (nie Main-Thread blockieren) ---

    def _insert_in_target(self, text):
        """Text in Ziel-App einfuegen — im Hintergrund-Thread."""
        target = self._app_observer.last_external_app()
        if not target:
            return

        def _run():
            try:
                activate_app(target)
                _time.sleep(0.15)
                type_text(text)
                log.info("Text eingefuegt (%d Zeichen)", len(text))
            except Exception as e:
                log.exception("Fehler beim Einfuegen: %s", e)

        threading.Thread(target=_run, daemon=True).start()

    # --- Aktionen ---

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
            self.panel.set_status("Kein Text zum Einfuegen")
            return
        self._insert_in_target(text)
        self.panel.set_status("Text eingefuegt")

    def _clear_text(self):
        self.panel.set_text("")
        self._text_was_edited = False
        self.panel.set_status("Bereit")

    # --- Aufnahme: Toggle-Modus (F18 / Button) ---

    def _toggle_recording(self):
        log.info("_toggle_recording: is_recording=%s",
                 self.recorder.is_recording)
        if self.recorder.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        """Aufnahme starten (gemeinsam fuer Toggle und PTT)."""
        if self.recorder.is_recording:
            return
        if not self._text_was_edited:
            self.panel.set_text("")
        self.recorder.start()
        self._recording_start = _time.time()
        self.panel.set_mic_icon(recording=True)
        self.panel.set_status("Aufnahme laeuft...")
        self._recording_timer = rumps.Timer(
            self._update_recording_time, 1)
        self._recording_timer.start()
        self._chunk_timer = rumps.Timer(self._transcribe_chunk, 15)
        self._chunk_timer.start()

    def _stop_recording(self):
        """Aufnahme stoppen (gemeinsam fuer Toggle und PTT)."""
        if not self.recorder.is_recording:
            return
        if self._chunk_timer:
            self._chunk_timer.stop()
            self._chunk_timer = None
        self._is_transcribing_chunk = False
        if self._recording_timer:
            self._recording_timer.stop()
            self._recording_timer = None
        self.panel.set_mic_icon(recording=False)
        audio = self.recorder.stop()
        log.info("recorder.stop: audio len=%d", len(audio))
        if len(audio) > 0:
            self.panel.set_status("Verarbeite...")
            self._process_final_chunk(audio)
        elif not self.panel.get_text().strip():
            self.panel.set_status("Keine Aufnahme erkannt")
        else:
            self.panel.set_status("Bereit")

    # --- Aufnahme: Push-to-Talk (F19) ---

    def _start_ptt_recording(self):
        """F19 gedrueckt — Aufnahme starten."""
        log.info("PTT start")
        self._start_recording()

    def _stop_ptt_recording(self):
        """F19 losgelassen — Aufnahme stoppen + transkribieren."""
        log.info("PTT stop")
        self._stop_recording()

    # --- Timer-Callbacks (abgesichert) ---

    def _update_recording_time(self, _):
        try:
            if self._recording_start and self.recorder.is_recording:
                elapsed = _time.time() - self._recording_start
                mins, secs = divmod(int(elapsed), 60)
                self.panel.set_status(
                    f"Aufnahme laeuft... {mins:02d}:{secs:02d}")
        except Exception:
            pass

    def _transcribe_chunk(self, _):
        """Alle 10 Sek. neuen Audio-Abschnitt transkribieren."""
        try:
            if not self.recorder.is_recording:
                return
            if self._is_transcribing_chunk:
                return
            audio = self.recorder.take_chunks()
            if len(audio) < SAMPLE_RATE * 2:
                return
            self._is_transcribing_chunk = True

            def _run():
                try:
                    text, lang = self.transcriber.transcribe(audio)

                    def _update():
                        self._is_transcribing_chunk = False
                        if text and self.recorder.is_recording:
                            self.panel.append_text(text)
                            log.info("chunk: %r", text[:60])
                            self._insert_in_target(text)

                    _on_main(_update)
                except Exception as e:
                    self._is_transcribing_chunk = False
                    log.exception("Chunk-Fehler: %s", e)

            threading.Thread(target=_run, daemon=True).start()
        except Exception as e:
            log.exception("_transcribe_chunk Fehler: %s", e)

    # --- Modell + Transkription ---

    def _on_model_loaded(self):
        log.info("Modell geladen, Button aktiviert")
        self.panel.mic_btn.setEnabled_(True)
        self.panel.set_status("Bereit")

    def _process_final_chunk(self, audio):
        """Letzten Audio-Rest nach Stopp transkribieren."""
        log.info("_process_final_chunk: %.1fs",
                 len(audio) / 16000)

        def _run():
            try:
                text, lang = self.transcriber.transcribe(audio)
                log.info("final: %r", text[:60] if text else '')
                _on_main(lambda: self._on_recording_finished(
                    text, lang))
            except Exception as e:
                log.exception("Final-Chunk Fehler: %s", e)

        threading.Thread(target=_run, daemon=True).start()

    def _on_recording_finished(self, text, lang):
        lang_names = {
            "de": "Deutsch", "en": "Englisch",
            "fr": "Franzoesisch", "es": "Spanisch",
            "it": "Italienisch", "nl": "Niederlaendisch",
        }
        lang_label = lang_names.get(lang, lang)
        if text:
            self.panel.append_text(text)
            self._insert_in_target(text)
        self._text_was_edited = False
        self.panel.set_status(f"Bereit ({lang_label})")

    # --- Screenshot-OCR ---

    def _do_screenshot_ocr(self):
        """Screenshot aufnehmen und OCR durchfuehren."""
        was_visible = self.panel.is_visible()
        if was_visible:
            self.panel.hide()

        def _run():
            try:
                _time.sleep(0.3)
                image = capture_screenshot()

                if was_visible:
                    _on_main(lambda: self.panel.show())

                if image is None:
                    _on_main(lambda: self.panel.set_status(
                        "Screenshot abgebrochen"))
                    return

                _on_main(lambda: self.panel.set_status("OCR laeuft..."))
                text = ocr_image(image)
                _on_main(lambda: self._on_ocr_done(text))
            except Exception as e:
                log.exception("Screenshot-OCR Fehler: %s", e)

        threading.Thread(target=_run, daemon=True).start()

    def _on_ocr_done(self, text):
        if text:
            self.panel.set_text(text)
            self._text_was_edited = False
            self.panel.set_status("Text erkannt")
            self._insert_in_target(text)
        else:
            self.panel.set_status("Kein Text erkannt")


def _check_accessibility():
    """Prueft Accessibility-Berechtigung und zeigt Hinweis."""
    from ApplicationServices import AXIsProcessTrustedWithOptions
    from CoreFoundation import kCFBooleanTrue

    options = {"AXTrustedCheckOptionPrompt": kCFBooleanTrue}
    trusted = AXIsProcessTrustedWithOptions(options)
    if not trusted:
        rumps.alert(
            title="Berechtigung erforderlich",
            message=(
                "Audio Transkript benoetigt Zugriff auf "
                "Bedienungshilfen (Accessibility) fuer Hotkeys "
                "und Text-Einfuegung.\n\n"
                "Bitte erteile die Berechtigung unter:\n"
                "Systemeinstellungen → Datenschutz & Sicherheit "
                "→ Bedienungshilfen"
            ),
        )
    return trusted


def main():
    _check_accessibility()
    app = AudioTranskriptApp()
    app.run()


if __name__ == "__main__":
    main()
