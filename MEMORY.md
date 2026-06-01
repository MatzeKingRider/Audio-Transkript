# MEMORY — Audio Transkript

## Aktueller Stand: v0.1.5 (F19-Beep weg + KVM-Switch-Resilience)

### Was in dieser Session getan wurde (2026-06-01)

Zwei Bugs gemeldet — F19-Warnton beim Push-to-Talk und kompletter App-Hänger
nach KVM-Switch (Tastatur/Maus/Monitor zum anderen Rechner und zurück).
Diagnose war zweistufig: erst dachten wir der Hotkey-Listener stirbt, am Ende
stellte sich heraus dass sounddevice/PortAudio der Schuldige war.

**Bug 1: F19-Beep beim PTT**

- Ursache: pynput hört über die Accessibility-API mit, konsumiert das Event
  aber NICHT systemweit. macOS findet keine UI-Action für F19 → NSBeep
- Lösung: **CGEventTap** auf `kCGSessionEventTap` fängt F19 vor allen Apps ab
  und gibt `None` zurück → Event verschwindet, kein Beep
- Neue Datei `src/f19_tap.py` mit `F19EventTap`-Klasse (Quartz Low-Level)
- Filter macOS-Auto-Repeat (`_is_pressed`-Flag); behandelt
  `kCGEventTapDisabledByTimeout`/`...ByUserInput` mit Re-Enable
- F19-Handling aus `src/hotkeys.py` entfernt (sonst doppelter Trigger);
  `HotkeyManager`-Konstruktor schlanker (nur noch `on_mic_toggle` + `on_ocr_trigger`)
- `HotkeyManager.is_listener_alive()` als Watchdog-Helper hinzugefügt

**Bug 2: App tot nach KVM-Switch (eigentliche Ursache)**

Iterative Diagnose über das Log war nötig:
1. Erst Hotkey-Recovery via Wake-Notifications + Watchdog gebaut → **half nicht**
2. Log zeigte: F18/F19 funktionieren WEITER (`_toggle_recording: is_recording=False`
   wird mehrfach gefeuert), aber Aufnahme startet nicht — also nicht die Hotkeys
3. Echte Ursache: `sounddevice`-Stream wird nach USB-Audio-Reconnect zum
   **Zombie** — `start()` wirft keine Exception, liefert aber 0 Samples
4. Fix: sounddevice/PortAudio MUSS bei jedem Aufnahme-Start frisch
   reinitialisiert werden (`sd._terminate(); sd._initialize()`)

Konkrete Code-Änderungen:

`src/recorder.py`:
- `Recorder.start()` macht jetzt IMMER vor `_open_stream()`:
  - `_force_close_stream()` (alten Zombie schließen)
  - `_reinit_sounddevice()` (PortAudio frisch)
  - `_chunks`, `_frames_received`, `_level` zurücksetzen
- Gibt `True`/`False` zurück statt stumm zu scheitern
- Neuer Frame-Counter `_frames_received` wird in `_callback` hochgezählt;
  `get_frames_received()` als Public-Getter
- Neuer Public-Wrapper `reinit_devices()` für Recovery von außen

`src/app.py`:
- `_start_recording` prüft `recorder.start()`-Return; bei Fehler Status
  „Mikrofon nicht verfuegbar" (rot)
- **Stream-Health-Check**: 500 ms nach Start einmaliger Timer, prüft
  ob `frames_received > 0`. Bei 0 Frames → Aufnahme abbrechen, sounddevice
  nochmal reinit, Status „Mikrofon zuruecksetzen — bitte erneut versuchen"
- `_recover_after_wake` ruft jetzt zusätzlich `recorder.reinit_devices()` —
  auch wenn Hotkeys leben, kann der Audio-Stream tot sein
- `F19EventTap` wird neben `HotkeyManager` initialisiert und in `_quit` /
  `_restart` mit aufgeräumt
- `AppActivationObserver` abonniert zusätzlich:
  - `NSWorkspaceDidWakeNotification` (Sleep-Wake)
  - `NSWorkspaceScreensDidWakeNotification` (Display-Wake)
  - `NSApplicationDidChangeScreenParametersNotification` (KVM-Switch —
    feuert wenn Display-Setup sich ändert; läuft über das default
    `NSNotificationCenter`, nicht NSWorkspace)
- Recovery-Callback `_recover_after_wake` neu: stoppt + startet Hotkeys + Tap,
  reinit sounddevice, bricht laufende Aufnahme ab, Status „Bereit (nach
  KVM-Switch)"
- **Watchdog-Timer** (alle 10 s) als Sicherheitsnetz: prüft
  `hotkeys.is_listener_alive()` UND `_f19_tap.is_alive()` (letzteres nutzt
  `CGEventTapIsEnabled()` — echter Health-Check, nicht nur Python-Handle)
- Watchdog-Intervall war zwischenzeitlich auf 30 s, jetzt 10 s

### Offene Punkte
- Modell-Drift Intel-Backend (`WHISPER_MODEL = "medium"` in `src/config.py:24`)
  — Memory v0.1.2 sagt large-v2; auf Apple Silicon (mlx) egal
- Optional: Klick auf Usage-Panel öffnet Detail-Sheet (war seit v0.1.3 offen)

### Nächste Schritte (wenn gewünscht)
- `git tag v0.1.5` als Release-Punkt setzen
- F19-Beep in anderen Apps gegenchecken (User wollte das noch verifizieren)
- Beobachten ob der Watchdog/Recovery zuverlässig greift; wenn nicht,
  präventiver Reinit auch im Watchdog-Tick (alle 10 s sounddevice neu)

### Wissen für künftige USB-Audio-Bugs
- `sounddevice.InputStream` wirft nach USB-Reconnect keine Exception, der
  Stream gilt als „läuft" und liefert 0 Samples. **Immer Frame-Counter
  einbauen** als Health-Check.
- `sd._terminate(); sd._initialize()` ist nicht öffentlich dokumentiert,
  aber stabil und der einzig zuverlässige Weg PortAudio-State zu refreshen,
  ohne den Python-Prozess neu zu starten.
- macOS-Beep bei unbenutzten F-Tasten lässt sich NUR über CGEventTap mit
  `return None` unterdrücken — pynput-Listener ohne `suppress=True` reicht
  nicht.
- KVM-Switches feuern oft KEINE `NSWorkspaceScreensDidWake`-Notification,
  aber zuverlässig `NSApplicationDidChangeScreenParametersNotification`.
