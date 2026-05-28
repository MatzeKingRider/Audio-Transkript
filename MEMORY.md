# MEMORY — Audio Transkript

## Aktueller Stand: v0.1.4 (Stabilisierung + VU-Meter + Gain)

### Was in dieser Session getan wurde (2026-05-28)

Diese Session war eine Regressions-Behebung von v0.1.3 plus neue Features.
v0.1.3 hatte mehrere Probleme: Aufnahme brach zu früh ab, Mic-Button stoppte
nicht auf den zweiten Klick, Transkription verlor Kontext zwischen Chunks,
Satzende wurde abgeschnitten. Außerdem fehlten Pegel-Anzeige und
Eingangs-Verstärkung für leise Mikros.

**Mic-Button-Bug (UI)**
- Hold-Logik komplett entfernt — Race-Condition zwischen 250-ms-Hold-Timer
  und Click-Erkennung machte den zweiten Klick unzuverlässig
- `MicButton`-Klasse auf reines NSButton-Verhalten reduziert
- Verdrahtung über Standard `setAction_("micClicked:")`, kein NSTimer mehr
- `on_mic_hold_start`, `on_mic_hold_end`, `micHoldCheck_`, `micHoldEnd_`,
  `is_pressed()`, `enter_hold()` entfernt aus `src/app.py`
- Tooltip: "Klick = Aufnahme starten/stoppen. F19 halten = Push-to-Talk."

**Cmd+Shift+R komplett entfernt**
- Kollidierte mit Browser-Hard-Reload (Chrome/Safari/Edge)
- `_is_ptt_combo`, `_is_ptt_release_key` aus `src/hotkeys.py` gelöscht
- `HOTKEY_PTT_ALT` aus `src/config.py` entfernt
- Aktive Hotkeys: **F17 / Cmd+Shift+O = OCR, F18 = Toggle, F19 = PTT**

**Transkriptions-Qualität**
- `condition_on_previous_text=True` in beiden Backends (mlx + faster-whisper) —
  Whisper behält Kontext zwischen Chunks
- Neuer Parameter `prev_text` in `Transcriber.transcribe()` — die letzten
  ~200 Zeichen werden via `_build_prompt()` an `initial_prompt` angehängt:
  aufeinanderfolgende kurze Sequenzen werden logisch verkettet
- VAD `min_silence_duration_ms`: 300 → **500 ms** (toleranter bei Atempausen)
- `_trim_silence`: Schwelle 0.008 → **0.004**, Puffer am Ende 0.3 s → **0.6 s**
  (leise Satzendungen gehen nicht mehr verloren)
- Trailing `"..."`-Halluzination (Whisper-Ende-Token) wird in
  `_filter_hallucinations()` zu sauberem `"."` ersetzt
- `min_len` für Chunking in `_transcribe_chunk`: 2 s → **0.5 s**
  (kurze Einsprech-Sequenzen werden nicht mehr verworfen)
- `_process_final_chunk` und `_transcribe_chunk` geben `prev_text` und
  `language` durch

**Sprach-Toggle (DE/EN) — UI**
- Kleiner Pill-Button oben rechts im Panel, Beschriftung `"DE"` / `"EN"`
- Action `langClicked_` → `on_lang_toggle` → `_toggle_language` im Controller
- State `self._language` im `AudioTranskriptApp`, default `"de"`
- `Transcriber.transcribe(..., language=...)` überschreibt Config-Default
- `WHISPER_LANGUAGE` in `src/config.py` ist wieder `"de"` (Default, kein None)
- Status-Zeile zeigt "Sprache: EN" beim Umschalten

**VU-Meter + Gain-Slider**
- Zwischen Mic- und Screenshot-Button, horizontale Anordnung
- `NSLevelIndicator` (continuous capacity, warning 0.7, critical 0.92)
  zeigt Peak-Pegel während Aufnahme (10 Hz Update via `rumps.Timer`)
- `NSSlider` 0…**10×** (von ursprünglich 4× erweitert), default 1×
- `Recorder.gain` (float) wird in `_callback` auf jedes Sample angewendet —
  wirkt sowohl auf VU als auch auf Whisper-Input
- `Recorder._level` wird in `_callback` als `np.max(np.abs(...))` berechnet,
  in `stop()` auf 0 zurückgesetzt
- VU läuft NUR während Aufnahme (User-Entscheidung: kein dauerhafter oranger
  Menüleisten-Punkt)
- Gain wird in **NSUserDefaults** unter Key `"mic_gain"` persistiert
  (`_set_gain` speichert, `_restore_gain` lädt beim App-Start),
  Plausibilitäts-Clamp 0…10
- Layout: `gap` zwischen Mic und OCR von 60 → **110 px**;
  Slider-Frame h=22 mit y=`top_y - 7` (Knopf vollständig sichtbar);
  Abstand Gain-Label ↔ Slider ausreichend groß

**Mic-Hint gekürzt**
- "F19 / Cmd+Shift+R halten" → **"F18 / F19 halten"** (passt jetzt ohne
  Abschneiden in die schmalere Spalte)

### Offene Punkte
- Modell-Drift Intel-Backend: `WHISPER_MODEL = "medium"` in `src/config.py:24`
  (Memory v0.1.2 sagt large-v2, Kommentar im Code auch — könnte beabsichtigt
  sein für Performance auf Intel)
- Optional: Klick auf Usage-Panel öffnet Detail-Sheet (war seit v0.1.3 offen)

### Nächste Schritte (wenn gewünscht)
- `git tag v0.1.4` als Release-Punkt setzen
- Beobachten ob 0.6 s Trim-Puffer ausreicht oder noch erhöht werden muss
- Beobachten ob VAD 500 ms zu spät schneidet (dann auf 350 ms zurück)
