# MEMORY — Audio Transkript

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
