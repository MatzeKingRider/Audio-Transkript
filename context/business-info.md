# Business Info

## Projektübersicht

Audio Transkript — ein lokales Tool zur Umwandlung von gesprochener Sprache und Text aus Medien in Eingabefelder. Läuft vollständig auf dem eigenen Rechner, keine Cloud-Abhängigkeit.

## Funktionen

- Audio/Video-Dateien transkribieren (Whisper large-v3 via mlx-whisper)
- Live-Audioeingabe (Mikrofon) transkribieren und in Eingabefelder eintragen (Claude Code, VS Code, etc.)
- Text aus Screenshots extrahieren (OCR via macOS Vision API) und in Eingabefelder eintragen

## Wichtiger Kontext

- Ziel-Hardware: Apple Silicon Macs (entwickelt auf M4 Pro, 24 GB RAM)
- Soll auch auf anderen Rechnern installierbar sein
- Technologie-Stack: Python, mlx-whisper (Apple Silicon optimiert), macOS Vision API
- Whisper-Modell: large-v3 (beste Genauigkeit, läuft flüssig auf M4 Pro)
