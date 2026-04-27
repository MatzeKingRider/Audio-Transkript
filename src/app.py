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
    NSWindowStyleMaskFullSizeContentView,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSColor,
    NSScreen,
    NSWorkspace,
    NSWorkspaceDidActivateApplicationNotification,
    NSImageScaleProportionallyUpOrDown,
    NSTouchBar,
    NSCustomTouchBarItem,
    NSSegmentedControl,
    NSSegmentSwitchTrackingMomentary,
    NSImageNameTouchBarAudioInputTemplate,
    NSImageNameTouchBarRecordStartTemplate,
    NSImageNameTouchBarRecordStopTemplate,
)
from PyObjCTools import AppHelper
from src.config import (
    APP_NAME, ICON_PATH, PANEL_WIDTH, PANEL_HEIGHT, PANEL_TITLE,
    HOTKEY_MIC_TOGGLE, HOTKEY_OCR, SAMPLE_RATE,
    UI_CORNER_RADIUS, UI_TEXT_INSET, UI_LINE_HEIGHT, UI_FONT_SIZE,
)
from src.recorder import Recorder
from src.transcriber import Transcriber, dedupe_overlap
from src.ocr import capture_screenshot, ocr_image
from src.text_input import type_text, activate_app
from src.hotkeys import HotkeyManager


def _on_main(fn):
    """Fuehrt fn auf dem Main-Thread aus (sicher von Hintergrund-Threads)."""
    AppHelper.callAfter(fn)


# --- Icon-Zeichnung ---

def _make_circle_icon(size, bg_color, draw_fn):
    """Rundes Icon im Glaslook: halbtransparent, Highlight-Schimmer oben."""
    img = NSImage.alloc().initWithSize_(NSMakeSize(size, size))
    img.lockFocus()
    # Katalogfarbe in RGB-Farbraum konvertieren, dann 60% Opacity
    try:
        rgb = bg_color.colorUsingColorSpaceName_("NSCalibratedRGBColorSpace")
        if rgb is None:
            rgb = bg_color.colorUsingColorSpaceName_("NSDeviceRGBColorSpace")
        r, g, b = rgb.redComponent(), rgb.greenComponent(), rgb.blueComponent()
        NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 0.62).setFill()
    except Exception:
        NSColor.colorWithWhite_alpha_(0.4, 0.62).setFill()
    circle = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(0, 0, size, size))
    circle.fill()
    # Heller Highlight-Schimmer (obere Hälfte, weiß halbtransparent)
    NSColor.colorWithWhite_alpha_(1.0, 0.28).setFill()
    highlight = NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(size * 0.12, size * 0.50, size * 0.76, size * 0.42))
    highlight.fill()
    # Feiner weißer Rand
    NSColor.colorWithWhite_alpha_(1.0, 0.40).setStroke()
    border = NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(1, 1, size - 2, size - 2))
    border.setLineWidth_(1.0)
    border.stroke()
    # Symbol
    NSColor.whiteColor().setFill()
    NSColor.whiteColor().setStroke()
    draw_fn(size)
    img.unlockFocus()
    return img


def _draw_mic(size):
    """Klassisches Mikrofon: Kapsel oben, U-Bogen darunter, Stiel, Fuss."""
    cx = size / 2
    lw = size * 0.05
    # Kapsel (Mikrofon-Körper)
    cap_w = size * 0.20
    cap_h = size * 0.28
    cap_y = size * 0.54
    kapsel = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(cx - cap_w / 2, cap_y, cap_w, cap_h), cap_w / 2, cap_w / 2)
    kapsel.fill()
    # U-Bogen um die Kapsel (öffnet nach oben)
    arm_r = size * 0.19
    arm_cy = cap_y + size * 0.04
    bogen = NSBezierPath.bezierPath()
    bogen.setLineWidth_(lw)
    bogen.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
        (cx, arm_cy), arm_r, 180, 0, False)
    bogen.stroke()
    # Stiel
    stiel = NSBezierPath.bezierPath()
    stiel.setLineWidth_(lw)
    stiel.moveToPoint_((cx, arm_cy - arm_r))
    stiel.lineToPoint_((cx, size * 0.18))
    stiel.stroke()
    # Fuss (breiter als Stiel)
    fuss_w = size * 0.30
    fuss = NSBezierPath.bezierPath()
    fuss.setLineWidth_(lw)
    fuss.moveToPoint_((cx - fuss_w / 2, size * 0.18))
    fuss.lineToPoint_((cx + fuss_w / 2, size * 0.18))
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


