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
    NSNormalWindowLevel,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskUtilityWindow,
    NSWindowStyleMaskFullSizeContentView,
    NSBackingStoreBuffered,
    NSColor,
    NSScreen,
    NSWorkspace,
    NSWorkspaceDidActivateApplicationNotification,
    NSWorkspaceDidWakeNotification,
    NSWorkspaceScreensDidWakeNotification,
    NSImageScaleProportionallyUpOrDown,
    NSLevelIndicator,
    NSSlider,
    NSTimer,
    NSEventTrackingRunLoopMode,
    NSDefaultRunLoopMode,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
)
from PyObjCTools import AppHelper
from Foundation import NSString, NSUserDefaults, NSNotificationCenter
from AppKit import NSApplicationDidChangeScreenParametersNotification
from src.config import (
    APP_NAME, ICON_PATH, PANEL_WIDTH, PANEL_HEIGHT, PANEL_TITLE,
    HOTKEY_MIC_TOGGLE, HOTKEY_OCR, SAMPLE_RATE,
    UI_CORNER_RADIUS, UI_TEXT_INSET, UI_LINE_HEIGHT, UI_FONT_SIZE,
    CLAUDE_USAGE_MONITOR_ENABLED,
)
from src import claude_usage
from src import vocabulary
from src.recorder import Recorder
from src.transcriber import Transcriber, dedupe_overlap
from src.ocr import capture_screenshot, ocr_image
from src.text_input import type_text, activate_app
from src.hotkeys import HotkeyManager
from src.f19_tap import F19EventTap


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


class MicButton(NSButton):
    """Reiner Toggle-Button: 1x klicken = Start, nochmal = Stopp.

    Push-to-Talk laeuft ueber den globalen F19-Hotkey, nicht ueber diesen Button —
    dort gibt es keine Race-Condition mit Click/Hold-Erkennung.
    """


class UsagePanelView(NSView):
    """Zeichnet kompakte Usage-Zeilen mit Fortschrittsbalken.

    Passt sich dynamisch an die Fensterbreite an (drawRect_ nutzt self.bounds()).
    """

    def initWithFrame_(self, frame):
        self = objc.super(UsagePanelView, self).initWithFrame_(frame)
        if self is None:
            return None
        # Python-only Instanzattribute — kein ObjC-Ivar-Problem
        self.__dict__["_rows"] = []
        self.__dict__["_warning_text"] = None
        return self

    def isFlipped(self):
        return True  # y-Koordinaten von oben nach unten

    @objc.python_method
    def update_rows(self, rows, warning_text=None):
        self.__dict__["_rows"] = list(rows) if rows else []
        self.__dict__["_warning_text"] = warning_text
        self.setNeedsDisplay_(True)

    def drawRect_(self, dirty):  # noqa: N802
        bounds = self.bounds()
        total_w = bounds.size.width

        ROW_H = 14
        GAP = 3
        BAR_H = 6
        LABEL_W = 108
        PCT_W = 32
        RIGHT_MARGIN = 4
        bar_x = LABEL_W + 4
        # Balkenbreite dynamisch — passt sich ans Fenster an
        bar_w = max(20.0, total_w - LABEL_W - 4 - PCT_W - 4 - 155 - RIGHT_MARGIN)
        pct_x = bar_x + bar_w + 4

        def _attrs(font, color):
            return {NSFontAttributeName: font,
                    NSForegroundColorAttributeName: color}

        main_font = NSFont.systemFontOfSize_(11)
        sec_font = NSFont.systemFontOfSize_(10)

        def _draw(text, rect, font, color):
            NSString.stringWithString_(text).drawInRect_withAttributes_(
                rect, _attrs(font, color))

        warning_text = self.__dict__.get("_warning_text")
        if warning_text:
            _draw(warning_text, NSMakeRect(0, 2, total_w, ROW_H * 2),
                  sec_font, NSColor.systemOrangeColor())
            return

        bar_bg = NSColor.quaternaryLabelColor()
        bar_fill = NSColor.systemBlueColor()

        for i, row in enumerate(self.__dict__.get("_rows") or []):
            top_y = i * (ROW_H + GAP)
            text_y = top_y + 1

            # Label
            lbl = row.get("label") or ""
            lbl_color = NSColor.labelColor() if i == 0 else NSColor.secondaryLabelColor()
            _draw(lbl, NSMakeRect(0, text_y, LABEL_W, ROW_H),
                  main_font if i == 0 else sec_font, lbl_color)

            # Balken-Hintergrund
            bar_y = top_y + (ROW_H - BAR_H) / 2
            r = BAR_H / 2
            bg_path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(bar_x, bar_y, bar_w, BAR_H), r, r)
            bar_bg.setFill()
            bg_path.fill()

            # Balken-Füllung
            pct = row.get("pct")
            if pct is not None:
                try:
                    fw = max(0.0, min(float(bar_w), bar_w * float(pct) / 100.0))
                    if fw >= 1.0:
                        fill_path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                            NSMakeRect(bar_x, bar_y, fw, BAR_H), r, r)
                        bar_fill.setFill()
                        fill_path.fill()
                except Exception:
                    pass

            # Prozent-Wert
            pct_str = f"{int(round(float(pct)))}%" if pct is not None else "—"
            _draw(pct_str, NSMakeRect(pct_x, text_y, PCT_W, ROW_H),
                  sec_font, NSColor.secondaryLabelColor())

            # Rechter Text (Reset-Zeit, Betrag)
            right = row.get("right") or ""
            if right:
                right_x = pct_x + PCT_W + 4
                _draw(right, NSMakeRect(right_x, text_y, max(0.0, total_w - right_x), ROW_H),
                      sec_font, NSColor.tertiaryLabelColor())


