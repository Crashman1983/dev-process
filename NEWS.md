# Was ist neu in dev-process

Für alle, die wissen wollen, was eine neue Version bringt, ohne die Technik
im Detail zu kennen. Je Version ein paar Sätze: was sich für ein Projekt
ändert, das die Vorlage nutzt, und was es davon hat. Die vollständigen
technischen Einzelheiten stehen im [CHANGELOG](CHANGELOG.md).

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
