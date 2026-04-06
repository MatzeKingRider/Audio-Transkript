# Panel-Textanzeige mit Bearbeitung und Zwischenablage

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transkriptions- und OCR-Ergebnisse in einem editierbaren Textfeld im Panel anzeigen, dort bearbeiten und in die Zwischenablage kopieren oder ins aktive Eingabefeld einfügen.

**Architecture:** Das Panel wird vergrößert und erhält ein scrollbares NSTextView als zentrales Textfeld. Unter dem Textfeld kommen zwei Aktions-Buttons: "Kopieren" (Zwischenablage) und "Einfügen" (ins aktive Feld). Das bisherige Status-Label bleibt als einzeilige Statusleiste erhalten. Bei Mikrofon-Aufnahme wird alle 3 Sekunden ein Zwischen-Transkript erzeugt und live im Textfeld angezeigt. Nach Aufnahme-Stopp erfolgt ein finales Transkript des gesamten Audios. Der gleiche Textfeld-Workflow gilt für Screenshot-OCR.

**Tech Stack:** Python, PyObjC (NSTextView, NSScrollView), mlx-whisper (chunked transcription), macOS Vision API

---

## Design-Entscheidungen und Vorschläge

### Live-Text während der Aufnahme

**Empfehlung: Chunked Transcription (alle 3 Sekunden)**

Während der Aufnahme wird alle 3 Sekunden der bis dahin aufgenommene Audio-Puffer an Whisper geschickt. Das Zwischen-Ergebnis wird im Textfeld angezeigt und bei jedem neuen Chunk aktualisiert. Nach Stopp wird das gesamte Audio noch einmal final transkribiert — das liefert das beste Ergebnis, weil Whisper mit mehr Kontext genauer arbeitet.

Alternativen die verworfen wurden:
- **Apple SFSpeechRecognizer**: Echtzeit-Streaming, aber deutlich schlechtere Genauigkeit als Whisper large-v3, besonders bei Deutsch. Würde zwei Speech-Engines parallel erfordern.
- **Wort-für-Wort Streaming**: mlx-whisper unterstützt kein Token-Streaming. Müsste man selbst implementieren — zu komplex für den Nutzen.

### Panel-Layout (neu: 420x400)

```
┌──────────────────────────────────────────┐
│  Audio Transkript                    [x] │
├──────────────────────────────────────────┤
│  [Mikrofon]              [Screenshot]    │
├──────────────────────────────────────────┤
│  ┌──────────────────────────────────────┐│
│  │                                      ││
│  │  Editierbares Textfeld (NSTextView)  ││
│  │  mit Scrollbar                       ││
│  │                                      ││
│  │                                      ││
│  └──────────────────────────────────────┘│
├──────────────────────────────────────────┤
│  [Kopieren]              [Einfügen]      │
├──────────────────────────────────────────┤
│  Statuszeile: "Bereit"                   │
└──────────────────────────────────────────┘
```

### Workflow-Änderung

**Bisher:** Aufnahme → Transkription → Auto-Einfügen in aktives Feld
**Neu:** Aufnahme (mit Live-Preview) → Finales Transkript im Textfeld → Nutzer kann bearbeiten → Manuell "Kopieren" oder "Einfügen" klicken

Das gibt dem Nutzer Kontrolle über den Text bevor er irgendwo eingefügt wird.

---

## Dateistruktur

| Datei | Aktion | Verantwortung |
|-------|--------|---------------|
| `src/config.py` | Ändern | Panel-Größe anpassen |
| `src/app.py` | Ändern | Panel-UI: NSTextView, Kopieren/Einfügen-Buttons, Live-Update-Logik |
| `src/transcriber.py` | Ändern | Neue Methode `transcribe_chunked()` für Zwischen-Transkription |
| `src/recorder.py` | Ändern | Methode `get_audio_snapshot()` um aktuellen Puffer ohne Stopp zu lesen |

