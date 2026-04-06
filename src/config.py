"""Konstanten und Einstellungen."""

# Menu Bar
APP_NAME = "AudioTranskript"
ICON_PATH = "assets/iconTemplate.png"

# Panel
PANEL_WIDTH = 420
PANEL_HEIGHT = 400
PANEL_TITLE = "Audio Transkript"

# Whisper
WHISPER_MODEL = "mlx-community/whisper-large-v3-mlx"
WHISPER_LANGUAGE = "de"

# Audio
SAMPLE_RATE = 16000
CHANNELS = 1

# Hotkeys
HOTKEY_MIC = "<cmd>+<shift>+t"
HOTKEY_OCR = "<cmd>+<shift>+o"

# Whisper Initial Prompt — hilft bei Groß-/Kleinschreibung und Satzzeichen
WHISPER_PROMPT = "Hallo, das ist ein Transkript. Bitte achte auf korrekte Groß- und Kleinschreibung sowie Satzzeichen."

# OCR
OCR_LANGUAGES = ["de-DE", "en-US"]