class TranscriptPanel(NSObject):
    """Floating NSPanel mit Buttons, Textfeld und Status-Anzeige."""

    @objc.python_method
    def setup(self):
        self.on_mic_click = None
        self.on_lang_toggle = None
        self.on_pin_toggle = None
        self.on_gain_change = None  # callback(new_gain: float)
        self.on_ocr_click = None
        self.on_copy_click = None
        self.on_insert_click = None
        self.on_clear_click = None
        self.on_text_edited = None
        self.on_train_add = None  # callback(wrong: str, right: str, context: str)
        self.on_usage_click = None
        self._programmatic_text_change = False
        self._train_context = ""  # Satz, in dem die markierte Stelle vorkam
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
        # Gespeicherte Fenstergroesse laden (Fallback: Defaults aus config)
        width, height = self._load_panel_size()
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, width, height),
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
        x = (screen.size.width - width) / 2
        y = (screen.size.height - height) / 2
        self.panel.setFrameOrigin_((x, y))

        content = self.panel.contentView()

        # --- Hilfsfunktion: glasiger Aktions-Button ---
        def _make_sf_button(title, symbol_name):
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 52))
            btn.setTitle_(title)
            btn.setBordered_(False)  # kein System-Bezel = kein doppelter Rahmen
            btn.setWantsLayer_(True)
            try:
                layer = btn.layer()
                layer.setBackgroundColor_(
                    NSColor.colorWithWhite_alpha_(1.0, 0.16).CGColor())
                layer.setCornerRadius_(10.0)
                layer.setBorderWidth_(0.6)
                layer.setBorderColor_(
                    NSColor.colorWithWhite_alpha_(1.0, 0.35).CGColor())
            except Exception:
                pass
            try:
                img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                    symbol_name, None)
                if img:
                    btn.setImage_(img)
                    btn.setImagePosition_(2)  # NSImageLeft
            except Exception:
                pass
            btn.setFont_(NSFont.systemFontOfSize_(11))
            try:
                btn.setImageHugsTitle_(True)  # Icon bleibt am Label, nicht am Rand
            except Exception:
                pass
            return btn

        # --- Alle Views erstellen (Frames werden von _relayout gesetzt) ---

        # Runde Hauptbuttons
        btn_size = 60
        self.mic_btn = MicButton.alloc().initWithFrame_(NSMakeRect(0, 0, btn_size, btn_size))
        self.mic_btn.setBordered_(False)
        self.mic_btn.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        self.mic_btn.setImage_(_make_circle_icon(btn_size, NSColor.systemBlueColor(), _draw_mic))
        self.mic_btn.setTarget_(self)
        self.mic_btn.setAction_("micClicked:")
        self.mic_btn.setToolTip_("Klick = Aufnahme starten/stoppen. F19 halten = Push-to-Talk.")
        content.addSubview_(self.mic_btn)

        self.mic_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 16))
        self.mic_label.setStringValue_("Mikrofon")
        self.mic_label.setEditable_(False); self.mic_label.setBezeled_(False)
        self.mic_label.setDrawsBackground_(False); self.mic_label.setAlignment_(1)
        self.mic_label.setFont_(NSFont.systemFontOfSize_(11))
        self.mic_label.setTextColor_(NSColor.labelColor())
        content.addSubview_(self.mic_label)

        self.mic_hint = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 160, 14))
        self.mic_hint.setStringValue_("F18 / F19 halten")
        self.mic_hint.setEditable_(False); self.mic_hint.setBezeled_(False)
        self.mic_hint.setDrawsBackground_(False); self.mic_hint.setAlignment_(1)
        self.mic_hint.setFont_(NSFont.systemFontOfSize_(10))
        self.mic_hint.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(self.mic_hint)

        self.ocr_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, btn_size, btn_size))
        self.ocr_btn.setBordered_(False)
        self.ocr_btn.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        self.ocr_btn.setImage_(_make_circle_icon(btn_size, NSColor.systemOrangeColor(), _draw_camera))
        self.ocr_btn.setTarget_(self)
        self.ocr_btn.setAction_("ocrClicked:")
        self.ocr_btn.setToolTip_("Screenshot + OCR (F17 / ⌘⇧O)")
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

        # Sprach-Toggle (DE/EN) — kleines Pill oben rechts
        self.lang_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 44, 22))
        self.lang_btn.setBezelStyle_(1)  # NSBezelStyleRounded
        self.lang_btn.setTitle_("DE")
        self.lang_btn.setFont_(NSFont.boldSystemFontOfSize_(11))
        self.lang_btn.setTarget_(self)
        self.lang_btn.setAction_("langClicked:")
        self.lang_btn.setToolTip_("Transkriptions-Sprache umschalten (DE/EN)")
        content.addSubview_(self.lang_btn)

        # Pin-Toggle (Floating-Modus an/aus) — links neben dem Sprach-Button
        self.pin_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 52, 22))
        self.pin_btn.setBezelStyle_(1)  # NSBezelStyleRounded
        self.pin_btn.setTitle_("Oben")
        self.pin_btn.setFont_(NSFont.boldSystemFontOfSize_(11))
        self.pin_btn.setTarget_(self)
        self.pin_btn.setAction_("pinClicked:")
        self.pin_btn.setToolTip_(
            "Vordergrund/Hintergrund umschalten: 'Oben' = Panel schwebt immer "
            "ueber anderen Apps, 'Frei' = normales Fensterverhalten")
        content.addSubview_(self.pin_btn)

        # VU-Meter (Pegel-Anzeige) zwischen Mic- und OCR-Button
        self.vu_meter = NSLevelIndicator.alloc().initWithFrame_(NSMakeRect(0, 0, 90, 14))
        self.vu_meter.setLevelIndicatorStyle_(1)  # NSLevelIndicatorStyleContinuousCapacity
        self.vu_meter.setMinValue_(0.0)
        self.vu_meter.setMaxValue_(1.0)
        self.vu_meter.setWarningValue_(0.7)
        self.vu_meter.setCriticalValue_(0.92)
        self.vu_meter.setDoubleValue_(0.0)
        self.vu_meter.setToolTip_("Mikrofon-Pegel (waehrend Aufnahme)")
        content.addSubview_(self.vu_meter)

        self.vu_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 90, 12))
        self.vu_label.setStringValue_("Pegel")
        self.vu_label.setEditable_(False); self.vu_label.setBezeled_(False)
        self.vu_label.setDrawsBackground_(False); self.vu_label.setAlignment_(1)
        self.vu_label.setFont_(NSFont.systemFontOfSize_(9))
        self.vu_label.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(self.vu_label)

        # Gain-Slider (0..10x Verstaerkung)
        self.gain_slider = NSSlider.alloc().initWithFrame_(NSMakeRect(0, 0, 90, 16))
        self.gain_slider.setMinValue_(0.0)
        self.gain_slider.setMaxValue_(10.0)
        self.gain_slider.setDoubleValue_(1.0)
        self.gain_slider.setTarget_(self)
        self.gain_slider.setAction_("gainChanged:")
        self.gain_slider.setContinuous_(True)
        self.gain_slider.setToolTip_("Mikrofon-Verstaerkung (1x = unveraendert)")
        content.addSubview_(self.gain_slider)

        self.gain_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 90, 12))
        self.gain_label.setStringValue_("Gain 1.0x")
        self.gain_label.setEditable_(False); self.gain_label.setBezeled_(False)
        self.gain_label.setDrawsBackground_(False); self.gain_label.setAlignment_(1)
        self.gain_label.setFont_(NSFont.systemFontOfSize_(9))
        self.gain_label.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(self.gain_label)

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

        # --- Inline-Training: falsch erkanntes Wort schnell korrigieren ---
        def _make_train_field(placeholder):
            f = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 24))
            f.setEditable_(True); f.setBezeled_(True)
            f.setFont_(NSFont.systemFontOfSize_(12))
            try:
                f.setPlaceholderString_(placeholder)
            except Exception:
                pass
            return f

        self.train_wrong = _make_train_field("Falsch erkannt (Wort/Wortgruppe markieren)")
        content.addSubview_(self.train_wrong)
        self.train_right = _make_train_field("Soll heißen")
        content.addSubview_(self.train_right)

        self.train_add_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(0, 0, 130, 26))
        self.train_add_btn.setTitle_("Hinzufügen")
        self.train_add_btn.setBezelStyle_(1)  # NSBezelStyleRounded
        self.train_add_btn.setTarget_(self)
        self.train_add_btn.setAction_("trainAddClicked:")
        content.addSubview_(self.train_add_btn)

        self.train_status = NSTextField.alloc().initWithFrame_(
            NSMakeRect(0, 0, 100, 22))
        self.train_status.setStringValue_("")
        self.train_status.setEditable_(False); self.train_status.setBezeled_(False)
        self.train_status.setDrawsBackground_(False); self.train_status.setSelectable_(False)
        self.train_status.setFont_(NSFont.systemFontOfSize_(11))
        self.train_status.setTextColor_(NSColor.tertiaryLabelColor())
        content.addSubview_(self.train_status)

        # Claude-Code-Usage-Panel (Balken-Ansicht, ueber dem Status-Label)
        self.usage_enabled = bool(CLAUDE_USAGE_MONITOR_ENABLED)
        self.usage_view = UsagePanelView.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 82))
        content.addSubview_(self.usage_view)
        if not self.usage_enabled:
            self.usage_view.setHidden_(True)

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
        gap = 110  # Platz fuer VU-Meter + Gain-Slider zwischen Mic und OCR

        # Untere Zone: Status + Usage-Panel + 3 Aktions-Buttons
        status_h = 28
        status_y = 10
        self.status_label.setFrame_(NSMakeRect(pad, status_y, inner_w, status_h))

        # Usage-Panel direkt ueber dem Status-Label
        if self.usage_enabled:
            usage_h = 82  # 5 Zeilen × (14px + 3px Gap) - letzte Gap
            usage_y = status_y + status_h + 4
            self.usage_view.setFrame_(NSMakeRect(pad, usage_y, inner_w, usage_h))
            usage_top_y = usage_y + usage_h + 6
        else:
            usage_top_y = status_y + status_h + 6

        btn_h = 52
        btn_area_y = usage_top_y
        btn_w = (inner_w - 20) // 3
        self.copy_btn.setFrame_(NSMakeRect(pad, btn_area_y, btn_w, btn_h))
        self.insert_btn.setFrame_(NSMakeRect(pad + btn_w + 10, btn_area_y, btn_w, btn_h))
        self.clear_btn.setFrame_(NSMakeRect(pad + 2 * (btn_w + 10), btn_area_y, btn_w, btn_h))

        # Obere Zone: Runde Buttons zentriert (nur Mic + OCR)
        lbl_h, hint_h = 16, 14
        top_block_h = btn_size + lbl_h + hint_h + 6
        top_y = h - top_block_h - 28
        total = 2 * btn_size + gap
        x_mic = (w - total) / 2
        x_ocr = x_mic + btn_size + gap
        lbl_w = btn_size + 80

        self.mic_btn.setFrame_(NSMakeRect(x_mic, top_y, btn_size, btn_size))
        self.mic_label.setFrame_(NSMakeRect(x_mic - 40, top_y - lbl_h - 2, lbl_w, lbl_h))
        self.mic_hint.setFrame_(NSMakeRect(x_mic - 40, top_y - lbl_h - hint_h - 4, lbl_w, hint_h))

        self.ocr_btn.setFrame_(NSMakeRect(x_ocr, top_y, btn_size, btn_size))
        self.ocr_label.setFrame_(NSMakeRect(x_ocr - 40, top_y - lbl_h - 2, lbl_w, lbl_h))
        self.ocr_hint.setFrame_(NSMakeRect(x_ocr - 40, top_y - lbl_h - hint_h - 4, lbl_w, hint_h))

        # Sprach-Toggle oben rechts in der Ecke
        lang_w, lang_h = 44, 22
        lang_x = w - pad - lang_w
        lang_y = h - lang_h - 10
        self.lang_btn.setFrame_(NSMakeRect(lang_x, lang_y, lang_w, lang_h))

        # Pin-Toggle (Floating/Frei) direkt links neben dem Sprach-Button
        pin_w = 52
        self.pin_btn.setFrame_(NSMakeRect(
            lang_x - pin_w - 6, lang_y, pin_w, lang_h))

        # VU-Block zwischen Mic und OCR — Slider-Knopf braucht volle Hoehe,
        # Slider sitzt etwas unterhalb der Button-Bodenkante, mit Abstand zum Label
        vu_w = 90
        vu_x = x_mic + btn_size + (gap - vu_w) / 2
        self.vu_label.setFrame_(NSMakeRect(vu_x, top_y + 50, vu_w, 10))
        self.vu_meter.setFrame_(NSMakeRect(vu_x, top_y + 36, vu_w, 12))
        self.gain_label.setFrame_(NSMakeRect(vu_x, top_y + 24, vu_w, 10))
        self.gain_slider.setFrame_(NSMakeRect(vu_x, top_y - 7, vu_w, 22))

        # Inline-Training-Sektion zwischen Action-Buttons und Scrollview
        train_h = 64
        train_y = btn_area_y + btn_h + 8
        field_h = 24
        fgap = 8
        fw = (inner_w - fgap) // 2
        row1_y = train_y + train_h - field_h  # obere Reihe: 2 Eingabefelder
        self.train_wrong.setFrame_(NSMakeRect(pad, row1_y, fw, field_h))
        self.train_right.setFrame_(NSMakeRect(pad + fw + fgap, row1_y, fw, field_h))
        add_w = 130  # untere Reihe: Hinzufügen + Status
        self.train_add_btn.setFrame_(NSMakeRect(pad, train_y, add_w, 26))
        self.train_status.setFrame_(
            NSMakeRect(pad + add_w + 10, train_y + 2, inner_w - add_w - 10, 22))

        # Mittlere Zone: Scrollview füllt den Rest
        scroll_top_y = train_y + train_h + 8
        round_bottom_y = top_y - lbl_h - hint_h - 8
        scroll_h = max(60, round_bottom_y - scroll_top_y)
        self.scroll_view.setFrame_(NSMakeRect(pad, scroll_top_y, inner_w, scroll_h))

    def windowDidResize_(self, notification):
        self._relayout()
        self._save_panel_size()

    def windowDidEndLiveResize_(self, notification):
        # Mancher Resize-Flow schickt nur DidEndLiveResize, nicht DidResize.
        # Doppelt speichern schadet nicht.
        self._save_panel_size()

    _PANEL_W_KEY = "panel_width"
    _PANEL_H_KEY = "panel_height"

    @objc.python_method
    def _load_panel_size(self):
        """Letzte Fenstergroesse aus NSUserDefaults; Fallback Defaults aus
        config. Plausibilitaets-Clamp gegen verbogene Prefs."""
        width, height = PANEL_WIDTH, PANEL_HEIGHT
        loaded_w, loaded_h = None, None
        try:
            d = NSUserDefaults.standardUserDefaults()
            w_obj = d.objectForKey_(self._PANEL_W_KEY)
            h_obj = d.objectForKey_(self._PANEL_H_KEY)
            if w_obj is not None:
                loaded_w = float(w_obj)
                width = loaded_w
            if h_obj is not None:
                loaded_h = float(h_obj)
                height = loaded_h
        except Exception:
            log.exception("Panel-Size laden fehlgeschlagen")
        # Vernuenftige Grenzen: nicht kleiner als Default, nicht groesser als 2000
        clamped_w = max(PANEL_WIDTH, min(2000.0, width))
        clamped_h = max(PANEL_HEIGHT, min(2000.0, height))
        log.info("Panel-Size geladen: stored=(%s,%s) -> verwendet=(%.0f,%.0f)",
                 loaded_w, loaded_h, clamped_w, clamped_h)
        return clamped_w, clamped_h

    @objc.python_method
    def _save_panel_size(self):
        try:
            frame = self.panel.frame()
            w = float(frame.size.width)
            h = float(frame.size.height)
            d = NSUserDefaults.standardUserDefaults()
            d.setDouble_forKey_(w, self._PANEL_W_KEY)
            d.setDouble_forKey_(h, self._PANEL_H_KEY)
            # Force-Sync auf Platte (theoretisch deprecated, schadet aber nie —
            # bei harten Restarts kann der Auto-Sync sonst verschluckt werden)
            try:
                d.synchronize()
            except Exception:
                pass
            log.info("Panel-Size gespeichert: %.0f x %.0f", w, h)
        except Exception:
            log.exception("Panel-Size speichern fehlgeschlagen")

    @objc.python_method
    def set_mic_icon(self, recording=False):
        if recording:
            self.mic_btn.setImage_(
                _make_circle_icon(60, NSColor.systemRedColor(), _draw_stop))
        else:
            self.mic_btn.setImage_(
                _make_circle_icon(60, NSColor.systemBlueColor(), _draw_mic))

    @objc.python_method
    def update_usage_rows(self, rows, warning_text=None):
        """Aktualisiert das Usage-Panel mit neuen Zeilen oder Warntext."""
        if not getattr(self, "usage_enabled", False):
            return
        try:
            self.usage_view.update_rows(rows, warning_text)
        except Exception:
            log.exception("update_usage_rows Fehler")

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

    def textViewDidChangeSelection_(self, notification):
        # Auswahl im Transkript automatisch ins "Falsch erkannt"-Feld übernehmen
        if self._programmatic_text_change:
            return
        tv = notification.object()
        rng = tv.selectedRange()
        if rng.length == 0 or rng.length > 80:  # leere Auswahl/ganze Absätze ignorieren
            return
        full = str(tv.string())
        sel = full[rng.location:rng.location + rng.length].strip()
        if sel and "\n" not in sel:
            self.train_wrong.setStringValue_(sel)
            self._train_context = self._sentence_around(
                full, rng.location, rng.location + rng.length)

    @objc.python_method
    def _sentence_around(self, text, start, end):
        """Den Satz extrahieren, in dem die Auswahl [start:end] liegt.
        Grenzen sind Satzzeichen (.!?) oder Zeilenumbrüche."""
        bounds = ".!?\n"
        left = 0
        for i in range(start - 1, -1, -1):
            if text[i] in bounds:
                left = i + 1
                break
        right = len(text)
        for i in range(end, len(text)):
            if text[i] in bounds:
                right = i + 1
                break
        return text[left:right].strip()

    @objc.IBAction
    def micClicked_(self, sender):
        if self.on_mic_click:
            self.on_mic_click()

    @objc.IBAction
    def langClicked_(self, sender):
        if self.on_lang_toggle:
            self.on_lang_toggle()

    @objc.IBAction
    def gainChanged_(self, sender):
        val = float(sender.doubleValue())
        try:
            self.gain_label.setStringValue_(f"Gain {val:.1f}x")
        except Exception:
            pass
        if self.on_gain_change:
            self.on_gain_change(val)

    @objc.python_method
    def set_vu_level(self, level: float):
        """VU-Meter auf neuen Pegel setzen (0..1)."""
        try:
            self.vu_meter.setDoubleValue_(max(0.0, min(1.0, level)))
        except Exception:
            pass

    @objc.python_method
    def set_gain(self, gain: float):
        """Slider + Label auf gespeicherten Gain-Wert setzen (ohne Callback)."""
        try:
            self.gain_slider.setDoubleValue_(gain)
            self.gain_label.setStringValue_(f"Gain {gain:.1f}x")
        except Exception:
            pass

    @objc.python_method
    def set_lang_label(self, lang: str):
        """UI-Beschriftung des Sprach-Buttons aktualisieren ('de' -> 'DE')."""
        try:
            self.lang_btn.setTitle_(lang.upper())
        except Exception:
            pass

    @objc.IBAction
    def pinClicked_(self, sender):
        if self.on_pin_toggle:
            self.on_pin_toggle()

    @objc.python_method
    def set_pin_label(self, floating: bool):
        """UI-Beschriftung: 'Oben' wenn floating aktiv, 'Frei' wenn normales
        Fensterverhalten."""
        try:
            self.pin_btn.setTitle_("Oben" if floating else "Frei")
        except Exception:
            pass

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

    @objc.IBAction
    def trainAddClicked_(self, sender):
        wrong = str(self.train_wrong.stringValue()).strip()
        right = str(self.train_right.stringValue()).strip()
        if not right:
            self._show_train_status("Bitte „Soll heißen“ ausfüllen", error=True)
            return
        if self.on_train_add:
            self.on_train_add(wrong, right, self._train_context)
        if wrong:
            msg = "✓ Gelernt: „%s“ → „%s“" % (wrong, right)
        else:
            msg = "✓ Begriff gelernt: „%s“" % right
        self.train_wrong.setStringValue_("")
        self.train_right.setStringValue_("")
        self._train_context = ""
        self._show_train_status(msg)

    @objc.python_method
    def _show_train_status(self, msg, error=False):
        """Kurzen Hinweis einblenden, der nach ein paar Sekunden verschwindet."""
        self.train_status.setStringValue_(msg)
        self.train_status.setTextColor_(
            NSColor.systemRedColor() if error else NSColor.systemGreenColor())
        NSObject.cancelPreviousPerformRequestsWithTarget_(self)
        self.performSelector_withObject_afterDelay_("clearTrainStatus:", None, 5.0)

    def clearTrainStatus_(self, _):
        self.train_status.setStringValue_("")
        self.train_status.setTextColor_(NSColor.tertiaryLabelColor())