class PTTButton(NSButton):
    def mouseDown_(self, event):
        try:
            target = self.target()
            if target and hasattr(target, "pttButtonDown_"):
                target.pttButtonDown_(self)
        except Exception:
            pass
        super(PTTButton, self).mouseDown_(event)

    def mouseUp_(self, event):
        try:
            target = self.target()
            if target and hasattr(target, "pttButtonUp_"):
                target.pttButtonUp_(self)
        except Exception:
            pass
        super(PTTButton, self).mouseUp_(event)


class TranscriptPanel(NSObject):
    """Floating NSPanel mit Buttons, Textfeld und Status-Anzeige."""

    @objc.python_method
    def setup(self):
        self.on_mic_click = None
        self.on_mic_ptt_down = None
        self.on_mic_ptt_up = None
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
            | NSWindowStyleMaskFullSizeContentView
        )
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, PANEL_WIDTH, PANEL_HEIGHT),
            style, NSBackingStoreBuffered, False)
        self.panel.setTitle_(PANEL_TITLE)
        self.panel.setTitlebarAppearsTransparent_(True)
        self.panel.setTitleVisibility_(1)  # NSWindowTitleHidden
        self.panel.setLevel_(NSFloatingWindowLevel)
        self.panel.setHidesOnDeactivate_(False)
        self.panel.setFloatingPanel_(True)

        # Immer Dunkel-Modus, unabhängig von System-Einstellung
        try:
            from AppKit import NSAppearance
            dark = NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua")
            self.panel.setAppearance_(dark)
        except Exception as e:
            log.warning("Dark-Mode konnte nicht gesetzt werden: %s", e)

        # Maximale Transparenz: clearColor + NSVisualEffectView (Blur hinter dem Fenster)
        try:
            self.panel.setOpaque_(False)
            self.panel.setBackgroundColor_(NSColor.clearColor())
            from AppKit import NSVisualEffectView
            content_view = self.panel.contentView()
            bounds = content_view.bounds()
            effect = NSVisualEffectView.alloc().initWithFrame_(bounds)
            # Material 3 = NSVisualEffectMaterialTitlebar → dünn, transparent im Darkmode
            try:
                effect.setMaterial_(3)
            except Exception:
                pass
            effect.setBlendingMode_(0)   # BehindWindow
            effect.setState_(1)          # Active
            effect.setAutoresizingMask_(2 | 16)
            if content_view.subviews():
                content_view.addSubview_positioned_relativeTo_(
                    effect, 0, content_view.subviews()[0])
            else:
                content_view.addSubview_(effect)
            # Abgerundete Ecken
            content_view.setWantsLayer_(True)
            layer = content_view.layer()
            if layer is not None:
                layer.setCornerRadius_(UI_CORNER_RADIUS)
                layer.setMasksToBounds_(True)
        except Exception as e:
            log.warning("Vibrancy/Appearance Setup fehlgeschlagen: %s", e)

        screen = NSScreen.mainScreen().frame()
        x = (screen.size.width - PANEL_WIDTH) / 2
        y = (screen.size.height - PANEL_HEIGHT) / 2
        self.panel.setFrameOrigin_((x, y))

        content = self.panel.contentView()

        # --- Hilfsfunktion: glasiger Aktions-Button ---
        def _make_sf_button(title, symbol_name):
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 52))
            btn.setTitle_(title)
            btn.setBezelStyle_(NSBezelStyleRounded)
            btn.setWantsLayer_(True)
            try:
                btn.layer().setBackgroundColor_(
                    NSColor.colorWithWhite_alpha_(1.0, 0.12).CGColor())
                btn.layer().setCornerRadius_(8.0)
                btn.layer().setBorderWidth_(0.5)
                btn.layer().setBorderColor_(
                    NSColor.colorWithWhite_alpha_(1.0, 0.25).CGColor())
            except Exception:
                pass
            try:
                img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                    symbol_name, None)
                if img:
                    btn.setImage_(img)
                    btn.setImagePosition_(2)  # NSImageAbove
            except Exception:
                pass
            btn.setFont_(NSFont.systemFontOfSize_(11))
            return btn

        # --- Alle Views erstellen (Frames werden von _relayout gesetzt) ---

        # Runde Hauptbuttons
        btn_size = 60
        self.mic_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, btn_size, btn_size))
        self.mic_btn.setBordered_(False)
        self.mic_btn.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        self.mic_btn.setImage_(_make_circle_icon(btn_size, NSColor.systemBlueColor(), _draw_mic))
        self.mic_btn.setTarget_(self)
        self.mic_btn.setAction_("micClicked:")
        self.mic_btn.setToolTip_("Aufnahme Start/Stopp (F18 / Cmd+Shift+T)")
        content.addSubview_(self.mic_btn)

        self.mic_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 16))
        self.mic_label.setStringValue_("Mikrofon")
        self.mic_label.setEditable_(False); self.mic_label.setBezeled_(False)
        self.mic_label.setDrawsBackground_(False); self.mic_label.setAlignment_(1)
        self.mic_label.setFont_(NSFont.systemFontOfSize_(11))
        self.mic_label.setTextColor_(NSColor.labelColor())
        content.addSubview_(self.mic_label)

        self.mic_hint = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 120, 14))
        self.mic_hint.setStringValue_("F18 / Cmd+Shift+T")
        self.mic_hint.setEditable_(False); self.mic_hint.setBezeled_(False)
        self.mic_hint.setDrawsBackground_(False); self.mic_hint.setAlignment_(1)
        self.mic_hint.setFont_(NSFont.systemFontOfSize_(10))
        self.mic_hint.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(self.mic_hint)

        self.ptt_btn = PTTButton.alloc().initWithFrame_(NSMakeRect(0, 0, btn_size, btn_size))
        self.ptt_btn.setBordered_(False)
        self.ptt_btn.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        self.ptt_btn.setImage_(_make_circle_icon(btn_size, NSColor.systemBlueColor(), _draw_mic))
        self.ptt_btn.setTarget_(self)
        self.ptt_btn.setToolTip_("Push-to-Talk halten (F19 / Cmd+Shift+M)")
        content.addSubview_(self.ptt_btn)

        self.ptt_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 16))
        self.ptt_label.setStringValue_("PTT")
        self.ptt_label.setEditable_(False); self.ptt_label.setBezeled_(False)
        self.ptt_label.setDrawsBackground_(False); self.ptt_label.setAlignment_(1)
        self.ptt_label.setFont_(NSFont.systemFontOfSize_(11))
        self.ptt_label.setTextColor_(NSColor.labelColor())
        content.addSubview_(self.ptt_label)

        self.ptt_hint = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 120, 14))
        self.ptt_hint.setStringValue_("F19 / Cmd+Shift+M halten")
        self.ptt_hint.setEditable_(False); self.ptt_hint.setBezeled_(False)
        self.ptt_hint.setDrawsBackground_(False); self.ptt_hint.setAlignment_(1)
        self.ptt_hint.setFont_(NSFont.systemFontOfSize_(10))
        self.ptt_hint.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(self.ptt_hint)

        self.ocr_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, btn_size, btn_size))
        self.ocr_btn.setBordered_(False)
        self.ocr_btn.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        self.ocr_btn.setImage_(_make_circle_icon(btn_size, NSColor.systemOrangeColor(), _draw_camera))
        self.ocr_btn.setTarget_(self)
        self.ocr_btn.setAction_("ocrClicked:")
        self.ocr_btn.setToolTip_("Screenshot + OCR (F17 / Cmd+Shift+O)")
        content.addSubview_(self.ocr_btn)

        self.ocr_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 16))
        self.ocr_label.setStringValue_("Screenshot")
        self.ocr_label.setEditable_(False); self.ocr_label.setBezeled_(False)
        self.ocr_label.setDrawsBackground_(False); self.ocr_label.setAlignment_(1)
        self.ocr_label.setFont_(NSFont.systemFontOfSize_(11))
        self.ocr_label.setTextColor_(NSColor.labelColor())
        content.addSubview_(self.ocr_label)

        self.ocr_hint = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 14))
        self.ocr_hint.setStringValue_("F17 / Cmd+Shift+O")
        self.ocr_hint.setEditable_(False); self.ocr_hint.setBezeled_(False)
        self.ocr_hint.setDrawsBackground_(False); self.ocr_hint.setAlignment_(1)
        self.ocr_hint.setFont_(NSFont.systemFontOfSize_(10))
        self.ocr_hint.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(self.ocr_hint)

        # Textfeld
        self.scroll_view = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 100))
        self.scroll_view.setHasVerticalScroller_(True)
        self.scroll_view.setHasHorizontalScroller_(False)
        self.scroll_view.setAutohidesScrollers_(False)
        self.scroll_view.setBorderType_(1)

        self.text_view = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 100))
        self.text_view.setEditable_(True)
        self.text_view.setSelectable_(True)
        self.text_view.setRichText_(False)
        self.text_view.setFont_(NSFont.systemFontOfSize_(UI_FONT_SIZE))
        self.text_view.setTextColor_(NSColor.labelColor())
        self.text_view.setAutoresizingMask_(2)  # NSViewWidthSizable
        self.text_view.setHorizontallyResizable_(False)
        self.text_view.setTextContainerInset_(NSMakeSize(6, 6))
        tc = self.text_view.textContainer()
        tc.setWidthTracksTextView_(True)
        tc.setContainerSize_(NSMakeSize(float("inf"), float("inf")))
        tc.setLineFragmentPadding_(0)
        from AppKit import NSMutableParagraphStyle
        ps = NSMutableParagraphStyle.alloc().init()
        ps.setLineHeightMultiple_(UI_LINE_HEIGHT)
        self.text_view.setDefaultParagraphStyle_(ps)
        try:
            self.text_view.setTypingAttributes_({
                "NSFont": NSFont.systemFontOfSize_(UI_FONT_SIZE),
                "NSColor": NSColor.labelColor(),
                "NSParagraphStyle": ps,
            })
        except Exception:
            pass
        self.text_view.setDelegate_(self)
        self.scroll_view.setDocumentView_(self.text_view)
        content.addSubview_(self.scroll_view)

        # Untere Aktions-Buttons
        self.copy_btn = _make_sf_button("Kopieren", "doc.on.doc")
        self.copy_btn.setTarget_(self); self.copy_btn.setAction_("copyClicked:")
        content.addSubview_(self.copy_btn)

        self.insert_btn = _make_sf_button("Einfügen", "arrow.down.to.line")
        self.insert_btn.setTarget_(self); self.insert_btn.setAction_("insertClicked:")
        content.addSubview_(self.insert_btn)

        self.clear_btn = _make_sf_button("Leeren", "trash")
        self.clear_btn.setTarget_(self); self.clear_btn.setAction_("clearClicked:")
        content.addSubview_(self.clear_btn)

        # Status-Label
        self.status_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 30))
        self.status_label.setStringValue_("Bereit")
        self.status_label.setEditable_(False); self.status_label.setBezeled_(False)
        self.status_label.setDrawsBackground_(False)
        self.status_label.setFont_(NSFont.systemFontOfSize_(13))
        self.status_label.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(self.status_label)

        # Delegate für Resize-Events + initiales Layout
        self.panel.setDelegate_(self)
        self._relayout()

    @objc.python_method
    def _relayout(self):
        """Berechnet alle Frames neu basierend auf der aktuellen Fenstergröße."""
        w = self.panel.contentView().bounds().size.width
        h = self.panel.contentView().bounds().size.height
        pad = 20
        inner_w = w - 2 * pad
        btn_size = 60
        gap = 40

        # Untere Zone: Status + 3 Aktions-Buttons
        status_h = 28
        status_y = 10
        self.status_label.setFrame_(NSMakeRect(pad, status_y, inner_w, status_h))

        btn_h = 52
        btn_area_y = status_y + status_h + 6
        btn_w = (inner_w - 20) // 3
        self.copy_btn.setFrame_(NSMakeRect(pad, btn_area_y, btn_w, btn_h))
        self.insert_btn.setFrame_(NSMakeRect(pad + btn_w + 10, btn_area_y, btn_w, btn_h))
        self.clear_btn.setFrame_(NSMakeRect(pad + 2 * (btn_w + 10), btn_area_y, btn_w, btn_h))

        # Obere Zone: Runde Buttons zentriert
        lbl_h, hint_h = 16, 14
        top_block_h = btn_size + lbl_h + hint_h + 6
        top_y = h - top_block_h - 28   # 28px Abstand zum oberen Rand (Traffic-Light-Bereich)
        total = 3 * btn_size + 2 * gap
        x_mic = (w - total) / 2
        x_ptt = x_mic + btn_size + gap
        x_ocr = x_ptt + btn_size + gap
        lbl_w = btn_size + 40

        self.mic_btn.setFrame_(NSMakeRect(x_mic, top_y, btn_size, btn_size))
        self.mic_label.setFrame_(NSMakeRect(x_mic - 20, top_y - lbl_h - 2, lbl_w, lbl_h))
        self.mic_hint.setFrame_(NSMakeRect(x_mic - 20, top_y - lbl_h - hint_h - 4, lbl_w, hint_h))

        self.ptt_btn.setFrame_(NSMakeRect(x_ptt, top_y, btn_size, btn_size))
        self.ptt_label.setFrame_(NSMakeRect(x_ptt - 20, top_y - lbl_h - 2, lbl_w, lbl_h))
        self.ptt_hint.setFrame_(NSMakeRect(x_ptt - 20, top_y - lbl_h - hint_h - 4, lbl_w, hint_h))

        self.ocr_btn.setFrame_(NSMakeRect(x_ocr, top_y, btn_size, btn_size))
        self.ocr_label.setFrame_(NSMakeRect(x_ocr - 20, top_y - lbl_h - 2, lbl_w, lbl_h))
        self.ocr_hint.setFrame_(NSMakeRect(x_ocr - 20, top_y - lbl_h - hint_h - 4, lbl_w, hint_h))

        # Mittlere Zone: Scrollview füllt den Rest
        scroll_top_y = btn_area_y + btn_h + 8
        round_bottom_y = top_y - lbl_h - hint_h - 8
        scroll_h = max(60, round_bottom_y - scroll_top_y)
        self.scroll_view.setFrame_(NSMakeRect(pad, scroll_top_y, inner_w, scroll_h))

    def windowDidResize_(self, notification):
        self._relayout()

    @objc.python_method
    def set_mic_icon(self, recording=False):
        if recording:
            self.mic_btn.setImage_(
                _make_circle_icon(60, NSColor.systemRedColor(), _draw_stop))
        else:
            self.mic_btn.setImage_(
                _make_circle_icon(60, NSColor.systemBlueColor(), _draw_mic))

    @objc.python_method
    def set_status(self, text, kind="idle"):
        self.status_label.setStringValue_(text)
        try:
            if kind == "recording":
                self.status_label.setTextColor_(NSColor.systemRedColor())
            elif kind == "processing":
                self.status_label.setTextColor_(NSColor.systemOrangeColor())
            else:
                self.status_label.setTextColor_(
                    NSColor.secondaryLabelColor())
        except Exception:
            pass

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
    def pttButtonDown_(self, sender):
        if self.on_mic_ptt_down:
            self.on_mic_ptt_down()

    @objc.IBAction
    def pttButtonUp_(self, sender):
        if self.on_mic_ptt_up:
            self.on_mic_ptt_up()

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


