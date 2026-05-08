# MEMORY — Audio Transkript

## Aktueller Stand: v0.1.3 (in Arbeit, noch nicht getaggt)

### Was zuletzt getan wurde (Session 2026-05-08)

**PTT-Buttons entfernt**
- On-Screen-PTT-Button (`PTTButton`-Klasse, `ptt_btn`, `ptt_label`, `ptt_hint`) vollständig aus `src/app.py` entfernt
- `TouchBarController`-Klasse + alle Touch-Bar-Hooks entfernt
- Mic-Button funktioniert jetzt als Push-and-Hold: kurzer Klick = Toggle, ≥250 ms halten = PTT

**Hotkey geändert**
- Alt-PTT-Hotkey war `Ctrl+P` (kollidiert mit VS Code Quick Open) und `Cmd+Shift+T` (VS Code Reopen Tab)
- Probiert: Cmd+Option+Space (System-Konflikt), Ctrl+Option+M (tippt µ-Zeichen)
- Final: **Cmd+Shift+R** — kein Sonderzeichen, kein VS Code-Konflikt, funktioniert bestätigt
- `src/config.py`: `HOTKEY_PTT_ALT = "cmd+shift+r"`
- `src/hotkeys.py`: `_is_ptt_combo()` prüft auf R + Cmd + Shift; `_is_ptt_release_key()` löst auf R-, Cmd- oder Shift-Release
- Mic-Hint und Tooltip in `src/app.py` zeigen "F19 / Cmd+Shift+R halten"

**Claude Code Usage Monitor**
- Neue Datei `src/claude_usage.py`: liest OAuth-Token aus macOS-Keychain (`Claude Code-credentials`), fragt `https://api.anthropic.com/api/oauth/usage` ab (Beta-Header `oauth-2025-04-20`), 60s Cache, 5min Cache bei HTTP 429
- API-Werte `used_credits` und `monthly_limit` sind in Cent → Division durch 100 für Euro-Anzeige
- Neue Klasse `UsagePanelView(NSView)` in `src/app.py`: custom `drawRect_` mit Progress-Bars, 5 Zeilen (Sitzung 5h, Woche alle, Woche Sonnet, Woche Opus, Woche Code + Extra-Credits)
- Wichtig: PyObjC 9.x bridget Python-`str` NICHT automatisch zu NSString für Drawing-Calls → immer `NSString.stringWithString_(text).drawInRect_withAttributes_(...)` verwenden
- Wichtig: Klassen-Attribute `= None` auf NSView-Subklassen crashen den ObjC-Runtime → `self.__dict__["_rows"] = []` in `initWithFrame_` verwenden
- `PANEL_HEIGHT = 490` (war 440, +50px für Usage-Panel)
- Feature-Flag: `CLAUDE_USAGE_MONITOR_ENABLED = True` in `src/config.py`

### Offene Punkte
- Kein offener Bug bekannt; App läuft stabil
- Version noch nicht auf v0.1.3 getaggt / kein Release-Commit

### Nächste Schritte (wenn gewünscht)
- `git tag v0.1.3` + Changelog-Commit
- Optional: Klick auf Usage-Panel öffnet Detail-Sheet (war im Plan, noch nicht umgesetzt)