Keine Änderungen an: `src/ocr.py`, `src/text_input.py`, `src/hotkeys.py`

---

### Task 1: Panel-Größe und Konstanten aktualisieren

**Files:**
- Modify: `src/config.py`

- [ ] **Step 1: Panel-Konstanten anpassen**

```python
# In src/config.py — PANEL_HEIGHT und PANEL_WIDTH ändern:

PANEL_WIDTH = 420
PANEL_HEIGHT = 400
```

- [ ] **Step 2: App starten und prüfen dass das Fenster größer ist**

Run: `cd /Users/matze/Entwicklung/Audio-Transkript && python -m src`
Expected: Panel öffnet sich größer (420x400), Buttons und Status-Label sind noch da (Layout wird in Task 2 angepasst)

- [ ] **Step 3: Commit**

```bash
git add src/config.py
git commit -m "feat: Panel-Größe auf 420x400 für Textfeld vergrößern"
```

---

### Task 2: Editierbares Textfeld und Aktions-Buttons ins Panel einbauen

**Files:**
- Modify: `src/app.py`

- [ ] **Step 1: NSTextView-Imports ergänzen**

Am Anfang von `app.py`, zu den AppKit-Imports hinzufügen:

```python
from AppKit import (
    NSApplication,
    NSObject,
    NSPanel,
    NSView,
    NSButton,
    NSTextField,
    NSTextView,
    NSScrollView,
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
    NSPasteboard,
    NSPasteboardTypeString,
)
```

- [ ] **Step 2: _build_panel-Methode komplett ersetzen**

Die gesamte `_build_panel`-Methode in `TranscriptPanel` ersetzen:

```python
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

    # --- Obere Zeile: Mikrofon + Screenshot Buttons (y=350) ---
    self.mic_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(20, PANEL_HEIGHT - 60, 180, 40)
    )
    self.mic_btn.setTitle_("Mikrofon")
    self.mic_btn.setBezelStyle_(NSBezelStyleRounded)
    self.mic_btn.setTarget_(self)
    self.mic_btn.setAction_("micClicked:")
    content.addSubview_(self.mic_btn)

    self.ocr_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(220, PANEL_HEIGHT - 60, 180, 40)
    )
    self.ocr_btn.setTitle_("Screenshot")
    self.ocr_btn.setBezelStyle_(NSBezelStyleRounded)
    self.ocr_btn.setTarget_(self)
    self.ocr_btn.setAction_("ocrClicked:")
    content.addSubview_(self.ocr_btn)

    # --- Textfeld mit Scrollbar (Mitte) ---
    scroll_frame = NSMakeRect(20, 90, PANEL_WIDTH - 40, PANEL_HEIGHT - 160)
    self.scroll_view = NSScrollView.alloc().initWithFrame_(scroll_frame)
    self.scroll_view.setHasVerticalScroller_(True)
    self.scroll_view.setBorderType_(1)  # NSBezelBorder

    text_frame = NSMakeRect(0, 0, scroll_frame.size.width, scroll_frame.size.height)
    self.text_view = NSTextView.alloc().initWithFrame_(text_frame)
    self.text_view.setEditable_(True)
    self.text_view.setSelectable_(True)
    self.text_view.setRichText_(False)
    self.text_view.setFont_(NSFont.systemFontOfSize_(14))
    self.text_view.setAutoresizingMask_(1)  # NSViewWidthSizable
    self.text_view.textContainer().setWidthTracksTextView_(True)

    self.scroll_view.setDocumentView_(self.text_view)
    content.addSubview_(self.scroll_view)

    # --- Untere Zeile: Kopieren + Einfügen Buttons (y=45) ---
    self.copy_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(20, 45, 180, 35)
    )
    self.copy_btn.setTitle_("Kopieren")
    self.copy_btn.setBezelStyle_(NSBezelStyleRounded)
    self.copy_btn.setTarget_(self)
    self.copy_btn.setAction_("copyClicked:")
    content.addSubview_(self.copy_btn)

    self.insert_btn = NSButton.alloc().initWithFrame_(
        NSMakeRect(220, 45, 180, 35)
    )
    self.insert_btn.setTitle_("Einfügen")
    self.insert_btn.setBezelStyle_(NSBezelStyleRounded)
    self.insert_btn.setTarget_(self)
    self.insert_btn.setAction_("insertClicked:")
    content.addSubview_(self.insert_btn)

    # --- Status-Label (unterste Zeile) ---
    self.status_label = NSTextField.alloc().initWithFrame_(
        NSMakeRect(20, 10, PANEL_WIDTH - 40, 25)
    )
    self.status_label.setStringValue_("Bereit")
    self.status_label.setEditable_(False)
    self.status_label.setBezeled_(False)
    self.status_label.setDrawsBackground_(False)
    self.status_label.setFont_(NSFont.systemFontOfSize_(12))
    self.status_label.setTextColor_(NSColor.secondaryLabelColor())
    content.addSubview_(self.status_label)
```

