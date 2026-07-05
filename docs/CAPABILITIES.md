# Was der Prozess kann — wie er funktioniert, warum, und was er bringt

Dieses Dokument erklärt `dev-process` für zwei Zielgruppen ohne Vorwissen: für
**Entwickler:innen** (auch Berufseinsteiger:innen), die täglich damit arbeiten,
und für **Management**, das entscheidet, ob sich der Prozess lohnt. Es beantwortet
drei Fragen — *wie geht das, warum so, welchen Vorteil bringt es* — erst
gemeinsam, dann je Zielgruppe.

Kurzfassung in je einem Satz:

- **Entwickler:in:** Der Prozess sagt dir für jede Aufgabe, wie viel Sorgfalt sie
  braucht, und fängt deine Fehler durch automatische Prüfungen ab, bevor ein
  Mensch sie im Review findet.
- **Management:** Der Prozess erzwingt maschinell, dass riskante Änderungen
  geprüft, nachvollziehbar und getestet sind — unabhängig davon, wer (oder welche
  KI) gerade tippt, und ohne dass jemand danebensteht.

---

## Wie es funktioniert (für beide)

Der Kern sind fünf Bausteine. Keiner davon verlässt sich auf Disziplin — jeder
ist entweder eine feste Regel oder eine Maschine, die prüft.

1. **Risiko-Tier statt Bauchgefühl.** Jede Aufgabe bekommt eine Stufe 0–3 — nach
   *Umfang*, nicht nach Anzahl geänderter Zeilen. Ein Zehn-Zeilen-Redirect, der
   eine gespeicherte URL liest, ist Tier 2, kein Tier 0. Die Stufe bestimmt den
   Weg:

   | Tier | Was das heißt | Weg |
   |---|---|---|
   | **0** | Keine Verhaltensänderung (Doku, Format) oder lokal & reversibel | Direkt committen bzw. kurzer Quick-Weg |
   | **1** | Kleines Feature/Fix, keine Contract-/Persistenz-/Auth-Berührung | Quick-Weg **+ ein Test** |
   | **2** | User-sichtbar, komponentenübergreifend, oder ein Interface/Contract | Plan → Umsetzen → **unabhängiger Review** |
   | **3** | Auth, Persistenz/Migration, Security, Multi-Repo | Zusätzlich Vorab-Design + Review über Modellgrenze hinweg |

2. **Neun bindende Regeln.** Verifikation vor Behauptung; Plan vor substanzieller
   Arbeit; Contract zuerst; ein Owner pro Verhalten (strukturell statt additiv);
   Tests beweisen Akzeptanz; Root-Cause vor Symptom; Review-Gate vor Merge;
   atomare Commits; Code wird zum Lesen geschrieben. Reihenfolge = Priorität.

3. **Durchsetzung durch Gates, nicht durch Erinnerung.** In der CI läuft ein
   `gate_runner`, der die Regeln prüft, die eine Maschine ehrlich prüfen *kann*:
   fehlt der unabhängige Review für eine riskante Änderung, driftet die
   Architektur-Doku vom echten Code, fehlt der Test zu einer fertigen Story —
   dann wird der Merge blockiert. Nicht „sollte man", sondern „geht nicht durch".

4. **Eine Quelle der Wahrheit, tool-unabhängig.** Die Methodik liegt als neutrales
   Markdown (`docs/process/`) im Repo. Adapter für Claude Code, GitHub Copilot,
   AGENTS.md u. a. sind dünn und zeigen darauf. Wechselt das KI-Werkzeug,
   degradiert nur die Bequemlichkeit — Methodik und Durchsetzung bleiben.

5. **Das Warum wird festgehalten.** Entscheidungen kommen in typisierte Decision
   Records (ADRs: *ist so* vs. *soll so werden* getrennt), das Journal hält fest,
   was das git-log nicht zeigt, und eine Feature-Registry verknüpft User-Story →
   Akzeptanzkriterium → Test. Kontext geht zwischen Sessions nicht verloren.

