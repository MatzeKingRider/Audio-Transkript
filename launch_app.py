"""Einstiegspunkt fuer py2app — startet die Menu-Bar-App."""

import os
import sys

# Projekt-Root in den Pfad aufnehmen damit "from src.xxx" funktioniert
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.app import main

main()