class AppActivationObserver(NSObject):
    """Beobachtet App-Wechsel + System-Wake (Sleep/Display) und ruft einen
    Recovery-Callback, damit der Hotkey-Listener nach KVM-Switch / Wake
    wiederbelebt werden kann."""

    @objc.python_method
    def setup(self, own_bundle_id, on_wake=None):
        self._own_bundle_id = own_bundle_id
        self._last_external_app = None
        self._on_wake = on_wake
        ws = NSWorkspace.sharedWorkspace()
        nc = ws.notificationCenter()
        nc.addObserver_selector_name_object_(
            self, "appDidActivate:",
            NSWorkspaceDidActivateApplicationNotification, None)
        # System-Wake (Sleep-Wake) — manche KVMs triggern das mit
        nc.addObserver_selector_name_object_(
            self, "systemDidWake:",
            NSWorkspaceDidWakeNotification, None)
        # Display-Wake — wird bei KVM-Switch zurueck zuverlaessig gefeuert
        nc.addObserver_selector_name_object_(
            self, "systemDidWake:",
            NSWorkspaceScreensDidWakeNotification, None)
        # KVM-Switch loest *Screen-Parameter-Wechsel* aus (Display weg/wieder
        # da). Diese Notification kommt vom NSApp-NotificationCenter, nicht
        # von NSWorkspace.
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self, "systemDidWake:",
            NSApplicationDidChangeScreenParametersNotification, None)
        return self

    def appDidActivate_(self, notification):
        try:
            app = notification.userInfo()["NSWorkspaceApplicationKey"]
            bundle_id = app.bundleIdentifier()
            if bundle_id and bundle_id != self._own_bundle_id:
                self._last_external_app = app
        except Exception:
            pass

    def systemDidWake_(self, notification):
        try:
            name = notification.name() if hasattr(notification, "name") else "?"
            log.info("Wake-Notification empfangen: %s", name)
            if self._on_wake:
                self._on_wake()
        except Exception:
            log.exception("systemDidWake_ Fehler")

    @objc.python_method
    def last_external_app(self):
        return self._last_external_app