Alles jenseits des Kerns sind **zuschaltbare Module** (Architektur-Prüfung,
Security-Floor, Contract-/Parity-Prüfung, GitHub-Issues als SSOT, Effizienz-
Telemetrie …). Ein Wegwerf-Skript installiert nichts davon; ein Mehrsession-
Produkt schaltet zu, was es braucht.

---

## Für Entwickler:innen

**Wie sich das im Alltag anfühlt.** Du beschreibst deine Aufgabe in normaler
Sprache. Der Prozess (bzw. dein KI-Agent, der ihn kennt) nennt zuerst den Tier —
damit weißt du sofort, ob ein kurzer Test reicht oder ob es Plan und Review
braucht. Du arbeitest, committest auf einem Branch, öffnest einen PR; die Gates
laufen automatisch. Ist etwas rot, sagt die Meldung *warum* — kein Rätselraten.

**Warum das für dich gemacht ist.** Die häufigsten Wege, wie Arbeit (menschliche
wie KI-generierte) schiefgeht, sind vorhersehbar: man behauptet etwas über den
Code, ohne nachzusehen; man überspringt den Test, weil „läuft ja"; man verliert
nach einer Pause den Faden; man flickt an der Oberfläche statt die Ursache zu
fixen. Der Prozess stellt genau an diesen Stellen eine Schranke auf, damit du
nicht auf reine Disziplin angewiesen bist.

**Was du konkret gewinnst.**

- **Kein Über- oder Unterprüfen.** Der Tier sagt dir, wie viel Prozess deine
  Änderung verdient. Du steckst keine Stunde Zeremonie in einen Typo — und
  gehst umgekehrt bei einer Auth-Änderung nicht ungeschützt ins Risiko.
- **Schnelleres, sachlicheres Feedback.** Die Gates fangen die mechanischen
  Fehler ab, bevor ein Senior sie im Review findet. Der menschliche Review kann
  sich auf das Interessante konzentrieren, nicht auf „du hast den Test vergessen".
- **Wiedereinstieg ohne Gedächtnisverlust.** Branch-State und Journal
  rehydrieren nach einer Pause den Kontext — du weißt wieder, wo du standest und
  warum.
- **Explizite Review-Checkliste.** Was ein Review prüft (Vollständigkeit,
  Korrektheit, Security untrusted-input→sink, ein Owner, Tests) steht
  ausgeschrieben da. Standards lernst du durch Benutzung, nicht durch
  Auswendiglernen.
- **Die Prüfungen lügen nicht.** Ein grünes Gate heißt wirklich grün — das System
  behauptet nie Deckung, wo es nicht prüfen kann. Dem grünen Haken kannst du
  trauen.

---

## Für Management

**Wie es die Organisation berührt.** Der Prozess ist versioniertes Markdown plus
CI-Konfiguration im Repo — kein Server, kein Abo, keine zusätzliche Plattform. Er
wird per `copier` eingespielt und per `copier update` aktualisiert; ein roter Gate
blockiert einen Merge, sobald er (einmalig) als *required check* im Branch-Schutz
verdrahtet ist. Der Aufwand skaliert mit dem Risiko der Änderung, nicht mit ihrer
Größe.

**Warum das ein reales Problem löst.** KI-Agenten produzieren Code schneller, als
menschliche Reviews nachkommen — und mit denselben Fehlermustern wie unerfahrene
Entwickler:innen, nur in höherem Tempo. Prosa-Richtlinien werden dabei ignoriert;
das Einzige, was bei diesem Tempo hält, ist maschinelle Durchsetzung. Genau die
liefert der Prozess, und zwar tool-übergreifend statt an einen Anbieter gekettet.

**Was es geschäftlich bringt.**

- **Risiko-proportionaler Aufwand.** Billige Änderungen bleiben billig, riskante
  bekommen zwangsweise mehr Prüfung. Kein pauschaler Prozess-Overhead, aber auch
  keine ungeprüfte Auth-/Datenänderung.
- **Auditierbarkeit ohne Zusatzarbeit.** Jede riskante Änderung hinterlässt Plan,
  Review-Attestierung und — bei Grundsatzentscheidungen — einen Decision Record.
  Nachvollziehbarkeit für Compliance fällt als Nebenprodukt an, nicht als
  Extra-Projekt.
