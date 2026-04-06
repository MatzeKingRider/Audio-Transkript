# Audio Transkript — Entwicklungsplan

## Kontext

Lokales macOS Menu-Bar-Tool, das Sprache per Whisper transkribiert und Text aus Screenshots per OCR extrahiert. Der erkannte Text wird direkt in das aktive Eingabefeld getippt. Alles läuft lokal auf Apple Silicon — keine Cloud.

## Architektur

```
Menu Bar Icon (rumps)
    ↓ Klick
Floating NSPanel (PyObjC, always-on-top)
    ├── [Mikrofon] Button → sounddevice → mlx-whisper → Text einfügen
    ├── [Screenshot] Button → screencapture -i -c → Vision OCR → Text einfügen
    └── Status-Anzeige
    
Globale Shortcuts (pynput):
    Cmd+Shift+T → Mikrofon Start/Stop
    Cmd+Shift+O → Screenshot OCR
```

**Text-Einfüge-Strategie:** Clipboard sichern → Text auf Clipboard → Cmd+V simulieren → Clipboard wiederherstellen. Funktioniert in allen Apps.

## Projektstruktur

```
src/
  __init__.py
  app.py           — Einstiegspunkt, Menu Bar, Panel UI
  transcriber.py   — mlx-whisper Modell laden & transkribieren
  ocr.py           — screencapture + Vision OCR
  recorder.py      — Mikrofon-Aufnahme (sounddevice)
  hotkeys.py       — Globale Tastenkürzel (pynput)
  text_input.py    — Text ins aktive Feld einfügen
  config.py        — Konstanten und Einstellungen
assets/
  iconTemplate.png — Menu-Bar-Icon (16x16, Template-Image)
install.sh         — Setup-Script
pyproject.toml     — Dependencies
```

## Implementierungsphasen

### Phase 1: Grundgeruest — Menu Bar + Panel
- `pyproject.toml` mit allen Dependencies erstellen
- `src/config.py` — Konstanten (Shortcuts, Panel-Groesse, Modellname)
- `src/app.py` — rumps App + NSPanel (floating, always-on-top)
  - NSPanel mit `NSFloatingWindowLevel`, `setHidesOnDeactivate_(False)`
  - 2 Buttons (Mikrofon, Screenshot) + Status-Label
  - Panel zeigen/verstecken per Menuebar-Klick
- `assets/iconTemplate.png` — einfaches Mikrofon-Icon
- **Test:** App starten, Icon erscheint, Panel oeffnet sich und bleibt im Vordergrund

### Phase 2: Mikrofon-Aufnahme
- `src/recorder.py` — `Recorder` Klasse mit sounddevice
  - 16kHz, mono, float32 (Whisper-Format)
  - `start()` / `stop()` → numpy Array zurueck
- Button in Panel verdrahten (Toggle: Start/Stop)
- **Test:** Aufnehmen, stoppen, Audio-Buffer vorhanden

### Phase 3: Whisper-Transkription
- `src/transcriber.py` — `Transcriber` Klasse
  - Modell beim App-Start im Hintergrund laden (mit Status-Anzeige)
  - `transcribe(audio) → str` mit mlx-whisper
  - Sprache: Deutsch als Standard
- Nach Aufnahme-Stop: Transkription im Hintergrund-Thread
- Ergebnis im Status-Label anzeigen
- **Test:** Sprechen → Text erscheint im Panel

### Phase 4: Screenshot OCR
- `src/ocr.py` — zwei Funktionen:
  - `capture_screenshot()`: `screencapture -i -c` (Bereich waehlen → Clipboard)
  - `ocr_image(NSImage) → str`: Vision VNRecognizeTextRequest, Sprachen de+en
- Panel vor Screenshot verstecken, danach wieder zeigen
- **Test:** Screenshot von Text → erkannter Text im Panel

### Phase 5: Text ins aktive Feld einfuegen
- `src/text_input.py` — `type_text(text)`
  - Clipboard sichern → Text setzen → Cmd+V simulieren → Clipboard wiederherstellen
- Vorherige App merken (`NSWorkspace.frontmostApplication()`) und reaktivieren
- Nach Transkription/OCR: Text automatisch einfuegen
- **Test:** TextEdit oeffnen → Sprechen → Text erscheint in TextEdit

### Phase 6: Globale Hotkeys
- `src/hotkeys.py` — pynput `GlobalHotKeys`
  - Cmd+Shift+T: Mikrofon Toggle
  - Cmd+Shift+O: Screenshot OCR
- Callbacks auf Main-Thread dispatchen (AppKit-Anforderung)
- **Test:** Shortcuts funktionieren ohne Panel-Interaktion

### Phase 7: Polish & Installation
- Berechtigungspruefung beim Start (Mikrofon, Accessibility)
- Aufnahme-Indikator (roter Punkt / Timer)
- Benachrichtigung nach Text-Einfuegung
- `install.sh` — venv erstellen, Dependencies installieren, Hinweise zu Berechtigungen
- Quit-Option im Menue
- **Test:** Frische Installation auf anderem Mac durchspielen

## Dependencies
```
rumps>=0.4.0
pyobjc-framework-Cocoa
pyobjc-framework-Quartz  
pyobjc-framework-Vision
sounddevice
numpy
mlx-whisper
pynput
```

## Benoetigte macOS-Berechtigungen
- **Mikrofon** — fuer Audioaufnahme
- **Bedienungshilfen (Accessibility)** — fuer Hotkeys + Tastatur-Simulation
- **Bildschirmaufnahme** — fuer screencapture

## Risiken & Loesungen
1. **rumps + PyObjC Run-Loop:** Alle AppKit-Objekte im `__init__` erstellen, UI-Updates nur auf Main-Thread
2. **Erster Modell-Download (~3GB):** Status-Anzeige + Button deaktivieren bis geladen
3. **Accessibility-Berechtigung:** Beim Start pruefen und Nutzer zur Einstellung leiten

## Verifikation
1. `source .venv/bin/activate && python -m src.app` — App startet, Icon in Menueleiste
2. Panel oeffnen → bleibt im Vordergrund ueber anderen Fenstern
3. Mikrofon-Button → Aufnahme → Stop → Text erscheint im aktiven Eingabefeld
4. Screenshot-Button → Bereich waehlen → OCR-Text erscheint im aktiven Eingabefeld
5. Cmd+Shift+T und Cmd+Shift+O funktionieren global
