# MEMORY — Audio Transkript

## Session 2026-06-17 — v0.1.7: Erkennung + Clipboard-Fix + Training-Reiter

### Warum
Drei Beschwerden vom Nutzer: (1) Eigennamen falsch erkannt — „Claude Code"
→ „Cloud Code", „raaco" → „Raku"; (2) beim Einfügen landet manchmal der
ALTE Zwischenablage-Inhalt im Ziel; (3) Wunsch, Begriffe selbst zu pflegen
(„Reiter Training"). Nur Apple-Silicon-Variante relevant (large-v3 bleibt —
kein Modellwechsel).

### Was gemacht wurde
- **Neuer Vokabular-Speicher** `src/vocabulary.py`: persistente JSON unter
  `~/Library/Application Support/AudioTranskript/vocabulary.json`. Einträge
  `{wrong, right}`; `right` (Pflicht) speist Whisper-Prompt + Korrektur,
  `wrong` (optional) löst Post-Processing-Ersetzung aus. Seedet beim ersten
  Start aus den config.py-Defaults (`WHISPER_PROMPT` + `WORD_CORRECTIONS`).
  API: `prompt_terms()` (längenbegrenzt ~200 Zeichen gegen Halluzination),
  `corrections()`, `add/remove/reload/entries`. Modul-Cache → Änderungen
  wirken ohne Neustart.
- **config.py**: `WHISPER_PROMPT` jetzt mit „Claude Code"; neue Korrekturen
  `cloud code`/`claude code` → „Claude Code", `raku/rakku/rakuh` → „raaco".
  Beide bleiben nur noch Default-Seed.
- **transcriber.py**: `_build_prompt`, `_fix_spacing` und `transcribe_quick`
  ziehen aus `vocabulary`. Korrekturen jetzt mit **Wortgrenzen** (`\b…\b`,
  kein Über-Treffer mitten im Wort) + **Callable-Ersatz** (Sonderzeichen-sicher).
- **Clipboard-Bug** (`src/text_input.py` + `src/app.py`): (a) Modul-`Lock`
  serialisiert parallele Einfüge-Threads (Live-Insert während Aufnahme
  überschrieb sich die Clipboard-Sicherung); (b) Wartezeit vor Restore
  `0.1 → 0.3 s` (Ziel-App las Clipboard erst nach dem Restore → alter Inhalt);
  (c) Leer-Text-Schutz in `type_text` + `_insert_in_target`.
- **Reiter „Training"** (`src/app.py`): neue `TrainingPanel`-Klasse =
  eigenes NSPanel (kein eingebetteter Tab — Hauptpanel ist voll, frame-basiert,
  kein NSTabView). Geöffnet über neuen Menüeintrag „Training…". Eingabezeile
  (wrong optional / right Pflicht) + NSTableView-Liste + „Markierten löschen".

### Fertig
- Automatisiert verifiziert: `py_compile` aller Dateien, voller `import src.app`
  inkl. ObjC-Registrierung TrainingPanel, Funktionstest (Seed, Korrekturen
  case-insensitive, Wortgrenzen schützen „Rakuten", add() sofort wirksam,
  JSON-Persistenz) — alles grün.
- Dabei Folgefehler gefunden+gefixt: `transcribe_quick` referenzierte noch
  das entfernte `WHISPER_PROMPT`.

### Offen / vom Nutzer noch live zu testen (braucht GUI + Mikro)
- „Claude Code"/„raaco" diktieren → korrekt; Clipboard-Test (kopierter Inhalt
  bleibt erhalten, kein Fremd-Einfügen); Training-Fenster Add/Liste/Löschen +
  Persistenz über Neustart.
- Entscheidung offen: echter eingebetteter Tab statt separatem Fenster (größerer
  UI-Umbau) — nur falls gewünscht.

### Nebenbefund (nicht geändert)
- `pyproject.toml` version steht auf `0.1.1` (driftet, Releases laufen über
  Commit-Message-Tags `v0.1.x`). Pre-existing in-flight in diesem Commit
  mitgenommen: hotkeys.py-Refactor + `pynput`-Entfernung aus pyproject.
- Untracked NICHT committet: `2026-04-22 19.28.42.jpg` (verirrtes Foto),
  `inspect_macbook.sh` (Diagnose-Skript) — liegen weiter auf der Platte.

## Session 2026-06-17 — Windows-Übergabe-Prompt erstellt

Kein Code geändert. Ziel: App an einen Dritten weitergeben, der sie mit
Claude Code **von Grund auf neu für Windows** baut (reine Windows-Variante,
KEIN Altcode-Transfer, kein Repo-Sharing).

