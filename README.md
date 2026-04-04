# Claude Starter Workspace

Ein fertiges Workspace-Template für Claude Code. Gibt Claude strukturierten Kontext, damit er versteht wer du bist und woran du arbeitest — über Sessions hinweg.

## Setup

1. Fülle die Dateien in `context/` mit deinen Informationen aus:
   - `business-info.md` — dein Unternehmen oder Business
   - `personal-info.md` — deine Rolle und Verantwortlichkeiten
   - `strategy.md` — deine aktuellen Prioritäten und Ziele
   - `current-data.md` — wichtige Kennzahlen und aktueller Stand
2. Öffne diesen Ordner in Claude Code
3. Starte jede Session mit `/prime`

## Struktur

```
├── CLAUDE.md              # Anweisungen für Claude (wird automatisch geladen)
├── .claude/commands/
│   └── prime.md           # /prime Befehl — Session-Initialisierung
├── context/               # Dein Hintergrundkontext (hier ausfüllen)
├── outputs/               # Arbeitsergebnisse von Claude
└── reference/             # Beispiel-Outputs, Inputmaterial, Vorlagen
```

## Nutzung

Starte jede Session mit `/prime`. Claude liest deine Kontextdateien und bestätigt sein Verständnis bevor er arbeitet.

Lege Material in `reference/` ab, das Claude als Input nutzen soll — Beispiel-Outputs, Dokumente zur Analyse, Vorlagen oder Muster. Claudes Arbeitsergebnisse landen in `outputs/`.

## Verfügbare Skills

Dieses Template ist optimiert für die Nutzung mit installierten Claude Code Skills:

| Kategorie | Skills |
|-----------|--------|
| Planung | `/architecture`, `/requirements`, `/help` |
| Entwicklung | `/backend`, `/frontend`, `/mobile` |
| Qualität | `/qa`, `/critic`, `/fix-strike` |
| Operations | `/deploy`, `/infrastructure` |
| Kreativ | `/visualizer`, `/frontend-design` |
| Workflow | `/commit`, `/skill-creator`, `superpowers` |

Starte mit `/help` um zu sehen, welcher Skill als nächstes sinnvoll ist.

## Als Template nutzen

1. Repository klonen oder als GitHub Template verwenden
2. `context/`-Dateien mit projektspezifischen Informationen füllen
3. `outputs/` und `reference/` werden automatisch ignoriert (nur `.gitkeep` bleibt)
4. Optional: Shell-Alias einrichten (siehe `shell-aliases.md`)