- [ ] **Step 3: Neue Callback-Properties und Button-Handler hinzufügen**

In der `setup`-Methode ergänzen:

```python
@objc.python_method
def setup(self):
    self.on_mic_click = None
    self.on_ocr_click = None
    self.on_copy_click = None
    self.on_insert_click = None
    self._build_panel()
    return self
```

Neue IBAction-Methoden zur `TranscriptPanel`-Klasse hinzufügen:

```python
@objc.IBAction
def copyClicked_(self, sender):
    if self.on_copy_click:
        self.on_copy_click()

@objc.IBAction
def insertClicked_(self, sender):
    if self.on_insert_click:
        self.on_insert_click()
```

- [ ] **Step 4: Neue Hilfsmethoden für das Textfeld**

Zur `TranscriptPanel`-Klasse hinzufügen:

```python
@objc.python_method
def set_text(self, text):
    """Text im editierbaren Textfeld setzen."""
    self.text_view.setString_(text)

@objc.python_method
def get_text(self):
    """Aktuellen Text aus dem Textfeld lesen."""
    return str(self.text_view.string())

@objc.python_method
def append_text(self, text):
    """Text ans Ende des Textfelds anhängen."""
    current = str(self.text_view.string())
    if current:
        self.text_view.setString_(current + text)
    else:
        self.text_view.setString_(text)
    # Ans Ende scrollen
    length = self.text_view.string().length()
    self.text_view.scrollRangeToVisible_((length, 0))
```

- [ ] **Step 5: App starten und prüfen**

Run: `cd /Users/matze/Entwicklung/Audio-Transkript && python -m src`
Expected: Panel zeigt Mikrofon/Screenshot-Buttons oben, Textfeld in der Mitte, Kopieren/Einfügen-Buttons unten, Statuszeile ganz unten. Textfeld ist editierbar.

- [ ] **Step 6: Commit**

```bash
git add src/app.py
git commit -m "feat: editierbares Textfeld und Kopieren/Einfügen-Buttons ins Panel"
```

---

### Task 3: Kopieren- und Einfügen-Logik in der App verdrahten

**Files:**
- Modify: `src/app.py`

- [ ] **Step 1: Callbacks im AudioTranskriptApp-Konstruktor verbinden**

In `AudioTranskriptApp.__init__`, nach den bestehenden Callback-Zuweisungen:

```python
self.panel.on_copy_click = self._copy_text
self.panel.on_insert_click = self._insert_panel_text
```

- [ ] **Step 2: Kopieren-Methode implementieren**

Neue Methode in `AudioTranskriptApp`:

```python
def _copy_text(self):
    """Text aus dem Panel in die Zwischenablage kopieren."""
    text = self.panel.get_text()
    if not text.strip():
        self.panel.set_status("Kein Text zum Kopieren")
        return
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)
    self.panel.set_status("In Zwischenablage kopiert")
```

