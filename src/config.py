"""Konstanten und Einstellungen."""

import platform

# Menu Bar
APP_NAME = "AudioTranskript"
ICON_PATH = "assets/iconTemplate.png"

# Panel
PANEL_WIDTH = 420
PANEL_HEIGHT = 400
PANEL_TITLE = "Audio Transkript"

# Architektur-Erkennung
IS_APPLE_SILICON = platform.machine() == "arm64"

# Whisper — unterschiedliches Backend je nach Chip
if IS_APPLE_SILICON:
    WHISPER_BACKEND = "mlx"
    WHISPER_MODEL = "mlx-community/whisper-large-v3-mlx"
else:
    WHISPER_BACKEND = "faster"
    # Auf Intel-CPU ist "medium" ein guter Kompromiss (Geschwindigkeit vs. Qualitaet)
    WHISPER_MODEL = "medium"

WHISPER_LANGUAGE = "de"

# Audio
SAMPLE_RATE = 16000
CHANNELS = 1

# Hotkeys
HOTKEY_MIC = "<cmd>+<shift>+t"
HOTKEY_OCR = "<cmd>+<shift>+o"

# Whisper Initial Prompt — steuert Schreibweisen und Fachbegriffe.
# Whisper nutzt diesen Text als Kontext fuer die Transkription.
# Firmenspezifische Begriffe hier eintragen damit sie korrekt erkannt werden.
WHISPER_PROMPT = (
    "Dies ist ein Transkript mit korrekter Gross- und Kleinschreibung sowie Satzzeichen. "
    "raaco ist ein daenischer Hersteller von Sortiment- und Aufbewahrungssystemen. "
    "raaco wird immer kleingeschrieben. "
    "Weitere Begriffe: Key-Account-Manager, Sortimentskästen, CarryLite, Boxxser, HandyBox, AssorterPro."
)

# OCR
OCR_LANGUAGES = ["de-DE", "en-US"]
