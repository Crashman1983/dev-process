# Was ist neu in dev-process

Für alle, die wissen wollen, was eine neue Version bringt, ohne die Technik
im Detail zu kennen. Je Version ein paar Sätze: was sich für ein Projekt
ändert, das die Vorlage nutzt, und was es davon hat. Die vollständigen
technischen Einzelheiten stehen im [CHANGELOG](CHANGELOG-DE.md).

English version: [NEWS.md](NEWS.md).

## v2.75.0 — Ein Template-Update wird einmal geprüft, auch wenn dazwischen anderes gemergt wird

Ein Projekt, das die Vorlage aktualisiert, quittiert und prüft das Update
einmal; andere Arbeit, die in der Zwischenzeit gemergt wird, zwingt es nicht
mehr zum Neuanfang. Ein in einem Plan zitiertes Beispiel kann die
Review-Einträge nicht mehr täuschen, die Zeilen, die einen Angriff auf eine
Änderung zusammenfassen, und der Beweis, dass ein Fix einen Test grün gemacht
hat, schreiben Werkzeuge aus dem, was wirklich lief, und ein neuer Bericht
zeigt, wie viel der Arbeit auf welchem Modell läuft.

## v2.74.2 — Eine Suite, die nach einem Fehler weiterläuft, zählt wieder

Ein Projekt, dessen Testsuite auch nach einem Fehler alle Stufen weiterfährt,
bekommt wieder sein Testzertifikat. Seit 2.74.0 hielt diese Betriebsart den
Merge auf, obwohl sie keinen Fehler verdeckt.

## v2.74.1 — Ein Review mit dem Familiennamen zählt wieder

Ein Projekt, das ab einer bestimmten Stufe nur die eigene Modellfamilie
freigeben lässt, nimmt jetzt auch Reviews an, die nur den Familiennamen
tragen. So schreibt es der Review-Befehl vor. Bisher fielen solche Reviews
stillschweigend heraus und hielten den Merge auf.

## v2.74.0 — Ein Projekt passt die Vorlage über Antworten an statt über eigene Dateien

Ein Projekt kann jetzt bei der Einrichtung wählen, ob seine Pläne, Journale und
Notizen Englisch oder in der Gesprächssprache geschrieben werden. Weitere
Wünsche, die ein Projekt bisher nur mit eigenen Fassungen von Vorlagedateien
umsetzen konnte, sind jetzt Einstellungen: dass ab einer Risikostufe ein Prüfer
der eigenen Modellfamilie zustimmen muss, dass jeder Plan sein Design-Regelwerk
nennt, und welche Messungen zu welchem Datum fällig sind. Bei der Übergabe an
Hilfsmodelle ist klarer geregelt, was mitgeht und was zurückkommt. Mehrere
Fehler aus dem Betrieb sind behoben. Der CHANGELOG erklärt je Version, warum
sich etwas geändert hat und wozu es führt, auf Deutsch und Englisch.

## v2.73.0 — Ein zweites Modell prüft mit, und Projekte ohne bezahltes CI sind vorgesehen

Ist auf dem Rechner die Codex CLI installiert, kann die Vorlage Arbeit und
Prüfungen jetzt auch an Codex-Modelle geben. Eine solche Prüfung zählt
vollwertig: Sie wird gegen den geprüften Stand abgeglichen und erst dann
festgehalten. Ein Modell einer anderen Familie gilt nur dann als
unabhängiger Prüfer, wenn feststeht, dass es nicht auch den Code geschrieben
hat. Ist Codex einmal nicht erreichbar, nennt die Vorlage den Ausweg und
hält fest, warum er nötig war. Pläne sagen außerdem je Arbeitspaket, ob ein
kleineres Hilfsmodell es übernimmt, und die Vorlage misst, ob sich das
lohnt. Projekte ohne bezahltes GitHub-CI wählen jetzt `manual`: Die
Prüfschritte bleiben als Knopf zum Selbststarten, und verlässlich prüft der
Push.
Eigene Regeln eines Projekts zu den Prozess-Dokumenten stehen jetzt in
eigenen Ergänzungsdateien statt in den Dokumenten der Vorlage. Ändert eine
neue Version eine Stelle, auf die so eine Ergänzung aufbaut, meldet die
Prüfung das, bis jemand nachgesehen hat, ob beides noch zusammenpasst.

## v2.72.0 — Was ein Projekt gelernt hat, kommt zurück in die Vorlage

Kenni, das erste Projekt auf dieser Vorlage, hatte in den letzten Wochen
einiges selbst verbessert. Vieles davon steckt jetzt in der Vorlage, damit
das Projekt nicht davonläuft und andere Projekte es auch haben. Dazu gehört
eine Bestätigung, dass Tests gelaufen sind, die bei Projekten mit
Testgruppen genau sagt, welche liefen; dazu Zeitmessungen je Testgruppe, Pläne, die jeder
Aufgabe die genaue Fundstelle mitgeben, sodass ein kleines Modell weniger
sucht (gemessen: rund ein Drittel der Schritte), und Lehren aus dem Betrieb.
Nach dem Update laufen die Tests vor dem ersten Push einmal neu. Zwei
größere Teile warten noch auf eine Entscheidung des Owners.

## v2.71.0 — Eine Prüfung zählt nur mit Beleg