class TrainingPanel(NSObject):
    """Kleines Fenster zum Pflegen des Vokabulars (Begriffe + Korrekturen).

    Eintrag: "Soll heissen" (Pflicht, speist Prompt + Korrektur) und optional
    "Wird erkannt als" (Korrektur-Ausloeser). Aenderungen wirken sofort beim
    naechsten Chunk (vocabulary-Cache wird beim Speichern aktualisiert).
    """

    _W = 420
    _H = 470

    @objc.python_method
    def setup(self):
        self._entries = []
        self.table = None
        self._build()
        return self

    @objc.python_method
    def _build(self):
        from AppKit import NSTableView, NSTableColumn
        W, H, pad = self._W, self._H, 16
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskUtilityWindow
        )
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, H), style, NSBackingStoreBuffered, False)
        self.panel.setTitle_("Training — Begriffe & Korrekturen")
        self.panel.setReleasedWhenClosed_(False)
        self.panel.setLevel_(NSFloatingWindowLevel)
        try:
            from AppKit import NSAppearance
            self.panel.setAppearance_(
                NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua"))
        except Exception as e:
            log.warning("Training: Dark-Mode fehlgeschlagen: %s", e)

        content = self.panel.contentView()

        # Erklaerung
        info = self._make_label(
            "Begriffe, die die App sicher kennen soll. „Wird erkannt als“ "
            "ist optional — leer lassen, wenn der Begriff nur bekannt sein "
            "soll. Mit Inhalt: wird automatisch ersetzt.",
            NSMakeRect(pad, H - pad - 46, W - 2 * pad, 46),
            size=11, color=NSColor.secondaryLabelColor())
        info.cell().setWraps_(True)
        content.addSubview_(info)

        # Eingabezeile
        self.wrong_field = self._make_field(
            NSMakeRect(pad, 372, 184, 26), "Wird erkannt als (optional)")
        content.addSubview_(self.wrong_field)
        self.right_field = self._make_field(
            NSMakeRect(210, 372, 194, 26), "Soll heißen")
        content.addSubview_(self.right_field)

        add_btn = self._make_button(
            "Begriff hinzufügen", NSMakeRect(pad, 336, W - 2 * pad, 28),
            "addClicked:")
        content.addSubview_(add_btn)

        # Tabelle
        scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(pad, 58, W - 2 * pad, 270))
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(2)  # NSBezelBorder
        scroll.setAutohidesScrollers_(True)
        table = NSTableView.alloc().initWithFrame_(scroll.bounds())
        col_w = NSTableColumn.alloc().initWithIdentifier_("wrong")
        col_w.headerCell().setStringValue_("Wird erkannt als")
        col_w.setWidth_(100)
        col_r = NSTableColumn.alloc().initWithIdentifier_("right")
        col_r.headerCell().setStringValue_("Soll heißen")
        col_r.setWidth_(110)
        col_c = NSTableColumn.alloc().initWithIdentifier_("context")
        col_c.headerCell().setStringValue_("Kontext")
        col_c.setWidth_(165)
        table.addTableColumn_(col_w)
        table.addTableColumn_(col_r)
        table.addTableColumn_(col_c)
        table.setDataSource_(self)
        table.setDelegate_(self)
        table.setAllowsMultipleSelection_(False)
        table.setUsesAlternatingRowBackgroundColors_(True)
        scroll.setDocumentView_(table)
        content.addSubview_(scroll)
        self.table = table

        # Loeschen + Status
        del_btn = self._make_button(
            "Markierten löschen", NSMakeRect(pad, 16, 160, 30),
            "deleteClicked:")
        content.addSubview_(del_btn)
        self.status = self._make_label(
            "", NSMakeRect(186, 18, W - 186 - pad, 26),
            size=11, color=NSColor.tertiaryLabelColor())
        content.addSubview_(self.status)

    # --- UI-Helfer ---

    @objc.python_method
    def _make_field(self, frame, placeholder):
        f = NSTextField.alloc().initWithFrame_(frame)
        f.setEditable_(True)
        f.setBezeled_(True)
        f.setFont_(NSFont.systemFontOfSize_(12))
        try:
            f.setPlaceholderString_(placeholder)
        except Exception:
            pass
        return f

    @objc.python_method
    def _make_label(self, text, frame, size=11, color=None):
        lbl = NSTextField.alloc().initWithFrame_(frame)
        lbl.setStringValue_(text)
        lbl.setEditable_(False)
        lbl.setBezeled_(False)
        lbl.setDrawsBackground_(False)
        lbl.setSelectable_(False)
        lbl.setFont_(NSFont.systemFontOfSize_(size))
        if color is not None:
            lbl.setTextColor_(color)
        return lbl

    @objc.python_method
    def _make_button(self, title, frame, action):
        btn = NSButton.alloc().initWithFrame_(frame)
        btn.setTitle_(title)
        btn.setBezelStyle_(1)  # NSBezelStyleRounded
        btn.setTarget_(self)
        btn.setAction_(action)
        return btn

    @objc.python_method
    def _set_status(self, msg):
        if getattr(self, "status", None) is not None:
            self.status.setStringValue_(msg)

    @objc.python_method
    def _reload_entries(self):
        self._entries = vocabulary.entries()
        if self.table is not None:
            self.table.reloadData()

    @objc.python_method
    def open_panel(self):
        self._reload_entries()
        self._set_status("%d Begriffe gepflegt" % len(self._entries))
        self.panel.center()
        self.panel.makeKeyAndOrderFront_(None)
        self.panel.orderFrontRegardless()

    # --- NSTableView DataSource (als ObjC-Selektoren) ---

    def numberOfRowsInTableView_(self, tableView):
        return len(self._entries)

    def tableView_objectValueForTableColumn_row_(self, tableView, column, row):
        try:
            entry = self._entries[row]
        except IndexError:
            return ""
        ident = str(column.identifier())
        if ident == "wrong":
            return entry.get("wrong", "")
        if ident == "context":
            return entry.get("context", "")
        return entry.get("right", "")

    # --- Actions ---

    @objc.IBAction
    def addClicked_(self, sender):
        wrong = str(self.wrong_field.stringValue()).strip()
        right = str(self.right_field.stringValue()).strip()
        if not right:
            self._set_status("Bitte „Soll heißen“ ausfüllen")
            return
        vocabulary.add(wrong, right)
        self.wrong_field.setStringValue_("")
        self.right_field.setStringValue_("")
        self._reload_entries()
        self._set_status("Hinzugefügt: " + right)

    @objc.IBAction
    def deleteClicked_(self, sender):
        row = self.table.selectedRow()
        if row is None or row < 0:
            self._set_status("Nichts ausgewählt")
            return
        try:
            entry = self._entries[row]
        except IndexError:
            return
        vocabulary.remove(entry.get("wrong", ""), entry.get("right", ""))
        self._reload_entries()
        self._set_status("Gelöscht")


