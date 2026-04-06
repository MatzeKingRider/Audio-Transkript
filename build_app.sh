#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="Audio Transkript"
APP_DIR="/Applications/${APP_NAME}.app"

echo "=== Audio Transkript — py2app Build ==="

# venv aktivieren
source .venv/bin/activate

# Alte Builds aufraumen
rm -rf build dist

# py2app vertraegt sich nicht mit pyproject.toml dependencies —
# temporaer verschieben fuer den alias-Build
mv pyproject.toml pyproject.toml.bak 2>/dev/null || true
python setup.py py2app -A
mv pyproject.toml.bak pyproject.toml 2>/dev/null || true

# Nach /Applications verschieben
rm -rf "$APP_DIR"
mv "dist/${APP_NAME}.app" "$APP_DIR"

# Login-Item registrieren
echo "Registriere als Login-Item..."
osascript -e "
tell application \"System Events\"
    if not (exists login item \"${APP_NAME}\") then
        make login item at end with properties {path:\"${APP_DIR}\", hidden:false}
    end if
end tell
" 2>/dev/null && echo "Login-Item registriert." || echo "WARNUNG: Login-Item konnte nicht registriert werden."

echo ""
echo "=== App installiert: $APP_DIR ==="
echo "Starten mit: open \"$APP_DIR\""
