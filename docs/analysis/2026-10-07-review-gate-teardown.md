# Entscheidung: Review-Gate halbieren

Datum: 2026-10-07 · Status: **freigegeben** (Owner, 2026-10-07); A, C, D, E und F umgesetzt (CHANGELOG, Release nach v2.52), B umgesetzt nach Schattenbetrieb (Nachtrag 2) ·
Vorgänger: Position 8 der Abbauliste
(`docs/analysis/2026-08-06-lean-teardown-list.md`), damals beschlossen und
nicht umgesetzt; seitdem ist `check_review.py` von 563 auf 3.080 Zeilen
gewachsen.

## Anlass

Das Review-Gate ist die größte Fehlerquelle des Templates. Von den
Fix-Releases v2.49 bis v2.51.1 betrifft der größte Teil `check_review`,
`make_review_bundle` und `attest`. Die Releases v2.31 bis v2.33 hießen
„Stale-Check als Entscheidungstabelle“, „Verwerfen im Stale-Check“ und
„Refute der Restbefund-Fixes“: Sechs Refute-Runden griffen eine einzige
Prüfung an. Downstream blockierte sich der Prozess an einem Tag mehrfach
selbst, darunter ein Review-Gate, das nach 600 s abbrach. Jede neue
Garantie im Gate brachte neue Randfälle, und jeder Randfall wurde ein
Release.

## Was das Gate garantieren soll, und was nicht

**Behalten** — das ist der Zweck des Gates:

1. Eine gemergte Arbeit ab Tier 2 hat ein klärendes Review in ihrem Tier,
   mit den Unabhängigkeits-Flags, die das Tier verlangt, oder eine
   benannte `review-waived:`-Ausnahme.