class AudioTranskriptApp(rumps.App):
    """Menu-Bar-App mit Floating Panel."""

    def __init__(self):
        log.info("AudioTranskriptApp.__init__ startet")
        super().__init__(APP_NAME, icon=ICON_PATH, template=True)
        self.panel = TranscriptPanel.alloc().init().setup()
        self.training_panel = TrainingPanel.alloc().init().setup()
        self.recorder = Recorder()
        self.transcriber = Transcriber()
        self._text_was_edited = False
        self._target_app = None
        self.panel.on_mic_click = self._toggle_recording
        self.panel.on_lang_toggle = self._toggle_language
        self.panel.on_pin_toggle = self._toggle_floating
        self.panel.on_gain_change = self._set_gain
        self.panel.on_ocr_click = self._do_screenshot_ocr
        self._language = "de"  # Whisper-Sprache, per UI umschaltbar
        self.panel.set_lang_label(self._language)
        # Floating-Modus aus NSUserDefaults wiederherstellen (Default: True)
        self._restore_floating()
        self._vu_timer = None
        self._health_check_timer = None
        # Recovery-Schutz: Reentrant-Lock + Cooldown gegen Recovery-Spam
        # (KVM-Switch feuert mehrere Notifications + Watchdog gleichzeitig)
        self._recovery_lock = threading.Lock()
        self._last_recovery_at = 0.0
        # Letzten Gain-Wert aus NSUserDefaults wiederherstellen
        self._restore_gain()
        self.panel.on_copy_click = self._copy_text
        self.panel.on_insert_click = self._insert_panel_text
        self.panel.on_clear_click = self._clear_text
        self.panel.on_text_edited = self._on_text_edited
        self.panel.on_train_add = self._add_training_term
        self._recording_start = None
        self._recording_timer = None
        self._chunk_timer = None
        self._is_transcribing_chunk = False
        self._next_chunk_is_overlap = False
        self._last_chunk_text = ""
        self.menu = [
            rumps.MenuItem("Oeffnen/Schliessen",
                           callback=self._toggle_panel),
            rumps.MenuItem("Training…",
                           callback=self._open_training),
            rumps.MenuItem("Im Hintergrund",
                           callback=self._go_background),
            None,
            rumps.MenuItem("Neustart",
                           callback=self._restart),
            rumps.MenuItem("Beenden", callback=self._quit),
        ]

        self._app_observer = AppActivationObserver.alloc().init().setup(
            "com.matze.audio-transkript",
            on_wake=lambda: _on_main(self._recover_after_wake))

        # Hotkeys: F17/F18/Cmd+Shift+O via CGEventTap (Main-Thread); F19 via
        # eigenem CGEventTap. Frueher lief das ueber pynput — dessen Listener
        # fragte aus einem Hintergrund-Thread die Input-Source ab und crashte
        # auf neuem macOS (HIToolbox dispatch_assert_queue/main).
        self.hotkeys = HotkeyManager(
            on_mic_toggle=self._toggle_recording,
            on_ocr_trigger=self._do_screenshot_ocr,
        )
        self.hotkeys.start()

        self._f19_tap = F19EventTap(
            on_press=self._start_ptt_recording,
            on_release=self._stop_ptt_recording,
        )
        self._f19_tap.start()

        # Watchdog (10 s): falls Listener oder Tap nach KVM-Switch tot sind
        # und keine Notification kam, hier mitnehmen. 10 s ist die maximale
        # Wartezeit fuer den Nutzer, bevor F-Tasten wieder reagieren.
        self._watchdog_timer = rumps.Timer(self._watchdog_tick, 10)
        try:
            self._watchdog_timer.start()
        except Exception as e:
            log.warning("Watchdog-Timer konnte nicht gestartet werden: %s", e)

        log.info("Hotkeys, EventTap und Observer eingerichtet")

        # Claude-Code-Usage-Monitor: 60s-Refresh
        self._usage_timer = None
        if CLAUDE_USAGE_MONITOR_ENABLED:
            self._refresh_usage()
            try:
                self._usage_timer = rumps.Timer(self._refresh_usage_tick, 60)
                self._usage_timer.start()
            except Exception as e:
                log.warning("Usage-Timer konnte nicht gestartet werden: %s", e)

        self.panel.mic_btn.setEnabled_(False)
        self.transcriber.load_model(
            on_progress=lambda msg: _on_main(
                lambda: self.panel.set_status(msg)),
            on_done=lambda: _on_main(self._on_model_loaded),
        )

    def _toggle_panel(self, _):
        self.panel.toggle()

    def _open_training(self, _):
        """Training-Fenster oeffnen (Vokabular pflegen)."""
        self.training_panel.open_panel()

    def _go_background(self, _):
        """Panel schliessen, App laeuft im Hintergrund weiter."""
        self.panel.hide()
        self.panel.set_status("Im Hintergrund (F18/F19 aktiv)")
        log.info("Hintergrund-Modus aktiviert")

    def _check_stream_health(self, _):
        """Wird 500 ms nach Aufnahme-Start einmalig gefeuert. Wenn der
        sounddevice-Stream bis dahin 0 Frames geliefert hat, ist er ein
        Zombie (typisch nach KVM-Switch) — Recovery + Status anzeigen."""
        try:
            if self._health_check_timer:
                self._health_check_timer.stop()
                self._health_check_timer = None
        except Exception:
            pass
        try:
            if not self.recorder.is_recording:
                return
            frames = self.recorder.get_frames_received()
            log.info("Stream-Health-Check: %d Frames nach 500ms", frames)
            if frames == 0:
                log.warning("Stream tot (0 Frames) -> Audio-Recovery")
                try:
                    self._stop_recording()
                except Exception:
                    log.exception("Health-Check: stop_recording schlug fehl")
                try:
                    self.recorder.reinit_devices()
                except Exception:
                    log.exception("Health-Check: reinit_devices schlug fehl")
                self.panel.set_status(
                    "Mikrofon zuruecksetzen — bitte erneut versuchen",
                    kind="recording")
        except Exception:
            log.exception("Stream-Health-Check Fehler")

    # --- Recovery nach Sleep/Wake/KVM-Switch ---

    def _cleanup_recording_ui(self):
        """Setzt UI-Timer + Mic-Icon zurueck OHNE Final-Transkription
        anzustossen. Wird in der Recovery genutzt, weil die laufende
        Aufnahme nach KVM-Switch eh kaputt ist."""
        for attr in ("_chunk_timer", "_vu_timer", "_recording_timer",
                     "_health_check_timer"):
            t = getattr(self, attr, None)
            if t is not None:
                try:
                    t.stop()
                except Exception:
                    pass
                setattr(self, attr, None)
        self._is_transcribing_chunk = False
        try:
            self.panel.set_vu_level(0.0)
            self.panel.set_mic_icon(recording=False)
        except Exception:
            pass

    def _recover_after_wake(self):
        """Hotkey-Listener, F19-EventTap UND sounddevice nach KVM-Switch / Wake
        wieder fit machen. Geschuetzt durch Reentrant-Lock + 5s-Cooldown —
        sonst feuern wir bei einem KVM-Switch 3-5x parallel und reissen
        PortAudio in einen Zustand aus dem auch ein Process-Neustart nicht
        mehr rauskommt."""
        if not self._recovery_lock.acquire(blocking=False):
            log.info("Recovery: laeuft bereits, skip")
            return
        try:
            now = _time.time()
            if now - self._last_recovery_at < 5.0:
                log.info("Recovery: Cooldown aktiv, skip "
                         "(letzte vor %.1fs)", now - self._last_recovery_at)
                return
            self._last_recovery_at = now
            log.info("Recovery: Hotkeys + F19-Tap + sounddevice neu starten")
            # Laufende Aufnahme HART abreissen — KEIN _stop_recording, weil
            # das einen Transcribe-Thread startet, der mit sd._terminate
            # kollidieren wuerde
            if self.recorder.is_recording:
                log.info("Recovery: laufende Aufnahme abbrechen (hard)")
                try:
                    self.recorder._force_close_stream()
                except Exception:
                    log.exception("Recovery: _force_close_stream schlug fehl")
                self.recorder.is_recording = False
                self._cleanup_recording_ui()
            # sounddevice-Geraeteliste refreshen
            try:
                self.recorder.reinit_devices()
            except Exception:
                log.exception("Recovery: sounddevice-Reinit schlug fehl")
            # Pynput-Listener neu
            try:
                self.hotkeys.stop()
            except Exception:
                pass
            self.hotkeys.start()
            # F19-Tap neu (mit Mach-Port-Invalidate im stop)
            try:
                self._f19_tap.stop()
            except Exception:
                pass
            self._f19_tap.start()
            try:
                self.panel.set_status("Bereit (nach KVM-Switch)")
            except Exception:
                pass
        except Exception:
            log.exception("Recovery fehlgeschlagen")
        finally:
            self._recovery_lock.release()

    def _watchdog_tick(self, _):
        """Periodischer Health-Check als Sicherheitsnetz. Nur wenn KEINE
        Aufnahme laeuft — sonst wuerden wir mit dem Stream-Health-Check
        kollidieren oder eine gesunde Aufnahme abreissen."""
        try:
            if self.recorder.is_recording:
                return
            listener_dead = not self.hotkeys.is_listener_alive()
            tap_dead = not self._f19_tap.is_alive()
            if listener_dead or tap_dead:
                log.warning(
                    "Watchdog: listener_dead=%s tap_dead=%s -> Recovery",
                    listener_dead, tap_dead)
                self._recover_after_wake()
        except Exception:
            log.exception("Watchdog-Tick Fehler")

    def _teardown_for_exit(self):
        """Alle Subsysteme sauber herunterfahren — gemeinsam fuer Quit + Restart.
        Wichtig: F19-Tap mit Mach-Port-Invalidate (siehe f19_tap.stop), und
        PortAudio kontrolliert terminieren, damit der naechste Process
        sauber starten kann."""
        for attr in ("_watchdog_timer", "_health_check_timer", "_vu_timer",
                     "_chunk_timer", "_recording_timer", "_usage_timer"):
            t = getattr(self, attr, None)
            if t is not None:
                try:
                    t.stop()
                except Exception:
                    pass
                setattr(self, attr, None)
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        try:
            self._f19_tap.stop()
        except Exception:
            pass
        try:
            self.recorder._force_close_stream()
            self.recorder.is_recording = False
        except Exception:
            pass
        try:
            import sounddevice as sd
            sd._terminate()
        except Exception:
            pass
        # PortAudio Zeit geben, das Device freizugeben
        _time.sleep(0.2)

    @staticmethod
    def _detect_app_bundle_path():
        """Wenn die App aus einem .app-Bundle laeuft, gib dessen Pfad zurueck;
        sonst None (= Dev-Modus aus Source)."""
        try:
            from Foundation import NSBundle
            path = str(NSBundle.mainBundle().bundlePath() or "")
            if path.endswith(".app") and os.path.isdir(path):
                return path
        except Exception:
            pass
        return None

    def _restart(self, _):
        """App komplett neu starten. Im .app-Bundle via 'open' (sonst fehlt
        nach execv die LaunchServices-Integration und das Menuleisten-Icon
        verschwindet sofort wieder). Im Dev-Modus per os.execv."""
        log.info("Neustart angefordert")
        self._teardown_for_exit()
        bundle = self._detect_app_bundle_path()
        if bundle:
            log.info("Restart via 'open %s'", bundle)
            import subprocess
            try:
                # sleep 1: alter Prozess muss wirklich weg sein, sonst
                # macht macOS-Single-Instance keinen neuen Process auf
                subprocess.Popen(
                    ['/bin/sh', '-c', f'sleep 1 && open "{bundle}"'])
            except Exception:
                log.exception("subprocess.Popen('open ...') schlug fehl")
            rumps.quit_application()
            return
        log.info("Restart via os.execv (Dev-Modus)")
        import sys
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception:
            log.exception("os.execv fehlgeschlagen")
            rumps.quit_application()

    def _quit(self, _):
        log.info("Beenden angefordert")
        self._teardown_for_exit()
        rumps.quit_application()

    @rumps.clicked(APP_NAME)
    def on_icon_click(self, _):
        self.panel.toggle()

    def _on_text_edited(self):
        self._text_was_edited = True

    @objc.python_method
    def _add_training_term(self, wrong, right, context=""):
        """Inline-Training: Begriff in den Vokabular-Speicher uebernehmen."""
        vocabulary.add(wrong, right, context)
        # Falls separates Training-Fenster offen ist, Liste aktualisieren
        try:
            if self.training_panel.panel.isVisible():
                self.training_panel._reload_entries()
        except Exception:
            pass

    # --- Claude-Code-Usage ---

    def _refresh_usage_tick(self, _):
        self._refresh_usage()

    def _refresh_usage(self):
        """Holt Usage-Daten im Hintergrund und aktualisiert das Panel."""
        def _run():
            try:
                data = claude_usage.fetch_usage()
                _on_main(lambda: self._apply_usage(data))
            except Exception as e:
                log.exception("Usage-Refresh Fehler: %s", e)
        threading.Thread(target=_run, daemon=True).start()

    def _apply_usage(self, data):
        if not data or not data.get("ok"):
            detail = (data or {}).get("detail", "Nutzungsdaten nicht verfuegbar.")
            self.panel.update_usage_rows([], f"⚠ {detail}")
            return

        def safe_pct(block):
            v = (block or {}).get("pct")
            try:
                return float(v) if v is not None else None
            except Exception:
                return None

        sess = data.get("session") or {}
        wk_all = data.get("week_all") or {}
        wk_son = data.get("week_sonnet") or {}
        wk_ome = data.get("week_omelette") or {}
        extra = data.get("extra") or {}

        rows = [
            {
                "label": "Aktuelle Sitzung",
                "pct": safe_pct(sess),
                "right": f"Reset {claude_usage.format_reset(sess.get('reset'))}",
            },
            {
                "label": "Alle Modelle",
                "pct": safe_pct(wk_all),
                "right": f"Reset {claude_usage.format_reset(wk_all.get('reset'))}",
            },
            {
                "label": "Nur Sonnet",
                "pct": safe_pct(wk_son),
                "right": "",
            },
            {
                "label": "Claude Code",
                "pct": safe_pct(wk_ome),
                "right": "",
            },
        ]

        if extra.get("enabled"):
            used = extra.get("used_credits")
            limit = extra.get("monthly_limit")
            cur = extra.get("currency") or ""
            sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(cur, cur)
            right = ""
            if used is not None and limit is not None:
                try:
                    # API liefert Cent-Werte — durch 100 dividieren
                    used_e = float(used) / 100.0
                    limit_e = float(limit) / 100.0
                    right = (f"{used_e:.2f} {sym} / {int(limit_e)} {sym}"
                             .replace(".", ","))
                except Exception:
                    pass
            rows.append({
                "label": "Zusatznutzung",
                "pct": extra.get("pct"),
                "right": right,
            })

        self.panel.update_usage_rows(rows, None)

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
        # Leer-Text-Schutz: sonst loest ein Cmd+V aus, das den alten
        # Clipboard-Inhalt einfuegt.
        if not text or not text.strip():
            return
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

    # --- Mikrofon-Gain + VU-Meter ---

    _GAIN_PREF_KEY = "mic_gain"

    def _restore_gain(self):
        """Letzten Gain-Wert laden und auf Recorder + UI anwenden."""
        try:
            defaults = NSUserDefaults.standardUserDefaults()
            stored = defaults.objectForKey_(self._GAIN_PREF_KEY)
            gain = float(stored) if stored is not None else 1.0
        except Exception:
            gain = 1.0
        # Plausibilitaet (falls jemand den Pref manuell verbiegt)
        gain = max(0.0, min(10.0, gain))
        self.recorder.gain = gain
        self.panel.set_gain(gain)
        log.info("Mic-Gain wiederhergestellt: %.2fx", gain)

    def _set_gain(self, value: float):
        self.recorder.gain = float(value)
        try:
            NSUserDefaults.standardUserDefaults().setDouble_forKey_(
                float(value), self._GAIN_PREF_KEY)
        except Exception:
            log.exception("Konnte Gain nicht speichern")
        log.info("Mic-Gain gesetzt: %.2fx", value)

    def _vu_tick(self, _):
        try:
            level = self.recorder.get_level() if self.recorder.is_recording else 0.0
            self.panel.set_vu_level(level)
        except Exception:
            pass

    # --- Sprach-Toggle (DE/EN) ---

    def _toggle_language(self):
        self._language = "en" if self._language == "de" else "de"
        self.panel.set_lang_label(self._language)
        log.info("Sprache umgeschaltet auf: %s", self._language)
        self.panel.set_status(
            f"Sprache: {self._language.upper()}")

    # --- Floating-Toggle (Panel im Vordergrund oder normales Fenster) ---

    _FLOATING_PREF_KEY = "panel_floating"

    def _restore_floating(self):
        """Letzten Floating-State aus NSUserDefaults laden (Default: True)."""
        try:
            d = NSUserDefaults.standardUserDefaults()
            stored = d.objectForKey_(self._FLOATING_PREF_KEY)
            self._floating = True if stored is None else bool(int(stored))
        except Exception:
            self._floating = True
        self._apply_floating()
        log.info("Floating-Modus wiederhergestellt: %s", self._floating)

    def _toggle_floating(self):
        self._floating = not self._floating
        self._apply_floating()
        try:
            NSUserDefaults.standardUserDefaults().setInteger_forKey_(
                1 if self._floating else 0, self._FLOATING_PREF_KEY)
        except Exception:
            log.exception("Floating-State konnte nicht gespeichert werden")
        log.info("Floating umgeschaltet: %s", self._floating)
        self.panel.set_status(
            "Immer im Vordergrund" if self._floating
            else "Normales Fenster (kann in den Hintergrund)")

    def _apply_floating(self):
        """Setzt Window-Level + Button-Label entsprechend self._floating."""
        try:
            self.panel.panel.setLevel_(
                NSFloatingWindowLevel if self._floating else NSNormalWindowLevel)
        except Exception:
            log.exception("Window-Level konnte nicht gesetzt werden")
        try:
            self.panel.set_pin_label(self._floating)
        except Exception:
            pass

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
        if not self.recorder.start():
            log.error("Audio-Aufnahme konnte nicht gestartet werden")
            self.panel.set_status(
                "Mikrofon nicht verfuegbar", kind="recording")
            return
        self._recording_start = _time.time()
        # Health-Check: prueft 500 ms nach Start, ob wirklich Samples
        # ankommen. Falls nicht (Zombie-Stream nach KVM-Switch), Recovery.
        self._health_check_timer = rumps.Timer(
            self._check_stream_health, 0.5)
        self._health_check_timer.start()
        self.panel.set_mic_icon(recording=True)
        self.panel.set_status("Aufnahme laeuft...", kind="recording")
        self._recording_timer = rumps.Timer(
            self._update_recording_time, 1)
        self._recording_timer.start()
        self._next_chunk_is_overlap = False
        self._last_chunk_text = ""
        # 1-Sekunden-Tick: entscheidet dynamisch, wann ein Chunk geschnitten wird
        self._chunk_timer = rumps.Timer(self._transcribe_chunk, 1)
        self._chunk_timer.start()
        # VU-Meter-Tick (10x pro Sekunde) — nur waehrend Aufnahme aktiv
        self._vu_timer = rumps.Timer(self._vu_tick, 0.1)
        self._vu_timer.start()

    def _stop_recording(self):
        """Aufnahme stoppen (gemeinsam fuer Toggle und PTT)."""
        if not self.recorder.is_recording:
            return
        if self._chunk_timer:
            self._chunk_timer.stop()
            self._chunk_timer = None
        if self._vu_timer:
            self._vu_timer.stop()
            self._vu_timer = None
        if self._health_check_timer:
            try:
                self._health_check_timer.stop()
            except Exception:
                pass
            self._health_check_timer = None
        self.panel.set_vu_level(0.0)
        self._is_transcribing_chunk = False
        if self._recording_timer:
            self._recording_timer.stop()
            self._recording_timer = None
        self.panel.set_mic_icon(recording=False)
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
            min_len = SAMPLE_RATE // 2  # 0.5 s — kurze Sequenzen werden nicht verworfen
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
                    text, lang = self.transcriber.transcribe(
                        audio, prev_text=prev_text, language=self._language)

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
                text, lang = self.transcriber.transcribe(
                    audio, prev_text=self._last_chunk_text,
                    language=self._language)
                log.info("final: %r (lang=%s)", text[:60] if text else '', lang)
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
