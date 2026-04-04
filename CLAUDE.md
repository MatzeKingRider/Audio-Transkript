# CLAUDE.md

Dies ist ein strukturierter Workspace. Benutzerkontext liegt in `context/`.

Führe `/prime` zum Sessionstart aus, um alle Kontextdateien zu lesen bevor du arbeitest.

## Workspace

- `context/` — wer der Benutzer ist, sein Business, Strategie und aktuelle Daten
- `outputs/` — Arbeitsergebnisse und Deliverables kommen hier rein
- `reference/` — Beispiel-Outputs, Inputmaterial für Analysen, Vorlagen und wiederverwendbare Muster

## Regeln

- Lies immer `/prime` oder die Kontextdateien bevor du mit der Arbeit beginnst
- Bei Workspace-Änderungen CLAUDE.md aktualisieren falls sich die Struktur ändert
- Antworten an den Zielen und Prioritäten des Benutzers aus dem Kontext ausrichten

## Verfügbare Skills

Dieser Workspace hat Zugriff auf spezialisierte Skills und Plugins:

### Projekt-Skills
- `/architecture` — Implementierungsansatz entwerfen ohne Code zu schreiben
- `/requirements` — Feature-Spezifikationen erstellen oder verfeinern
- `/backend` — Feature-Arbeit in NestJS + Prisma Backend
- `/frontend` — Feature-Arbeit in React + Vite Frontend
- `/mobile` — Feature-Arbeit in React Native Mobile App
- `/deploy` — Deployment-Anleitung für Synology Docker Compose
- `/infrastructure` — Home-Infrastruktur verwalten (Cloudflare, Docker, Netzwerk)
- `/qa` — Feature gegen Akzeptanzkriterien validieren
- `/critic` — Konstruktive Kritik an Arbeit, Plänen, Analysen
- `/fix-strike` — Produktverhalten und UI reparieren
- `/visualizer` — Daten in interaktive HTML-Dashboards verwandeln
- `/help` — Projektstatus und nächsten Skill empfehlen

### Workflow-Plugins
- `superpowers` — Planung, Brainstorming, Code-Review, parallele Agents
- `frontend-design` — Hochwertige Frontend-Interfaces erstellen
- `playwright` — Browser-Automatisierung und Testing
- `commit-commands` — Git Commit, Push, PR Workflows (`/commit`, `/commit-push-pr`)
- `skill-creator` — Neue Skills erstellen und optimieren

## Typische Projekttypen

Der Benutzer arbeitet typischerweise an:
- **Web-Dashboards** (Express + React + Vite)
- **Smart Storage** (NestJS + Prisma + React Native)
- **Infrastruktur** (Docker auf Linux Mac Mini, Synology NAS, Cloudflare)
- **Business-Analysen und Strategiearbeit** (als Unternehmer und KAM)