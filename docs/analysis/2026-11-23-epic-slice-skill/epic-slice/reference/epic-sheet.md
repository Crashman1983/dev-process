# Das Epic-Blatt

Ein Markdown-Dokument im Plan-Ordner des Projekts. Der Fließtext ist für
Menschen und für das Review des Blatts; der eine `json`-Block ist das, was
`load_sheet()` liest und prüft.

## Aufbau

```markdown
# Epic 3061: Gemeinsame Oberfläche für Web, iPhone und Mac

## Ziel
Was der Owner am Ende sieht und woran er es misst.

## Referenz
Welcher Stand die Messlatte ist und warum genau dieser.

## Querschnittsverhalten
Je Verhalten: was gilt, wer es besitzt, welche Issues es berühren.

## Entscheidungen
Was im Gespräch mit dem Owner entschieden wurde, mit Datum.

## Scheiben
Kurz in Worten, warum so geschnitten und in welcher Reihenfolge.
```

Darunter der Datenblock:

```json
{
  "epic": "3061",
  "reference": {
    "build": "Gerätebuild e337fcd32d der iPhone-App",
    "check": "git rev-parse --verify e337fcd32d && git describe --tags e337fcd32d"
  },
  "integration_owner": "Steward",
  "cross_cutting": [
    {"behavior": "Kopfzeile scrollt mit dem Inhalt", "owner": "Integrationsowner"},
    {"behavior": "Fehlerzustand einer Fläche", "owner": "#3089"}
  ],
  "shared_paths": [
    "docs/feature-registry/*",
    "frontend-react/src/tokens/*",
    "frontend-react/src/routes.tsx",
    "docs/openapi.json"
  ],
  "regular": [
    {"issue": 3093, "reason": "Auth- und Sitzungszustand, Tier 3, landet vor Scheibe s2"}
  ],
  "slices": [
    {
      "id": "s1",
      "base": "origin/main",
      "max_parallel": 4,
      "checks": [
        ["npm", "--prefix", "frontend-react", "run", "build"],
        ["npm", "--prefix", "frontend-react", "run", "test", "--", "src/surfaces/chat"]
      ],
      "issues": [
        {
          "issue": 3084,
          "title": "Chat: sichere Ränder der Zeichenfläche",
          "tier": 2,
          "owns": ["frontend-react/src/surfaces/chat/*"],
          "tests": ["npm --prefix frontend-react run test -- src/surfaces/chat"]
        }
      ]
    }
  ]
}
```

Das Beispiel zeigt die Form. Die Pfade und Befehle darin sind erfunden und
müssen für das Projekt ersetzt werden.

## Pflichtfelder und was geprüft wird

| Feld | Regel |
|---|---|
| `epic` | Kennung, wird Teil der Zweig- und Ordnernamen |
| `reference.build` | Pflicht. Der Stand, gegen den gebaut und verglichen wird |
| `reference.check` | Pflicht. Ein Befehl oder Schritt, mit dem ein Arbeiter die Referenz bestätigt |
| `integration_owner` | Pflicht. Wer zusammenführt und gemeinsame Dateien ändert |
| `cross_cutting` | Je Eintrag `behavior` und `owner` |
| `shared_paths` | Muster der gemeinsamen Dateien; kein Issue darf sie besitzen |
| `regular` | Issues, die den normalen Weg gehen (alles ab Tier 3) |
| `slices[].base` | Pflicht. Von wo die Scheibe abzweigt |
| `slices[].checks` | Prüfbefehle auf dem zusammengeführten Stand, je Befehl eine Liste |
| `slices[].issues[].owns` | Pflicht. Muster der Dateien, die dem Issue gehören |
| `slices[].issues[].tier` | Höchstens 2; Tier 3 wird abgelehnt |
| `slices[].issues[].tests` | Was der Arbeiter und sein Prüfer ausführen |

`load_sheet()` lehnt das Blatt ab, wenn sich die Dateien zweier Issues einer
Scheibe überlappen oder ein Issue eine gemeinsame Datei besitzt. Die Prüfung
vergleicht nur den festen Anfang der Muster, sie ist also grob: `src/a/*` und
`src/a/x/*` überlappen, `src/a/*` und `src/ab/*` ebenfalls. Schneide die Muster
im Zweifel entlang von Ordnern.

`*` überschreitet Verzeichnisgrenzen: `src/chat/*` meint den ganzen Baum.

## Woran ein gutes Blatt zu erkennen ist

- Zwei Arbeiter, die nur das Blatt und ihr Issue lesen, bauen gegen denselben
  Stand und kommen sich nicht in die Quere.
- Jedes Verhalten, das der Owner am Gerät als „überall gleich" erwartet, hat
  einen Namen und einen Owner.
- Eine Scheibe bleibt unter der Größe, ab der das Review warnt (im Template
  30 Dateien oder 1.500 Zeilen). Sind die Issues groß, gehören zwei bis drei
  in eine Scheibe, nicht fünf.
- Riskante Teile stehen unter `regular` und sind in der Reihenfolge vorn.