- [ ] **Step 3: Einfügen-Methode implementieren**

Neue Methode in `AudioTranskriptApp`:

```python
def _insert_panel_text(self):
    """Text aus dem Panel ins aktive Eingabefeld einfügen."""
    text = self.panel.get_text()
    if not text.strip():
        self.panel.set_status("Kein Text zum Einfügen")
        return
    if self._previous_app:
        activate_app(self._previous_app)
        _time.sleep(0.15)
    type_text(text)
    self.panel.set_status("Text eingefügt")
```

- [ ] **Step 4: Bisherige _insert_text_or_clipboard und _insert_text entfernen**

Die Methoden `_insert_text_or_clipboard` und `_insert_text` entfernen. Sie werden nicht mehr gebraucht, da der Nutzer jetzt manuell Kopieren/Einfügen wählt.

- [ ] **Step 5: _on_transcription_done und _on_ocr_done anpassen**

Die Callback-Methoden so ändern, dass sie nur den Text ins Textfeld setzen (kein Auto-Einfügen mehr):

```python
def _on_transcription_done(self, text):
    if text:
        self.panel.set_text(text)
        self.panel.set_status("Transkription abgeschlossen — Text kann bearbeitet werden")
    else:
        self.panel.set_status("Kein Text erkannt")

def _on_ocr_done(self, text):
    if text:
        self.panel.set_text(text)
        self.panel.set_status("OCR abgeschlossen — Text kann bearbeitet werden")
    else:
        self.panel.set_status("Kein Text erkannt")
```

- [ ] **Step 6: NSPasteboard-Import aus app.py aufräumen**

Den lokalen Import `from AppKit import NSPasteboard, NSPasteboardTypeString` in `_insert_text_or_clipboard` entfernen (Methode wird gelöscht). Die Imports sind jetzt oben in der Datei.

- [ ] **Step 7: App starten und Workflow testen**

Run: `cd /Users/matze/Entwicklung/Audio-Transkript && python -m src`
Test:
1. Screenshot aufnehmen → OCR-Text erscheint im Textfeld
2. Text im Textfeld bearbeiten
3. "Kopieren" klicken → In Zwischenablage, in einem Editor Cmd+V testen
4. "Einfügen" klicken → Text wird ins aktive Feld eingefügt

- [ ] **Step 8: Commit**

```bash
git add src/app.py
git commit -m "feat: Kopieren/Einfügen-Workflow statt Auto-Einfügen"
```

---

### Task 4: Audio-Snapshot aus dem Recorder ermöglichen

**Files:**
- Modify: `src/recorder.py`

- [ ] **Step 1: get_audio_snapshot-Methode hinzufügen**

Neue Methode in der `Recorder`-Klasse, nach `stop()`:

```python
def get_audio_snapshot(self):
    """Gibt den bisherigen Audio-Puffer zurück OHNE die Aufnahme zu stoppen."""
    if not self._chunks:
        return np.array([], dtype=np.float32)
    return np.concatenate(self._chunks, axis=0).flatten()
```

- [ ] **Step 2: Commit**

```bash
git add src/recorder.py
git commit -m "feat: Audio-Snapshot ohne Aufnahme-Stopp auslesen"
```

---

### Task 5: Live-Transkription während der Aufnahme

**Files:**
- Modify: `src/app.py`
- Modify: `src/transcriber.py`

- [ ] **Step 1: Transcriber um schnelle Zwischen-Transkription ergänzen**

Neue Methode in `Transcriber` (nach `transcribe()`):