class TouchBarController(NSObject):
    """PTT-Button in der Touch Bar — nur aktiv auf Macs mit Touch Bar."""

    PTT_IDENTIFIER = "com.matze.audiotranskript.ptt"

    @objc.python_method
    def setup(self, ptt_start_fn, ptt_stop_fn, panel_window=None):
        self._ptt_start = ptt_start_fn
        self._ptt_stop = ptt_stop_fn
        self._touch_bar = None
        self._ptt_segment = None
        self._build(panel_window)
        return self

    @objc.python_method
    def _build(self, panel_window=None):
        from AppKit import NSSet
        item = self._create_item()

        tb = NSTouchBar.alloc().init()
        tb.setDefaultItemIdentifiers_([self.PTT_IDENTIFIER])
        tb.setTemplateItems_(NSSet.setWithObject_(item))
        self._touch_bar = tb

        if panel_window is not None:
            panel_window.setTouchBar_(tb)
        NSApplication.sharedApplication().setTouchBar_(tb)

    @objc.python_method
    def _create_item(self):
        item = NSCustomTouchBarItem.alloc().initWithIdentifier_(self.PTT_IDENTIFIER)
        # NSSegmentedControl im Momentary-Modus: Action faeugt bei Druecken UND Loslassen —
        # isSelectedForSegment_ gibt True beim Druecken, False beim Loslassen.
        seg = NSSegmentedControl.segmentedControlWithLabels_trackingMode_target_action_(
            ["🎙 PTT"],
            NSSegmentSwitchTrackingMomentary,
            self,
            "pttSegmentAction:",
        )
        seg.setWidth_forSegment_(80, 0)
        self._ptt_segment = seg
        item.setView_(seg)
        return item

    @objc.IBAction
    def pttSegmentAction_(self, sender):
        if sender.isSelectedForSegment_(0):
            self._ptt_start()
        else:
            self._ptt_stop()

    @objc.python_method
    def update_recording_state(self, recording: bool):
        seg = self._ptt_segment
        if seg is None:
            return
        # Im Momentary-Modus kann man kein Label programmatisch aendern
        # aber wir koennen den Segment-Zustand visuell beeinflussen:
        if recording:
            seg.setLabel_forSegment_("⏹ Stopp", 0)
        else:
            seg.setLabel_forSegment_("🎙 PTT", 0)