Eine Prüfung gilt jetzt erst als bestanden, wenn ihre Belege vorliegen. Zu
jeder Anforderung muss ein Test genannt sein, der fehlschlagen würde, wenn
das Verhalten kaputtgeht. Änderungen an den Prüfwerkzeugen selbst müssen
vorher gezielt angegriffen worden sein. Wo ein zweites KI-Modell als
Gegenleser vorgesehen ist, muss es gelaufen sein. Einen Plan prüft kein
kleineres Modell als das, das ihn geschrieben hat. Wer bewusst
darauf verzichtet, schreibt einen Satz mit Grund dazu; so bleibt sichtbar
und zählbar, wo abgekürzt wurde. Anlass war eine Nacht, in der sechs
Änderungen glatt durchgingen und eine Nachprüfung sechs schwere Fehler fand.

## v2.70.0 — Wissen, das schon da ist, wird gefunden

Viele Prüfrunden scheitern, weil ein Agent etwas Bestehendes nicht kannte:
eine Einstellung, einen Hintergrunddienst, eine Stelle, die dieselben Daten
liest. Projekte können solche Dinge jetzt automatisch aus ihrem Code
auflisten lassen, und jeder Plan bekommt die Einträge, die ihn betreffen,
gleich mitgeliefert. Wer etwas ändert, das andere lesen, muss nachweisen,
dass er alle Leser gesucht hat. Und es gibt ein Protokoll wie dieses hier
auch für Projekte: Jede Änderung, die ein Nutzer bemerkt, bekommt ein paar
verständliche Sätze, gesammelt in einer Datei „Was ist neu“.

## v2.69.0 — Veraltete Pläne fallen auf

Bevor ein Agent mit der Umsetzung beginnt, prüft der Prozess jetzt, wie alt
der Plan ist: Wie weit ist der Code seitdem gelaufen, und wie viele dieser
Änderungen betreffen genau die Dateien, die der Plan nennt? Anlass war ein
Plan, der über 1000 Änderungen alt war. Vorerst wird nur gemessen; später
kann der Prozess warnen oder anhalten. Außerdem werden Umstellungen vorher in
einer frischen Umgebung durchgespielt, Releases unterscheiden reine Updates
von Umstellungen mit Projektschritten, und ein Arbeiter, der lange stumm
bleibt, weckt den Koordinator.

## v2.68.0 — Jede Prüfung wird gemessen

Jede automatische Prüfung schreibt jetzt auf, was sie kostet und was sie
findet. So lässt sich belegen, welche Prüfungen sich lohnen. Eine Prüfung
kann zur Probe nur beobachten, statt zu blockieren — aber nur mit Zustimmung
des Owners und nie bei den Kernprüfungen. Ein Wächter macht eine Lockerung
selbständig rückgängig, sobald sie Schaden anrichtet. Dazu kommen eine
wöchentliche und eine monatliche Auswertung.

## v2.67.0 — Der Prozess kann sich selbst verbessern

Wiederkehrende Engpässe werden zu begrenzten Versuchen: eine Annahme, vorher
festgelegte Erfolgskriterien, ein Probelauf mit Ablaufdatum und eine
Entscheidung, die nicht trifft, wer die Änderung gebaut hat. Gleichzeitig
misst der Prozess jede Arbeit vom Start bis zur Auslieferung: wie lange daran
gearbeitet und wie lange gewartet wurde und was sie gekostet hat.

## v2.66.0 — Weniger Verwechslungen bei Plänen

Koordinator und Merge-Zug erkennen jetzt nach derselben Regel, welche Pläne
zu einer Arbeit gehören. Vorher konnte eine Arbeit an einer fremden Prüfung
hängenbleiben oder eine nötige Prüfung übersehen. Fällt eine Planprüfung
durch oder ist sie unklar, beginnt die Umsetzung nicht.

## v2.65.0 — Ein kaputter Rechner wird erkannt

Vor jedem Testlauf prüft der Prozess, ob der Rechner bereit ist. Ein
defekter Rechner meldet sich dann als solcher, statt als scheinbar
fehlgeschlagene Tests, die niemand verursacht hat.

## v2.64.0 — Ein einheitlicher Testablauf

Welche Tests eine Änderung braucht, folgt aus einer Zuordnung im Projekt
statt aus Handarbeit. Schwere Testläufe kommen sich nicht mehr in die Quere,
und ein Stand, der schon geprüft wurde, wird nicht noch einmal getestet. Das
spart Wartezeit bei jedem Push und jedem Merge.

## v2.63.0 — Weniger unnötige Prüfrunden

Der Prozess erkennt selbst, wann ein Plan geprüft werden muss, statt
versehentlich eine Codeprüfung ohne Code zu starten. Ein Einwand eines
zweiten Modells hält die Arbeit nur noch auf, wenn er ernst genug ist.

## v2.62.0 — Vier Lücken aus dem Alltag geschlossen

Vier Fehler in den automatischen Prüfungen, die im täglichen Betrieb eines
Projekts aufgefallen waren, sind behoben. Unter anderem blieben gültige
Prüfungen nicht mehr wegen einer alten Zeile hängen, und Sicherheitsscanner
schlagen beim Abschluss einer Arbeit nicht mehr an.

## v2.61.0 — Die Einstufung wird nachgerechnet

Die Prüfung fragt zuerst, ob eine Änderung wirklich so harmlos ist, wie
angegeben. Wird ein Wert geändert, etwa eine Version oder ein Pfad, muss
jede Stelle, die ihn verwendet, nachweislich gefunden werden. Die
Update-Hilfe startet bei `--help` nicht mehr versehentlich ein Update.

## v2.60.0 — Einfache Aufgaben auf dem kleinen Modell

Genau beschriebene Aufgaben ohne eigene Entscheidung erledigt jetzt ein
kleines, günstiges Modell. Aufgaben, die ein Urteil brauchen, bleiben beim
großen Modell. Das senkt die Kosten, ohne die Qualität der Entscheidungen
anzutasten.