```python
def transcribe_quick(self, audio):
    """Schnelle Zwischen-Transkription für Live-Preview.
    
    Nutzt dasselbe Modell, aber gibt bei sehr kurzem Audio leeren String zurück
    um unnötige Verarbeitung zu vermeiden.
    """
    if not self.model_loaded:
        return ""
    # Mindestens 1 Sekunde Audio für sinnvolles Ergebnis
    if len(audio) < SAMPLE_RATE:
        return ""
    result = mlx_whisper.transcribe(
        audio, path_or_hf_repo=WHISPER_MODEL, language=WHISPER_LANGUAGE
    )
    return result.get("text", "").strip()
```

- [ ] **Step 2: SAMPLE_RATE-Import in transcriber.py hinzufügen**

```python
from src.config import WHISPER_MODEL, WHISPER_LANGUAGE, SAMPLE_RATE
```

- [ ] **Step 3: Live-Transkriptions-Timer in app.py implementieren**

In `AudioTranskriptApp.__init__` eine neue Instanzvariable:

```python
self._live_transcription_timer = None
self._is_transcribing_chunk = False
```

- [ ] **Step 4: _toggle_recording anpassen für Live-Transkription**

Die `_toggle_recording`-Methode komplett ersetzen:

```python
def _toggle_recording(self):
    self._previous_app = get_frontmost_app()
    if self.recorder.is_recording:
        # --- Aufnahme stoppen ---
        if self._recording_timer:
            self._recording_timer.stop()
            self._recording_timer = None
        if self._live_transcription_timer:
            self._live_transcription_timer.stop()
            self._live_transcription_timer = None
        self._is_transcribing_chunk = False
        self.panel.mic_btn.setTitle_("Mikrofon")
        self.panel.set_status("Finale Transkription...")
        audio = self.recorder.stop()
        if len(audio) > 0:
            self._process_audio(audio)
        else:
            self.panel.set_status("Keine Aufnahme erkannt")
    else:
        # --- Aufnahme starten ---
        self.panel.set_text("")  # Textfeld leeren
        self.recorder.start()
        self._recording_start = _time.time()
        self.panel.mic_btn.setTitle_("Stopp")
        self.panel.set_status("Aufnahme läuft...")
        self._recording_timer = rumps.Timer(self._update_recording_time, 1)
        self._recording_timer.start()
        # Live-Transkription alle 3 Sekunden
        self._live_transcription_timer = rumps.Timer(self._transcribe_live_chunk, 3)
        self._live_transcription_timer.start()
```

- [ ] **Step 5: Live-Chunk-Transkription implementieren**

Neue Methode in `AudioTranskriptApp`:

```python
def _transcribe_live_chunk(self, _):
    """Alle 3 Sekunden den bisherigen Audio-Puffer transkribieren und im Textfeld anzeigen."""
    if not self.recorder.is_recording or self._is_transcribing_chunk:
        return
    audio = self.recorder.get_audio_snapshot()
    if len(audio) == 0:
        return
    self._is_transcribing_chunk = True

    def _run():
        text = self.transcriber.transcribe_quick(audio)
        def _update():
            self._is_transcribing_chunk = False
            if text and self.recorder.is_recording:
                self.panel.set_text(text)
        _on_main(_update)

    threading.Thread(target=_run, daemon=True).start()
```

- [ ] **Step 6: App starten und Live-Transkription testen**

Run: `cd /Users/matze/Entwicklung/Audio-Transkript && python -m src`
Test:
1. "Mikrofon" klicken und sprechen
2. Nach ca. 3-4 Sekunden erscheint erster Text im Textfeld
3. Weiter sprechen — Text wird alle 3 Sek. aktualisiert
4. "Stopp" klicken — finale Transkription ersetzt den Text
5. Text ist editierbar, Kopieren/Einfügen funktioniert

- [ ] **Step 7: Commit**

```bash
git add src/app.py src/transcriber.py
git commit -m "feat: Live-Transkription alle 3 Sekunden während Aufnahme"
```

---

### Task 6: Screenshot-OCR an neuen Workflow anpassen

**Files:**
- Modify: `src/app.py`

