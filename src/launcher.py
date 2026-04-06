"""Launcher für die .app — setzt Pfade und startet die App."""

import os
import sys

# Projekt-Root setzen
PROJECT_DIR = os.path.join(os.path.dirname(__file__), os.pardir)
PROJECT_DIR = os.path.abspath(PROJECT_DIR)
os.chdir(PROJECT_DIR)

# Site-packages der venv in den Pfad aufnehmen
VENV_SITE = os.path.join(PROJECT_DIR, ".venv", "lib", "python3.11", "site-packages")
if VENV_SITE not in sys.path:
    sys.path.insert(0, VENV_SITE)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.app import main

main()
