"""Konstanten und Einstellungen."""

import platform

# Menu Bar
APP_NAME = "AudioTranskript"
ICON_PATH = "assets/iconTemplate.png"

# Panel
PANEL_WIDTH = 520
PANEL_HEIGHT = 440
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

# Hotkeys — F-Tasten (F17-F19)
HOTKEY_MIC_TOGGLE = "<f18>"   # Toggle: Start/Stop (einmal druecken)
HOTKEY_OCR = "<f17>"          # Screenshot-OCR
# F19 = Push-to-Talk (halten = Aufnahme, loslassen = Stopp) — in hotkeys.py

# Whisper Initial Prompt — steuert Schreibweisen.
# ACHTUNG: Whisper halluziniert den Prompt zurueck wenn er zu lang ist.
# Daher nur ein kurzer Beispielsatz mit den wichtigsten Schreibweisen.
WHISPER_PROMPT = "raaco, Boxxser, CarryLite, HandyBox."

# Woerter die immer in einer bestimmten Schreibweise erscheinen sollen.
# Format: {falsch_lowercase: richtig}
WORD_CORRECTIONS = {
    "raco": "raaco",
    "raaco": "raaco",   # Gross -> klein
    "rako": "raaco",
    "racko": "raaco",
    "boxser": "Boxxser",
    "boxxer": "Boxxser",
    "carrylite": "CarryLite",
    "carry lite": "CarryLite",
    "handybox": "HandyBox",
    "handy box": "HandyBox",
    "assorterpro": "AssorterPro",
    "assorter pro": "AssorterPro",
}

# OCR
OCR_LANGUAGES = ["de-DE", "en-US"]
