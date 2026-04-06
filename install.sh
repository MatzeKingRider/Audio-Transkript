#!/bin/bash
set -e

echo "=== Audio Transkript — Installation ==="
echo ""

# Python-Version pruefen
PYTHON=$(command -v python3 || true)
if [ -z "$PYTHON" ]; then
    echo "FEHLER: Python 3 nicht gefunden. Bitte installiere Python 3.10+."
    exit 1
fi

PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python: $PY_VERSION"

# Pruefe Apple Silicon
ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo "WARNUNG: Dieses Tool ist fuer Apple Silicon optimiert (gefunden: $ARCH)"
    echo "         mlx-whisper funktioniert nur auf Apple Silicon."
    exit 1
fi
echo "Architektur: $ARCH (Apple Silicon)"

# Virtual Environment erstellen
echo ""
echo "Erstelle Virtual Environment..."
$PYTHON -m venv .venv
source .venv/bin/activate

# Dependencies installieren
echo "Installiere Dependencies..."
pip install -e . 2>&1 | tail -3
pip install py2app 2>&1 | tail -1

# App-Icon erstellen (falls noch nicht vorhanden)
if [ ! -f assets/AppIcon.icns ]; then
    echo "Erstelle App-Icon..."
    mkdir -p build/AppIcon.iconset
    for size in 16 32 128 256 512; do
        sips -z $size $size assets/iconTemplate.png --out "build/AppIcon.iconset/icon_${size}x${size}.png" 2>/dev/null
    done
    for size in 16 32 128 256; do
        double=$((size * 2))
        sips -z $double $double assets/iconTemplate.png --out "build/AppIcon.iconset/icon_${size}x${size}@2x.png" 2>/dev/null
    done
    iconutil -c icns build/AppIcon.iconset -o assets/AppIcon.icns
    rm -rf build/AppIcon.iconset
fi

# macOS App erstellen
echo ""
echo "Erstelle macOS App..."
bash build_app.sh

echo ""
echo "=== Installation abgeschlossen ==="
echo ""
echo "Die App liegt unter: /Applications/Audio Transkript.app"
echo "Sie startet automatisch beim naechsten Login."
echo ""
echo "Jetzt starten mit:"
echo "  open /Applications/Audio\ Transkript.app"
echo ""
echo "=== Benoetigte macOS-Berechtigungen ==="
echo "Bitte erteile folgende Berechtigungen in Systemeinstellungen → Datenschutz & Sicherheit:"
echo ""
echo "  1. Bedienungshilfen — fuer Hotkeys + Text einfuegen"
echo "  2. Mikrofon         — fuer Audioaufnahme"
echo "  3. Bildschirmaufnahme — fuer Screenshot-OCR"
echo ""
echo "Tastenkuerzel:"
echo "  Cmd+Shift+T — Mikrofon Start/Stop"
echo "  Cmd+Shift+O — Screenshot OCR"