- **Kein Kopf-Monopol.** Der Prozess steckt im Repo, nicht im Kopf eines Seniors.
  Ein neuer Mensch oder Agent wird durch die Gates geführt; scheidet jemand aus,
  geht das Verfahrenswissen nicht mit.
- **Wirkung wird messbar, nicht behauptet.** Das Telemetrie-Modul liefert
  Kennzahlen — Wirksamkeit, Konvergenz (wie oft ein Review durchgeht), Tempo,
  Kosten, DORA-Change-Failure-Rate — jede mit Konfidenz und Maßnahme. Man sieht,
  ob der Prozess wirkt.
- **Keine Anbieterbindung.** Ein Wechsel des KI-Werkzeugs kostet Bequemlichkeit,
  nicht die Methodik oder ihre Durchsetzung. Die Investition ist portabel.
- **Verlässliche Ampel.** Weil das System nie „grün" meldet, wo es nicht prüfen
  kann (kein False-Green), ist ein grüner Lauf eine belastbare Aussage — die
  Basis dafür, Merges überhaupt an Gates zu binden.

---

## Ein konkreter Durchlauf

Aufgabe: *„Ergänze das Nutzerprofil um ein Feld, das in der API erscheint."*

1. **Tier-Einordnung:** berührt einen Contract (die API) und Persistenz ⇒
   **Tier 2**, unabhängig davon, dass der Diff klein ist.
2. **Vor dem Code:** Bei aktivem `github-issues`-Modul erzwingt ein Gate, dass ein
   Issue existiert; bei `contract-first` wird die Fähigkeit erst im geteilten Spec
   deklariert, bevor eine Oberfläche darauf baut.
3. **Plan:** ein kurzer Plan mit den betroffenen Dateien und den Tests, die das
   Akzeptanzkriterium beweisen sollen.
4. **Umsetzung + Tests:** der Test zur Story muss existieren, sonst blockt das
   Feature-Registry-Gate „fertig ohne Test".
5. **Review:** ein frischer, nicht-implementierender Blick prüft aus einem
   read-only Bundle — die Attestierung wird im Journal festgehalten; fehlt sie
   für einen gemergten Tier-2-Plan, schlägt das Review-Gate an.
6. **Entscheidung:** war eine Grundsatzfrage dabei (z. B. Nullable vs.
   Default-Wert), hält ein Decision Record sie fest, bevor der Code sie annimmt.

Ergebnis: die Änderung ist im Repo — mit Test, Review-Spur und Begründung. Nicht,
weil jemand daran gedacht hat, sondern weil die Gates es sonst nicht durchgelassen
hätten.

---

## Was der Prozess *nicht* ist (ehrliche Grenzen)

- **Kein Ersatz für Fachwissen.** Die Gates prüfen das maschinell Prüfbare — dass
  ein Review stattfand, nicht ob er klug war; dass ein Test existiert, nicht ob er
  das Richtige prüft. Urteilsvermögen bleibt menschlich.
- **Kein Security-Audit.** Der `security-floor` fängt den grep-baren Teil
  verbotener Muster ab — eine Grundlinie, keine vollständige Sicherheitsprüfung.
- **Kein Wahrheitsbeweis über Identität.** Das Review-Gate sieht nicht, *wer*
  reviewt hat; die Unabhängigkeit wird attestiert und arithmetisch geprüft, nicht
  forensisch bewiesen. Das benennt der Prozess offen, statt ein False-Green zu
  erzeugen.
- **Nicht für Wegwerf-Arbeit.** Für Prototypen, Einmal-Skripte und
  Single-Session-Aufgaben ist der Overhead netto negativ — dort nichts (oder nur
  das Minimalprofil) installieren.

Der Prozess rechnet sich für alles Mehrsession-, Multi-Agent- oder
Contract-/Persistenz-/Auth-behaftete — also dort, wo ein entkommener Fehler teuer
und ein vergessener Review wahrscheinlich ist.