class AudioTranskriptApp(rumps.App):
    """Menu-Bar-App mit Floating Panel."""

    def __init__(self):
        log.info("AudioTranskriptApp.__init__ startet")
        super().__init__(APP_NAME, icon=ICON_PATH, template=True)
        self.panel = TranscriptPanel.alloc().init().setup()
        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self._text_was_edited = False
        self._target_app = None
        self.panel.on_mic_click = self._toggle_recording
        self.panel.on_mic_ptt_down = self._start_ptt_recording
        self.panel.on_mic_ptt_up = self._stop_ptt_recording
        self.panel.on_ocr_click = self._do_screenshot_ocr
        self.panel.on_copy_click = self._copy_text
        self.panel.on_insert_click = self._insert_panel_text
        self.panel.on_clear_click = self._clear_text
        self.panel.on_text_edited = self._on_text_edited
        self._recording_start = None
        self._recording_timer = None
        self._chunk_timer = None
        self._is_transcribing_chunk = False
        self._next_chunk_is_overlap = False
        self._last_chunk_text = ""
        self.menu = [
            rumps.MenuItem("Oeffnen/Schliessen",
                           callback=self._toggle_panel),
            rumps.MenuItem("Im Hintergrund",
                           callback=self._go_background),
            None,
            rumps.MenuItem("Neustart",
                           callback=self._restart),
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

        # Touch Bar PTT — graceful, nur auf MacBook Pro mit Touch Bar aktiv
        self._touch_bar_ctrl = None
        try:
            ctrl = TouchBarController.alloc().init().setup(
                self._start_ptt_recording,
                self._stop_ptt_recording,
                panel_window=self.panel.panel,
            )
            self._touch_bar_ctrl = ctrl
            log.info("Touch Bar PTT eingerichtet")
        except Exception as e:
            log.info("Touch Bar nicht verfuegbar (erwartet auf Mac Mini): %s", e)

        log.info("Hotkeys und Observer eingerichtet")

        self.panel.mic_btn.setEnabled_(False)
        self.transcriber.load_model(
            on_progress=lambda msg: _on_main(
                lambda: self.panel.set_status(msg)),
            on_done=lambda: _on_main(self._on_model_loaded),
        )

    def _toggle_panel(self, _):
        self.panel.toggle()

    def _go_background(self, _):
        """Panel schliessen, App laeuft im Hintergrund weiter."""
        self.panel.hide()
        self.panel.set_status("Im Hintergrund (F18/F19 aktiv)")
        log.info("Hintergrund-Modus aktiviert")

    def _restart(self, _):
        """App komplett neu starten."""
        log.info("Neustart angefordert")
        self.hotkeys.stop()
        if self.recorder.is_recording:
            self.recorder.stop()
        import subprocess
        # Shell-Befehl: 1 Sek. warten, dann App oeffnen
        # Laeuft unabhaengig vom aktuellen Prozess weiter
        subprocess.Popen(
            'sleep 1 && open "/Applications/Audio Transkript.app"',
            shell=True)
        rumps.quit_application()

    def _quit(self, _):
        self.hotkeys.stop()
        rumps.quit_application()

    @rumps.clicked(APP_NAME)
    def on_icon_click(self, _):
        self.panel.toggle()

    def _on_text_edited(self):
        self._text_was_edited = True

    def _remember_target_app(self):
        """Merkt die App, in die wir nachher Text einfügen wollen."""
        from AppKit import NSWorkspace
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if not front:
            return
        bid = front.bundleIdentifier()
        if bid and bid != "com.matze.audio-transkript":
            self._target_app = front
        elif self._app_observer.last_external_app():
            self._target_app = self._app_observer.last_external_app()

    # --- Hilfsfunktion: Text in Ziel-App einfuegen (nie Main-Thread blockieren) ---

    def _insert_in_target(self, text):
        """Text in Ziel-App einfuegen — im Hintergrund-Thread."""
        target = self._target_app or self._app_observer.last_external_app()
        if not target:
            # Fallback: aktuell aktive App (falls Observer noch nichts hat)
            from AppKit import NSWorkspace
            front = NSWorkspace.sharedWorkspace().frontmostApplication()
            bid = front.bundleIdentifier() if front else None
            if bid and bid != "com.matze.audio-transkript":
                target = front
        if not target:
            log.warning("Kein Ziel-App gefunden")
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
        self._remember_target_app()
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
        if self._touch_bar_ctrl:
            self._touch_bar_ctrl.update_recording_state(True)
        self.panel.set_status("Aufnahme laeuft...", kind="recording")
        self._recording_timer = rumps.Timer(
            self._update_recording_time, 1)
        self._recording_timer.start()
        self._next_chunk_is_overlap = False
        self._last_chunk_text = ""
        # 1-Sekunden-Tick: entscheidet dynamisch, wann ein Chunk geschnitten wird
        self._chunk_timer = rumps.Timer(self._transcribe_chunk, 1)
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
        if self._touch_bar_ctrl:
            self._touch_bar_ctrl.update_recording_state(False)
        audio = self.recorder.stop()
        log.info("recorder.stop: audio len=%d", len(audio))
        if len(audio) > 0:
            self.panel.set_status("Verarbeite...", kind="processing")
            self._process_final_chunk(audio)
        elif not self.panel.get_text().strip():
            self.panel.set_status("Keine Aufnahme erkannt")
        else:
            self.panel.set_status("Bereit")

    # --- Aufnahme: Push-to-Talk (F19) ---

    def _start_ptt_recording(self):
        """F19 gedrueckt — Aufnahme starten."""
        self._remember_target_app()
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
                    f"Aufnahme laeuft... {mins:02d}:{secs:02d}",
                    kind="recording")
        except Exception:
            pass

    def _transcribe_chunk(self, _):
        """1-Sekunden-Tick: smart chunking.

        - Warten bis der Puffer >= 2s ist.
        - Bei Sprechpause (>=1.5s Stille) sauberen Chunk schneiden.
        - Bei Puffer >=25s Hard-Cut mit 0.5s Overlap.
        """
        try:
            if not self.recorder.is_recording:
                return
            if self._is_transcribing_chunk:
                return

            snapshot = self.recorder.get_audio_snapshot()
            buf_len = len(snapshot)
            min_len = SAMPLE_RATE * 2
            if buf_len < min_len:
                return

            is_overlap_chunk = False
            audio = None

            if self.recorder.has_silence_tail(min_silence_s=1.5,
                                              rms_threshold=0.008):
                audio = self.recorder.take_chunks()
                is_overlap_chunk = self._next_chunk_is_overlap
                self._next_chunk_is_overlap = False
            elif buf_len >= SAMPLE_RATE * 25:
                # Hard-Cut mit Overlap
                audio = self.recorder.take_chunks_with_overlap(overlap_s=0.5)
                is_overlap_chunk = self._next_chunk_is_overlap
                self._next_chunk_is_overlap = True
            else:
                return

            if audio is None or len(audio) < min_len:
                return

            self._is_transcribing_chunk = True
            prev_text = self._last_chunk_text

            def _run():
                try:
                    text, lang = self.transcriber.transcribe(audio)

                    def _update():
                        self._is_transcribing_chunk = False
                        final_text = text
                        if final_text and is_overlap_chunk and prev_text:
                            final_text = dedupe_overlap(prev_text, final_text)
                        if final_text and self.recorder.is_recording:
                            self._last_chunk_text = final_text
                            self.panel.append_text(final_text)
                            log.info("chunk: %r (overlap=%s)",
                                     final_text[:60], is_overlap_chunk)
                            self._insert_in_target(final_text)

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
        self._remember_target_app()
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

                _on_main(lambda: self.panel.set_status(
                    "OCR laeuft...", kind="processing"))
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