- **Deliverable:** `outputs/windows-neuentwicklung-prompt.md` — eine
  einzige Markdown-Datei: kurze Benutzungs-Anleitung + vollständiger,
  copy-paste-fertiger Prompt für Claude Code (Block `=== PROMPT START ===`
  bis `=== PROMPT ENDE ===`).
- Prompt ist self-contained: kompletter Funktionsumfang + über v0.1.1–v0.1.6
  gelernte Verhaltensweisen (Smart Chunking/Pausenerkennung,
  Halluzinations-Filter, VU-Meter, Gain 0–10×, DE/EN, Geräte-Resilienz,
  persistente Settings, Autostart) sind eingearbeitet.
- Windows-Mapping im Prompt: rumps/AppKit → PySide6, CGEventTap → `keyboard`,
  Apple Vision → Windows-eigene OCR (`winsdk`), faster-whisper bleibt,
  py2app → PyInstaller. Hinweis: F17–F19 gibt's auf Windows nicht → Hotkeys
  soll Claude mit dem Empfänger abstimmen.
- Prompt ist auf Deutsch. Offen/optional: englische Fassung, falls der
  Empfänger kein Deutsch spricht.

Mac-Code, Repo und Git-Status unverändert.

## Aktueller Stand: v0.1.6 (KVM-Hänger gefixt + Restart-Bundle + Fenstergröße)

### Was in dieser Session getan wurde (2026-06-02)

Drei Probleme nach v0.1.5 zu lösen: KVM-Switch hängte die App immer noch
(plus: Neustart half gar nicht mehr), die Mac-App startete nach „Neustart"
im Menü nicht wieder, und Fenstergröße ging beim Neustart verloren.

**Bug 1 — KVM-Switch tötete sounddevice + Mach-Port-Leak (v0.1.6 Hauptfix)**

Diagnose im Code zeigte **vier strukturelle Schwachstellen**:

1. **`F19EventTap.stop()` rief kein `CFMachPortInvalidate`** —
   Mach-Port leakte bei jeder Recovery im Kernel. macOS limitiert die
   Anzahl gleichzeitiger Event-Taps pro Prozess → nach mehreren
   KVM-Switches kapitulierte das System lautlos. Erklärt warum
   irgendwann auch Neustart nicht mehr half.
2. **`_recover_after_wake` ohne Reentrant-Sperre** — KVM-Switches feuern
   typisch 3-5 Notifications zeitgleich (`DidChangeScreenParameters`,
   `ScreensDidWake`, Watchdog). Jede Recovery rief `sd._terminate();
   sd._initialize()` parallel → `coreaudiod` ging in einen kaputten
   Zustand aus dem auch Process-Neustart nicht mehr rauskam.
3. **Recovery rief `_stop_recording`** das einen Transcribe-Thread
   startete, der mit dem direkt folgenden `sd._terminate()` kollidieren
   konnte.
4. **`_restart` stoppte Watchdog-Timer nicht** und nutzte
   `subprocess.Popen('sleep 1 && open ...')` — wenn der alte Prozess
   noch nicht weg war (Watchdog hing), startete macOS keine neue
   Instanz (Single-Instance-Schutz).

Fixes:
- `src/f19_tap.py`: `CFMachPortInvalidate(self._tap)` im `stop()` nach
  `CFRunLoopRemoveSource`
- `src/app.py`: `self._recovery_lock = threading.Lock()` +
  `self._last_recovery_at` + **5 s Cooldown** in `_recover_after_wake`.
  Mehrfach-Trigger werden mit „Cooldown aktiv, skip" geloggt.
- `src/app.py`: Neue Methode `_cleanup_recording_ui()` (stoppt nur die
  UI-Timer + Mic-Icon, OHNE Transkription). Recovery nutzt
  `recorder._force_close_stream()` + `_cleanup_recording_ui()` statt
  `_stop_recording()` — kein Transcribe-Thread-Race mit `sd._terminate`.
- `src/app.py`: Neue gemeinsame Methode `_teardown_for_exit()` für
  Quit + Restart (stoppt ALLE Timer inkl. Watchdog, F19-Tap mit
  Invalidate, `recorder._force_close_stream`, `sd._terminate()`,
  `time.sleep(0.2)`). `_quit` und `_restart` nutzen beide diese Methode.
- `src/app.py`: Watchdog (`_watchdog_tick`) skipped wenn
  `recorder.is_recording == True` — keine Kollision mit laufender Aufnahme.