2. Nach dem geprüften Stand kam kein ungeprüfter Code dazu.
3. Ein stehender Block wird nicht übergangen.
4. Ein reines Template-Update wird berechnet, nicht geprüft.
5. Ein volles Review deckt den ganzen Branch ab, nicht nur einen
   Ausschnitt (#160).

**Aufgeben** — Garantien, die die Mechanik heute zusätzlich liefert:

- Ein getippter statt berechneter `REVIEW`-Eintrag fällt nicht mehr auf.
- Ein Delta-Review ist nicht mehr als solches markiert.
- Ein im geprüften Bereich gelöschter Block-Eintrag wird nicht mehr
  rekonstruiert.

Die Begründung steht je Punkt unten.

## Die Entscheidungen

### A. Der Diff-Digest entfällt

`diff=<sha256>` ist `sha256(git diff base head)`
(`check_review.artifact_digest`). Er ist eine reine Funktion der beiden
SHAs, die die Zeile ohnehin trägt. Ein Commit-SHA adressiert seinen Inhalt
bereits: Wer `base` und `head` kennt, kennt den Diff. Das Nachrechnen
beweist nichts, was die SHAs nicht schon festlegen. Es fängt nur eine
Zeile, deren Digest jemand von Hand getippt hat. Seit v2.40 schreibt aber
`attest.py` jede Zeile, also tippt niemand mehr.

Was dafür heute existiert und entfällt:

- die Digest-Formel mit festgenagelter git-Konfiguration;
- das Nachrechnen für alte Zeilen über alle `core.abbrev`-Werte von 4 bis 16
  (`_legacy_digests`);
- das Integritäts-Ledger mit Cache und Fetch-Stempel;
- die Integritätsprüfung je Eintrag;
- die Delta-Digests (`mode=delta`).

Das sind zusammen rund 400 Zeilen in `check_review` und 80 in Bundle und
`attest`.

**Aufgegebene Garantie:** Eine Zeile mit erfundenem `head` fällt nicht mehr
durch einen falschen Digest auf. Das tat sie auch vorher nicht, denn
`attest` rechnet den Digest für jeden `head`, den man ihm gibt. Die
Agenten, die diese Zeilen schreiben, sind keine Angreifer. Gegen
Nachlässigkeit hilft der einzige Schreiber `attest.py`, nicht ein Hash.

### B. „Kein ungeprüfter Code“ wird ein Inhaltsvergleich statt einer Historientabelle

Heute entscheidet eine Tabelle über die Historie zwischen dem geprüften
Head und dem Tip. Sie unterscheidet:

- Merges von `main`;
- Konfliktauflösungen;
- „evil merges“;
- `-s ours`;
- Rebase und Amend;
- Mitpassagiere im Zug.

Dazu kommt eine eigene Erkennung für Merges, die eine geprüfte Änderung
verwerfen. Zusammen sind das rund 600 Zeilen und 66 Tests.

**Neue Regel:** Eine Datei gilt als ungeprüft, wenn ihr Inhalt am Tip
keinem dieser Stände entspricht:

- dem geprüften Head der Arbeit;
- dem Integrationszweig;
- dem geprüften Head eines anderen Passagiers desselben Pushs.

Bookkeeping unter `.process-work/` zählt nicht. Dieser Vergleich auf drei
Ebenen deckt ab, ohne die Historie zu lesen:

- **Merge von `main` nach dem Review:** Die Datei entspricht `main`. Sie ist
  geprüft, ein neues Review braucht es nicht.
- **Konfliktauflösung, evil merge, `-s ours`:** Das Ergebnis entspricht
  weder dem Head noch `main`, also gilt die Datei als ungeprüft.
- **Neuer Commit, Amend, Rebase mit eigener Änderung:** Der Inhalt ist
  neu, also gilt die Datei als ungeprüft.
- **Verworfene geprüfte Änderung:** Der Inhalt entspricht wieder `main`.
  Er ist geprüft, und der Verlust zeigt sich als fehlende Änderung im
  Produkt, nicht als Gate-Fund. Das ist dieselbe Lage wie bei einem
  späteren Revert.

**Bekannte Grenze:** Ändern zwei Passagiere eines Zugs dieselbe Datei und
git führt beide sauber zusammen, entspricht das Ergebnis keinem Stand. Die
Datei gilt dann als ungeprüft, und die beiden fahren in getrennten Zügen.
Heute löst eine Sonderregel für Mitpassagiere das auf. Getrennte Züge
kosten eine Zugfahrt, keine Review-Runde.

### C. `base=` und die Fork-Point-Prüfung bleiben

Ein volles Review muss den ganzen Branch abdecken, nicht einen Ausschnitt
(#160). Dafür genügt eine einzige Prüfung: `base` ist der Fork-Point von
`head` mit dem Integrationszweig. Das sind etwa 35 Zeilen statt heute 130
über Bereichsgrenzen und Remote-Refs.

### D. Delta-Bundles bleiben als Lesehilfe, nicht als eigene Review-Art

`make_review_bundle.py --since <sha>` bleibt erhalten. Ein solches Bundle
zeigt den Fix-Diff, die offenen Funde der letzten Runde und die Dateien,
die der Fix berührt. Die `REVIEW`-Zeile bindet aber immer den vollen Head.
`mode=delta`, die Kette der Tier-3-Delta-Anker und die Regeln, wann ein
Delta zu weit greift, entfallen. Das sind etwa 250 Zeilen und rund 25
Tests.

**Aufgegebene Garantie:** Ein Pass, der auf einem Delta-Bundle beruht, ist
nicht mehr als solcher erkennbar. Er band schon bisher den Digest des
ganzen Branches. Ob der Prüfer nur den Fix oder alles gelesen hat, konnte
das Gate nie sehen.

### E. Der stehende Block wird am Tip gelesen

Heute rekonstruiert das Gate Block-Einträge, die im gepushten Bereich
gelöscht oder bei einem Merge verloren gingen. Dafür liest es die Blobs
jedes Commits im Bereich, das sind etwa 125 Zeilen. Künftig liest es den
Journal-Stand am Tip. Ein gelöschter Block-Eintrag ist ein sichtbarer Diff
im Journal und keine Lücke, die ein Agent unbemerkt nutzt.

### F. Altdaten bleiben gültig

Alte `REVIEW`-Zeilen mit `diff=` und `mode=` bleiben lesbar. Die Felder
werden ignoriert, kein Eintrag wird ungültig. Pässe ohne Head zählen wie
bisher nur, solange kein Pass mit Head existiert.

## Umfang

| | heute | danach |
|---|---:|---:|
| `check_review.py` | 3.080 | ≈ 1.600 |
| `make_review_bundle.py` + `attest.py` | 1.630 | ≈ 1.450 |
| Tests, die entfallen | – | ≈ 95 |
| Tests, die umgeschrieben werden (Stale-Check) | – | ≈ 60 |

Die Zahlen beruhen auf einer Bestandsaufnahme Abschnitt für Abschnitt. Die
Grammatik, die Ablageorte der Records, die Tier-Präsenz, die Erkennung des
Integrationszweigs, die berechneten Template-Updates und `_unhomed_plans`
bleiben unverändert.

## Reihenfolge

Jeder Schritt ist ein eigener Commit mit grüner Suite:

1. Alt-Zeilen tolerant lesen (F).
2. Digest und Integritäts-Ledger entfernen (A).
3. Delta-Modus und Tier-3-Ankerkette entfernen, `--since` als Lesehilfe
   behalten (D).
4. Stale-Check durch den Inhaltsvergleich ersetzen (B), zuerst parallel zur
   Tabelle gegen Kennis echte Historie. Unterschiede werden einzeln
   begründet, bevor die Tabelle fällt.
5. Den stehenden Block am Tip lesen (E).
6. Die Doku nachziehen: `verification-independence.md`, `/review` und die
   Bundle-Präambel.

Schritt 4 ist der heikle und läuft als Tier 3 mit Refute vor der ersten
Runde. Die übrigen Schritte sind reine Entfernungen: Die verbleibenden
Tests müssen grün bleiben, und Kennis Journal muss ohne neuen harten Fehler
durchlaufen.

## Was ausdrücklich nicht passiert

- **Kein neues Gate, kein neues Feld, keine neue Phase.**
- **Die Unabhängigkeits-Arithmetik bleibt unverändert:**
  `bundle,non-implementing`, `cross-model` oder `single-family`.
- **Die Pflicht zum Review je Tier bleibt unverändert.**

## Nachtrag: Stand nach der Umsetzung

A, C, D, E und F sind umgesetzt. B (Inhaltsvergleich statt Historientabelle)
ist bewusst noch nicht umgesetzt. Bei der Umsetzung zeigte sich eine Lücke
der Regel, wie sie oben steht: Ändern Branch und `main` verschiedene Stellen
derselben Datei, entspricht das zusammengeführte Ergebnis weder dem Head
noch `main`. Die Regel würde es als ungeprüft melden, und jeder Merge von
`main` in einen solchen Branch bräuchte ein neues Review. Die bisherige
Logik rechnet dafür den Auto-Merge nach (`_merge_own`).

B braucht deshalb als dritten erlaubten Stand den sauberen Auto-Merge von
Head und `main` (und im Zug den der Passagiere). Danach muss B, wie unter
„Reihenfolge“ vorgesehen, im Schattenbetrieb gegen Kennis echte Historie
laufen. Das ist ein eigenes Paket mit Tier 3 und Refute.

## Nachtrag 2: B umgesetzt, wie die Regel jetzt lautet

Die Regel aus dem Abschnitt B hielt dem Schattenbetrieb und dem Refute in
mehreren Punkten nicht stand. Die umgesetzte Fassung:

**Der eine geprüfte Stand.** Eine Datei am Tip gilt als geprüft, wenn ihr
Inhalt (Modus und Objekt) git's eigenem Merge entspricht: aus dem
Integrationszweig dort, wo der Tip ihn zuletzt traf (jede Merge-Basis von
Tip und Integrations-Ref), mit dem geprüften Head und mit jedem weiteren
klärenden Review, dessen Head der Tip enthält. Ein Pfad, der in diesem Merge
kollidiert, gilt nie als geprüft, auch nicht bei Konflikten ohne Marker
(modify/delete, rename/delete, Datei wird Symlink).

**Wer ganz zählt.** Ein Review zählt ganz, wenn der Tip seinen Head enthält,
wenn seine Basis auf `main` liegt, oder wenn seine Basis selbst geprüfter
Inhalt ist: das, was die ganzen Reviews darunter gemergt ergeben,
Buchhaltung ausgenommen. Es hat dann alles gesehen, was es über geprüften
Inhalt hinaus bringt (Schattenbetrieb: Eine Arbeit, die ihren Merge von
`main` geprüft hat, trug den Attest-Commit der vorigen Arbeit als Basis). Ein Review mit einer Basis über `main` bürgt nur für
die Dateien seines eigenen Bereichs. Ein Head, den ein Rebase ersetzt hat,
braucht seine Fork-Point-Basis, um ganz zu zählen. Ohne Integrationszweig
ist der Head der einzige geprüfte Stand. Jeder git-Fehler ist „veraltet“;
einen schwächeren Ersatzvergleich gibt es nicht mehr. Damit ist Kenni #2439
erledigt: Ein `merge-tree`-Timeout las einen Revert-Merge als frisch.

**Korrekturen gegenüber Abschnitt B:**

1. **Der Head allein ist kein geprüfter Stand** (Schattenbetrieb). Für
   Dateien, die nur `main` geändert hat, entspricht ein `-s ours`-Merge genau
   dem Head; `main`s Fix wäre still verschwunden.
2. **Mehrere geprüfte Arbeiten zusammen** (Schattenbetrieb). In Kennis
   Historie liegen drei Arbeiten auf einem Branch, jede ändert die
   Feature-Registry. Ihr sauberer gemeinsamer Merge gilt als geprüft. Das
   hebt auch die Grenze für Zug-Passagiere auf derselben Datei auf. Gefaltet
   werden nur die jüngsten Heads: Eine spätere Runde, die einen Merge von
   `main` geprüft hat, deckt die Konfliktauflösung darin.
3. **Drops bleiben ein Fund** (Refute). Abschnitt B wollte einen Merge, der
   die geprüfte Änderung zugunsten von `main` verwirft, durchlassen. Dieselbe
   Regel ließ aber auch einen späteren Commit durch, der eine geprüfte Datei
   auf `main`s Stand zurücksetzt, etwa den Guard einer geprüften Route. Der
   Stand „Merge-Basis selbst“ entfällt deshalb. Jede Konfliktauflösung, auf
   welche Seite auch immer, braucht eine neue Runde.
4. **Jeder Zug-Träger wird geprüft** (Refute). Tragen zwei Zug-Merges
   denselben Head, wird jeder Passagier-Tip beurteilt, nicht nur der jüngste.
5. **Ein Slice-Review, dessen Head ein Rebase ersetzt hat** (Refute), bürgt
   nur für seinen Bereich. Sonst hätte ein ungeprüfter Commit unterhalb
   seiner Basis als geprüft gegolten.

**Was sich gegenüber der Historientabelle ändert:** Ein Rebase oder Merge
von `main` ohne Konflikt lässt das Review gültig, wenn es eine
Fork-Point-Basis hat (#158). Neu strenger: Ein Konflikt, der auf die eigene
Seite aufgelöst wird, gilt als ungeprüft; die Tabelle ließ das durch.
Voraussetzung ist git 2.38 (`merge-tree --write-tree`).

**Schattenbetrieb gegen Kennis Historie.** 500 Urteile über die 250 zuletzt
gelandeten Pässe, jeweils am Branch-Tip beim Einsteigen in den Zug und am
gelandeten Merge auf `main`. Als andere Reviews zählten wie im Gate nur
klärende Pässe. 494 Urteile stimmen überein, 6 weichen ab, alle erklärt:

- **2 × alt veraltet, neu geprüft (Arbeit 2166).** Die Tabelle meldete einen
  Drop, weil eine frühere Runde einen anderen Stand von `check_review.py`
  und `.copier-answers.yml` gesehen hatte. Den Endstand beider Dateien
  haben spätere klärende Pässe derselben Arbeit geprüft. Hier lag die
  Tabelle falsch.
- **4 × alt geprüft, neu veraltet (Arbeiten 1918 und 1919).** Beide bauen
  auf Arbeit 1917 auf, deren einziger klärender Pass eine alte Delta-Runde
  mit einer Basis ist, die kein Fork-Point ist. Solche Zeilen weist das Gate
  seit v2.53 schon vorab als ungültig zurück; für neue Reviews kann das
  nicht vorkommen.

Unterwegs deckte der Schattenbetrieb drei Fehler des Entwurfs auf, die oben
als Korrekturen stehen (der Head allein, mehrere Arbeiten zusammen, die
Faltung nur der jüngsten Heads), und zwei weitere Verfeinerungen: Eine
spätere Runde, die einen Merge von `main` als Head geprüft hat, deckt die
Auflösung darin (Arbeit 2197), und eine Basis aus geprüftem Inhalt zählt
ganz (Arbeiten 1917 bis 1919). Ein binärer Screenshot-Konflikt, der
`main`s Neuaufnahme verwarf, wäre mit der Tabelle durchgerutscht; ohne
die spätere Runde meldet ihn der Inhaltsvergleich.

**Laufzeit.** Die Tabelle brauchte im Median 25 s pro Urteil, der
Inhaltsvergleich 0,05 s, höchstens 2,3 s.

**Offen, schon vorher so:** Ein lokales `main`, das `origin/main` nur um
Merges voraus ist, gilt als Integrationsstand. Enthält es ungeprüften Code,
sieht das Gate ihn nicht, weder mit der Tabelle noch mit dem Inhaltsvergleich.

Entfallen sind `_dropped_by_merge`, `_merge_own`, die Tabelle über die
Historie, `work_bases` und das Feld `dropped`.
