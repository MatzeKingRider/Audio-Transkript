"""Benutzer-Vokabular: Begriffe (Priming) + Korrekturen (falsch -> richtig).

Persistenz als JSON in ~/Library/Application Support/AudioTranskript/vocabulary.json.
Beim ersten Start (oder defekter Datei) wird aus den Default-Seeds in config.py
befuellt, damit nichts verloren geht. Der Training-Reiter schreibt hier hinein;
transcriber.py liest prompt_terms() und corrections() bei jeder Transkription.

Ein Eintrag: {"wrong": str, "right": str, "context": str}
- "right" (Pflicht): korrekte Schreibweise -> speist Whisper-Prompt UND Korrektur.
- "wrong" (optional): wenn gesetzt, wird der Text per Post-Processing ersetzt;
  wenn leer, dient der Begriff nur als Prompt-Priming.
- "context" (optional): der Satz, in dem die Korrektur angelegt wurde -- reine
  Dokumentation (in der Trainingsliste sichtbar), beeinflusst die Ersetzung nicht.
"""

import json
import logging
import os
import re
import threading

from src.config import WHISPER_PROMPT, WORD_CORRECTIONS

log = logging.getLogger("AT")

_APP_SUPPORT = os.path.expanduser(
    "~/Library/Application Support/AudioTranskript")
_PATH = os.path.join(_APP_SUPPORT, "vocabulary.json")

# Maximale Laenge des Prompt-Begriffsteils, damit Whisper den Prompt nicht
# zurueck-halluziniert (vgl. Hinweis in config.py).
_PROMPT_MAX_CHARS = 200

_lock = threading.RLock()
_entries = None  # type: list[dict] | None


# --- Seed (erster Start) ----------------------------------------------------

def _split_prompt(prompt):
    """'raaco, Boxxser.' -> ['raaco', 'Boxxser']."""
    return [p.strip() for p in re.split(r"[,.]", prompt) if p.strip()]


def _seed_entries():
    """Default-Eintraege aus den config.py-Seeds bauen."""
    entries = []
    # 1) Korrekturen (falsch -> richtig)
    for wrong, right in WORD_CORRECTIONS.items():
        entries.append({"wrong": wrong, "right": right})
    # 2) Reine Prompt-Begriffe, die noch nicht als 'right' vorkommen
    rights = {e["right"].lower() for e in entries}
    for term in _split_prompt(WHISPER_PROMPT):
        if term.lower() not in rights:
            entries.append({"wrong": "", "right": term})
            rights.add(term.lower())
    return entries


# --- Persistenz -------------------------------------------------------------

def _normalize(raw):
    """JSON-Rohdaten in saubere Eintragsliste verwandeln."""
    out = []
    if isinstance(raw, list):
        for e in raw:
            if isinstance(e, dict) and (e.get("right") or "").strip():
                out.append({
                    "wrong": (e.get("wrong") or "").strip(),
                    "right": (e.get("right") or "").strip(),
                    "context": (e.get("context") or "").strip(),
                })
    return out


def _write_to_disk(entries):
    try:
        os.makedirs(_APP_SUPPORT, exist_ok=True)
        tmp = _PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _PATH)
    except Exception as exc:
        log.warning("vocabulary: Speichern fehlgeschlagen: %s", exc)


def _load_from_disk():
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = _normalize(data)
        if entries:
            return entries
    except FileNotFoundError:
        pass
    except Exception as exc:
        log.warning("vocabulary: Laden fehlgeschlagen, nutze Seed: %s", exc)
    # Erststart oder leere/defekte Datei -> Seed schreiben
    seeded = _seed_entries()
    _write_to_disk(seeded)
    return seeded


def _ensure_loaded():
    global _entries
    if _entries is None:
        with _lock:
            if _entries is None:
                _entries = _load_from_disk()


# --- Oeffentliche API -------------------------------------------------------

def reload():
    """Cache von der Platte neu laden (nach Aenderungen im Training-Reiter)."""
    global _entries
    with _lock:
        _entries = _load_from_disk()
    return entries()


def entries():
    """Kopie aller Eintraege (fuer die UI-Liste)."""
    _ensure_loaded()
    with _lock:
        return [dict(e) for e in _entries]


def add(wrong, right, context=""):
    """Eintrag hinzufuegen (Duplikate werden ignoriert).

    context: optionaler Satz, in dem die Korrektur entstand (nur Doku).
    """
    wrong = (wrong or "").strip()
    right = (right or "").strip()
    context = (context or "").strip()
    if not right:
        return
    _ensure_loaded()
    with _lock:
        for e in _entries:
            if e["wrong"].lower() == wrong.lower() and e["right"] == right:
                # Duplikat: fehlenden Kontext nachtragen, sonst nichts tun
                if context and not e.get("context"):
                    e["context"] = context
                    _write_to_disk(_entries)
                return
        _entries.append({"wrong": wrong, "right": right, "context": context})
        _write_to_disk(_entries)


def remove(wrong, right):
    """Eintrag entfernen (exakter Treffer auf wrong+right)."""
    wrong = (wrong or "").strip()
    right = (right or "").strip()
    _ensure_loaded()
    with _lock:
        _entries[:] = [e for e in _entries
                       if not (e["wrong"] == wrong and e["right"] == right)]
        _write_to_disk(_entries)


def prompt_terms():
    """Begriffe fuer den Whisper initial_prompt — laengenbegrenzt."""
    _ensure_loaded()
    with _lock:
        items = list(_entries)
    seen = set()
    terms = []
    for e in items:
        t = e["right"].strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            terms.append(t)
    out = ""
    for t in terms:
        candidate = (out + ", " + t) if out else t
        if len(candidate) > _PROMPT_MAX_CHARS:
            break
        out = candidate
    return (out + ".") if out else ""


def corrections():
    """Dict {falsch: richtig} fuer das Post-Processing."""
    _ensure_loaded()
    with _lock:
        items = list(_entries)
    out = {}
    for e in items:
        w = e["wrong"].strip()
        r = e["right"].strip()
        if w and r:
            out[w] = r
    return out