- [ ] **Step 1: _do_screenshot_ocr anpassen**

Die Methode so ändern, dass sie `_previous_app` vor dem Screenshot setzt und das Panel mit dem Ergebnis befüllt:

```python
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
```

Hinweis: Diese Methode ist identisch zum aktuellen Stand. Der Unterschied liegt in `_on_ocr_done` (bereits in Task 3 angepasst), die jetzt `set_text` statt Auto-Einfügen nutzt. Dieser Task ist eine Verifikation, dass alles zusammenpasst.

- [ ] **Step 2: Testen**

Run: `cd /Users/matze/Entwicklung/Audio-Transkript && python -m src`
Test:
1. "Screenshot" klicken
2. Bereich auswählen
3. OCR-Text erscheint im editierbaren Textfeld
4. Text bearbeiten, dann "Kopieren" oder "Einfügen" klicken

- [ ] **Step 3: Commit (falls Änderungen nötig waren)**

```bash
git add src/app.py
git commit -m "fix: Screenshot-OCR an neuen Textfeld-Workflow angepasst"
```

---

### Task 7: Textfeld per Tastaturkürzel leeren

**Files:**
- Modify: `src/app.py`

- [ ] **Step 1: Löschen-Button hinzufügen**

In `_build_panel`, einen kleinen "Leeren"-Button neben der Statuszeile einfügen. Die Statuszeile schmaler machen um Platz zu schaffen:

```python
# --- Status-Label (unterste Zeile, schmaler für Leeren-Button) ---
self.status_label = NSTextField.alloc().initWithFrame_(
    NSMakeRect(20, 10, PANEL_WIDTH - 120, 25)
)
self.status_label.setStringValue_("Bereit")
self.status_label.setEditable_(False)
self.status_label.setBezeled_(False)
self.status_label.setDrawsBackground_(False)
self.status_label.setFont_(NSFont.systemFontOfSize_(12))
self.status_label.setTextColor_(NSColor.secondaryLabelColor())
content.addSubview_(self.status_label)

# --- Leeren-Button ---
self.clear_btn = NSButton.alloc().initWithFrame_(
    NSMakeRect(PANEL_WIDTH - 100, 8, 80, 28)
)
self.clear_btn.setTitle_("Leeren")
self.clear_btn.setBezelStyle_(NSBezelStyleRounded)
self.clear_btn.setTarget_(self)
self.clear_btn.setAction_("clearClicked:")
content.addSubview_(self.clear_btn)
```

- [ ] **Step 2: Clear-Handler und Callback**

In `TranscriptPanel`:

```python
@objc.IBAction
def clearClicked_(self, sender):
    if self.on_clear_click:
        self.on_clear_click()
```

In `setup`:

```python
self.on_clear_click = None
```

In `AudioTranskriptApp.__init__`:

```python
self.panel.on_clear_click = self._clear_text
```

Neue Methode:

```python
def _clear_text(self):
    """Textfeld leeren."""
    self.panel.set_text("")
    self.panel.set_status("Bereit")
```

- [ ] **Step 3: Testen und Commit**

Run: `cd /Users/matze/Entwicklung/Audio-Transkript && python -m src`
Test: Text eingeben, "Leeren" klicken → Textfeld leer, Status "Bereit"

```bash
git add src/app.py
git commit -m "feat: Leeren-Button zum Zurücksetzen des Textfelds"
```

---

## Zusammenfassung der Änderungen

| Datei | Was sich ändert |
|-------|----------------|
| `src/config.py` | Panel-Größe 420x400 |
| `src/app.py` | NSTextView + NSScrollView, Kopieren/Einfügen/Leeren-Buttons, Live-Transkription-Timer, kein Auto-Einfügen mehr |
| `src/transcriber.py` | `transcribe_quick()` für Live-Preview |
| `src/recorder.py` | `get_audio_snapshot()` zum Lesen ohne Stopp |
