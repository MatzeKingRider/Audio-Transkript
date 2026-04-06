# Audio Transkript

Lokales macOS Menu-Bar-Tool fuer Sprach-Transkription und Screenshot-OCR. Laeuft komplett offline auf Apple Silicon mit mlx-whisper.

## Features

- **Sprach-Transkription** mit Whisper Large V3 (lokal, kein Internet)
- **Automatische Spracherkennung** (Deutsch bevorzugt, erkennt andere Sprachen automatisch)
- **Screenshot-OCR** mit macOS Vision API (Deutsch + Englisch)
- **Auto-Insert** — transkribierter Text wird direkt ins aktive Eingabefeld eingefuegt
- **Blockweise Uebertragung** bei langen Aufnahmen (alle 10 Sek.)
- **Globale Hotkeys** (Cmd+Shift+T = Mikrofon, Cmd+Shift+O = Screenshot)
- **Floating Panel** mit Textfeld, Kopieren, Einfuegen, Leeren
- **Auto-Start** beim Mac-Login

## Voraussetzungen

- macOS 13+ (Ventura oder neuer)
- Apple Silicon (M1/M2/M3/M4)
- Python 3.10+
- ca. 4 GB RAM fuer das Whisper-Modell

## Installation

```bash
# 1. Repository klonen
git clone https://github.com/MatzeKingRider/Audio-Transkript.git
cd Audio-Transkript

# 2. Alles installieren (venv + Dependencies + App bauen)
bash install.sh
```

Das Script:
- Erstellt eine Python-venv
- Installiert alle Dependencies (mlx-whisper, rumps, pyobjc, etc.)
- Baut die macOS-App mit py2app
- Installiert nach `/Applications/Audio Transkript.app`
- Registriert als Login-Item (Auto-Start)

## Manuelle Installation (Schritt fuer Schritt)

```bash
# venv erstellen
python3 -m venv .venv
source .venv/bin/activate

# Dependencies installieren
pip install -e .
pip install py2app

# App bauen
bash build_app.sh
```

## Nach der Installation

Beim ersten Start fragt macOS nach Berechtigungen. Alle drei muessen erteilt werden:

| Berechtigung | Wo | Wofuer |
|---|---|---|
| **Bedienungshilfen** | Datenschutz & Sicherheit → Bedienungshilfen | Hotkeys + Text einfuegen |
| **Mikrofon** | Datenschutz & Sicherheit → Mikrofon | Audioaufnahme |
| **Bildschirmaufnahme** | Datenschutz & Sicherheit → Bildschirmaufnahme | Screenshot-OCR |

**Wichtig:** Falls die App nach einem Update nicht mehr einfuegt oder Screenshots nicht funktionieren:
```bash
# Berechtigungen zuruecksetzen (macOS merkt sich die alte Binary)
tccutil reset Accessibility com.matze.audio-transkript
tccutil reset ScreenCapture com.matze.audio-transkript
# Dann App neu starten und Berechtigungen erneut erteilen
```

## Benutzung

| Aktion | Hotkey | Button |
|---|---|---|
| Mikrofon Start/Stop | Cmd+Shift+T | Blauer Mikrofon-Button |
| Screenshot-OCR | Cmd+Shift+O | Oranger Kamera-Button |

### Ablauf Sprach-Transkription
1. Klick ins Ziel-Eingabefeld (z.B. Notizen, Browser, Texteditor)
2. Cmd+Shift+T druecken → Aufnahme startet
3. Sprechen (bei langen Texten wird alle 10 Sek. ein Block uebertragen)
4. Cmd+Shift+T druecken → Aufnahme stoppt, letzter Block wird eingefuegt

### Ablauf Screenshot-OCR
1. Klick ins Ziel-Eingabefeld
2. Cmd+Shift+O druecken → Fadenkreuz erscheint
3. Bereich auswaehlen → Text wird erkannt und eingefuegt

## Entwicklung

```bash
# App direkt aus dem Terminal starten (ohne Build)
source .venv/bin/activate
python -m src

# Log-Datei pruefen
cat $TMPDIR/audiotranskript.log
```

## Projektstruktur

```
src/
  app.py          — Menu-Bar-App, Panel-UI, Aufnahme-Steuerung
  config.py       — Konstanten (Modell, Hotkeys, Panel-Groesse)
  recorder.py     — Mikrofon-Aufnahme mit sounddevice
  transcriber.py  — Whisper-Transkription mit mlx-whisper
  ocr.py          — Screenshot + Vision-OCR
  text_input.py   — Text einfuegen via Clipboard + Cmd+V
  hotkeys.py      — Globale Tastenkuerzel mit pynput
setup.py          — py2app-Konfiguration
build_app.sh      — Baut die .app und installiert nach /Applications
install.sh        — Komplette Installation (venv + App)
```
