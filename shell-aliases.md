# Shell Alias für Claude Code

Dieser Alias ermöglicht den schnellen Start einer Claude Code Session mit automatisch geladenem Workspace-Kontext.

## Einrichtung

Diese Zeile in die `~/.zshrc` einfügen:
```bash
alias cs='claude "/prime"'
```

Dann die Shell neu laden: `source ~/.zshrc`

## Der Alias

### `cs` — Claude Safe
```bash
alias cs='claude "/prime"'
```

Startet Claude Code und führt sofort `/prime` aus, um den Workspace-Kontext zu laden. Claude fragt vor dem Ausführen von Befehlen, dem Lesen sensibler Dateien oder dem Vornehmen von Änderungen um Erlaubnis.

**Verwenden wenn:** Eine neue Session gestartet wird und jede Aktion manuell freigegeben werden soll.

## Warum `/prime` automatisch?

`/prime` lädt beim Start den gesamten Workspace-Kontext — Ziele, Projektstruktur, laufende Aufgaben und Konventionen. Damit startet Claude jede Session vollständig orientiert, ohne dass man den Kontext manuell erklären muss.