**Bug 2 — Mikrofon liefert nach KVM kurz keine Samples (Symptom: 0-Frames-
Health-Check, „Mikrofon nicht verfügbar"-Status nach KVM)**

Diagnose aus Live-Log: nach KVM-Switch öffnet `sd.InputStream` erfolgreich,
aber CoreAudio braucht 500–800 ms bis das USB-Mikro „warm" ist und Samples
liefert. Mein bisheriger Health-Check gab nach 500 ms auf und reinit-ete,
ohne den Stream neu zu öffnen → nächster F19-Druck startete wieder bei 0.

Fix in `src/recorder.py` (`Recorder.start()`):
- Eingebaute **Retry-Schleife mit Sample-Polling**, max 3 Versuche
- Pro Versuch: `_force_close_stream` → `_reinit_sounddevice` →
  `_open_stream` → bis zu 900 ms warten ob `_frames_received > 0`
- Bei Erfolg: `is_recording=True`, sofort return True
- Bei Misserfolg: 400 ms Pause, nächster Versuch
- Standardfall (Mikro warm): <100 ms blockierend
- KVM-Fall: ~500–800 ms
- Worst Case (3 Retries): ~3.9 s — akzeptabel, weil User auf „Aufnahme läuft"
  wartet
- `start()` gibt nur True zurück wenn Samples wirklich kamen, nicht nur
  „Stream offen"
- Log-Zeile bei Erfolg: `recorder.start: Samples nach Nms (Versuch N/3)`

**Bug 3 — „Neustart" im Menü beendete die App, startete sie aber nicht neu**

Ursache: `os.execv(sys.executable, [sys.executable] + sys.argv)` ersetzt
den Prozess durch einen reinen Python-Interpreter. Bei einer aus dem
gebundleten `.app` gestarteten Anwendung fehlt damit die
LaunchServices-Integration (Menüleisten-Icon, Bundle-Identity), der
Prozess beendet sich nach Sekundenbruchteil.

Fix in `src/app.py` (`_restart`):
- Neue Hilfsmethode `_detect_app_bundle_path()` via
  `NSBundle.mainBundle().bundlePath()` — gibt den `.app`-Pfad zurück
  wenn aus Bundle, sonst None
- `_restart` zweigeteilt:
  - **Bundle-Modus**: `subprocess.Popen(['/bin/sh', '-c',
    'sleep 1 && open "/path/to/Audio Transkript.app"'])` + quit
  - **Dev-Modus**: `os.execv` als Fallback
- 1 s `sleep` gibt dem alten Prozess Zeit, sauber wegzugehen (sonst
  Single-Instance-Block)
- Klappt sauber dank `_teardown_for_exit()` aus Bug 1

**Feature — Fenstergröße persistieren**

In `src/app.py` (`TranscriptPanel`):
- Neue Methoden `_load_panel_size()` + `_save_panel_size()` über
  NSUserDefaults (Keys: `panel_width`, `panel_height`)
- `_build_panel` lädt gespeicherte Größe bei jedem Start, Fallback auf
  `PANEL_WIDTH`/`PANEL_HEIGHT` aus config
- `windowDidResize_` ruft nach `_relayout` auch `_save_panel_size()`
- Plausibilitäts-Clamp: nicht kleiner als Default, max 2000 px

### Offene Punkte
- Modell-Drift Intel-Backend (`WHISPER_MODEL = "medium"` in `src/config.py:24`)
  — auf Apple Silicon (mlx) irrelevant
- Optional: Klick auf Usage-Panel öffnet Detail-Sheet (seit v0.1.3 offen)
- Falls KVM in seltenen Fällen doch noch hängt: nächster Hebel wäre
  Subprocess-Isolation für den Audio-Stack (eigener Worker-Prozess,
  Pipe zur Haupt-App)

### Nächste Schritte (wenn gewünscht)
- `git tag v0.1.6` als Release-Punkt
- Auch Fenster-**Position** persistieren (aktuell wird nur Größe gespeichert,
  Position wird beim Start auf Bildschirmmitte gesetzt)

### Wissen für künftige USB-Audio + KVM-Bugs
- CGEventTap-Cleanup IMMER mit `CFMachPortInvalidate` — sonst leakt der
  Mach-Port im Kernel
- Recovery-Funktionen IMMER mit Reentrant-Lock + Cooldown — KVM-Switches
  feuern 3-5 Notifications zeitgleich
- `sd._terminate()` darf NICHT parallel zu einem aktiven Stream laufen —
  zerstört `coreaudiod`-State
- `os.execv` funktioniert NICHT für .app-Bundle-Restart — `open` via
  Subprocess + `quit` ist der Weg
- CoreAudio braucht nach USB-Reconnect 500-800 ms bis Samples kommen —
  einfaches „Stream offen?" reicht nicht als Health-Check, Frame-Counter
  muss tatsächlich hochzählen
