# Design: Automatisierter Scalable-Invest-Agent

Datum: 2026-09-02  
Status: Vom Nutzer inhaltlich freigegeben; Umsetzung noch ausstehend

## Ziel

Ein Agent startet montags bis freitags um 08:30, 12:30, 15:30, 18:30 und 22:30 Uhr in der Zeitzone Europe/Berlin eigenständig einen vollständigen GitHub-Lauf für die Strategien A, B und C. Er überwacht den von ihm ausgelösten Lauf bis zum Abschluss, prüft anschließend ausschließlich die neu erzeugten Ergebnisse, gleicht sie mit dem privaten Scalable-Depot ab und liefert nach jedem Lauf eine vollständige Auswertung.

Bei einem gültigen Kauf-, Verkaufs- oder Stoppsignal erstellt der Agent eine vollständige Scalable-Ordervorschau. Eine Order darf erst nach der für genau diese Vorschau erforderlichen separaten ausdrücklichen Bestätigung des Nutzers übermittelt werden.

## Bestehende Grundlage

Repository: schnapsy85/strategy-c-hybrid  
Branch: main  
Zentraler Workflow: .github/workflows/daily_scan.yml

Der Workflow führt bereits folgende Schritte aus:

1. Repository auschecken und mit main synchronisieren.
2. Python und Abhängigkeiten einrichten.
3. Tests ausführen.
4. gemeinsame Marktdaten aktualisieren und Strategie C scannen.
5. Strategie A scannen.
6. Strategie B scannen.
7. Ergebnisse nach data und docs synchronisieren.
8. geänderte Daten und Scanergebnisse nach main schreiben.

Maßgebliche Ergebnisdateien:

- data/strategy_a_latest.json
- data/strategy_b_latest.json
- data/latest.json

## Agentengesteuerter Workflow-Start

Der Agent soll jeden geplanten Lauf selbst auslösen. Dafür wird eine technisch neutrale Steuerdatei angelegt:

- .automation/run-request.json

Sie enthält ausschließlich technische Daten wie Lauf-ID, angeforderten Zeitpunkt und Zeitfenster. Sie enthält keine Depotdaten, Orderdaten, Budgets oder Broker-IDs.

Der Workflow daily_scan.yml erhält zusätzlich einen Push-Trigger, der ausschließlich auf Änderungen dieser Steuerdatei reagiert. Der vorhandene Zeitplan im Workflow wird entfernt, damit keine doppelten automatischen Läufe entstehen. Der manuelle workflow_dispatch-Start bleibt erhalten.

Zu jedem geplanten Zeitpunkt:

1. führt der Agent einen lesenden Verbindungstest für GitHub und Scalable aus;
2. liest er die aktuelle Steuerdatei samt Blob-SHA;
3. ersetzt er ihren Inhalt durch eine neue eindeutige Laufanforderung;
4. verwendet er den entstandenen Commit-SHA als Korrelations-ID;
5. sucht er den dazugehörigen Lauf von daily_scan.yml;
6. überwacht er genau diesen Lauf bis zum Status completed.

Die fünf Zeitpunkte gelten ausschließlich montags bis freitags. Wochenendläufe finden nicht statt. Die Zeitzone Europe/Berlin muss erhalten bleiben, damit Sommer- und Winterzeit automatisch berücksichtigt werden.

## Workflow-Überwachung und Wiederholungen

GitHub-Zugriff und Startanforderung erhalten jeweils bis zu zwei Wiederholungsversuche bei vorübergehenden Verbindungsfehlern.

Sobald der Workflow-Lauf gefunden wurde, prüft der Agent Status, Conclusion, Laufnummer, Versuch, Startzeit und Endzeit. Bei einem fehlgeschlagenen Lauf:

1. liest der Agent Jobs, Schritte und verfügbare Fehlerprotokolle;
2. startet er einmal gezielt die fehlgeschlagenen Jobs neu;
3. überwacht er den neuen Versuch erneut bis zum Abschluss;
4. beendet er bei erneutem Fehlschlag den Lauf ohne Strategie- oder Orderentscheidung;
5. liefert er einen vollständigen Fehlerbericht.

Unbekannte oder nicht eindeutig zuordenbare Läufe dürfen nicht als Erfolg gewertet werden.

## Validierung der Scanergebnisse

Nach einem erfolgreichen GitHub-Lauf liest der Agent die drei Ergebnisdateien neu ein. Für jede Strategie werden mindestens folgende Prüfungen durchgeführt:

- Status der Ergebnisdatei;
- Erzeugungszeitpunkt gehört zum überwachten Lauf;
- neuester vollständig abgeschlossener Börsentag;
- Freshness-Prüfung;
- Universum und Abdeckungsquote;
- fehlende oder zu kurze Historien;
- unterdrückte Signale;
- Marktfilter;
- Kauf-, Watch- und Exit-Signale.

Ein GitHub-Lauf gilt für die Agentenauswertung nur dann als fachlich erfolgreich, wenn die Dateien zum überwachten Lauf gehören und die jeweilige Strategie ihre eigenen Datenqualitätsregeln erfüllt.

Bei stale_data, partial_data oder einer fehlgeschlagenen Freshness-Prüfung werden Signale der betroffenen Strategie gesperrt. Andere fehlerfreie Strategien können weiterhin ausgewertet werden, sofern keine gemeinsame Datenquelle beschädigt ist.

## Private Trennung der Strategiepositionen

Das Repository ist öffentlich. Deshalb dürfen dort keine persönlichen Depotwerte, exakten Bestände, Broker-Portfolio-IDs, Order-IDs, Transaktionshistorien oder privaten Performancewerte gespeichert werden.

Die Zuordnung offener Strategiepositionen erfolgt privat in Scalable über drei Portfolio-Gruppen:

- Strategie A
- Strategie B
- Strategie C

Bestehende Strategiepositionen werden der korrekten Gruppe zugeordnet. Andere Fonds, ETFs, Derivate, Sparpläne und private Positionen bleiben ungruppiert oder in ihren bisherigen Gruppen und werden vom Agenten nicht verändert.

Nach einer bestätigten und nachweislich ausgeführten neuen Strategieorder ordnet der Agent die neue Position bei einem Folgelauf der passenden Strategiegruppe zu. Eine Position wird erst zugeordnet, wenn sie tatsächlich im Bestand vorhanden ist.

Startkapital, realisierte historische Strategietrades und bereits bearbeitete Signale werden ausschließlich im privaten Agentenauftrag geführt, nicht im öffentlichen Repository.

## Scalable-Prüfung

Nach validierten GitHub-Ergebnissen liest der Agent:

- die drei Strategiegruppen;
- zugehörige Bestände und aktuelle Kurse;
- relevante offene, ausstehende und abgeschlossene Transaktionen;
- aktiven Stop- oder Verkaufsorders;
- den zur Strategie gehörenden Kapitalstatus.

Scalable-Zugriffe erhalten bis zu zwei Wiederholungsversuche. Bleiben Depot-, Kurs-, Transaktions- oder Budgetdaten unvollständig, wird keine Ordervorschau erstellt.

Andere Depotpositionen dürfen weder für das Strategiebudget angerechnet noch verkauft, gruppiert, mit Stops versehen oder anderweitig verändert werden.

## Signal- und Orderlogik

Die bestehenden Regeln der Strategien A, B und C werden nicht verändert.

Vor einer Ordervorschau prüft der Agent mindestens:

1. Strategie und Signalstatus sind gültig.
2. Signaldatei und Signalzeitpunkt sind aktuell.
3. Dasselbe Signal wurde noch nicht verarbeitet.
4. Es besteht keine Position und keine kollidierende offene Order.
5. Bei bestehenden Positionen wird die vorgesehene Exit- und Stopplogik geprüft.
6. Der aktuelle Scalable-Kurs ist nicht veraltet.
7. Gap-Regel, Handelbarkeit, Handelsplatz und Kapitalgrenzen sind erfüllt.
8. Positionsgröße und Stop werden mit dem realen ausführbaren Kurs neu berechnet.

Erst danach darf eine Kauf-, Verkaufs- oder Stop-Ordervorschau erstellt werden.

Die vollständige menschlich lesbare Scalable-Vorschau wird unverändert und vollständig präsentiert. Für jede einzelne Order ist eine separate ausdrückliche Bestätigung in einer späteren Nutzerinteraktion erforderlich. Bestätigungen dürfen nicht auf andere oder spätere Vorschauen übertragen werden.

Ist eine Vorschau abgelaufen, erstellt der Agent eine neue Vorschau und verlangt erneut eine Bestätigung.

Bei Timeout oder unbekanntem Übermittlungsergebnis wird eine Order niemals blind wiederholt. Zuerst werden Transaktionen, offene Orders und Bestand geprüft, damit keine Doppelorder entsteht.

## Vollständiger Bericht nach jedem Lauf

Nach jedem der fünf täglichen Läufe erhält der Nutzer eine vollständige Auswertung, auch wenn keine Signale vorliegen.

Der Bericht enthält:

- geplantes Zeitfenster und tatsächliche Startzeit;
- GitHub-Commit-SHA, Workflow-Laufnummer, Versuch, Laufzeit und Ergebnis;
- Datenstand, Status, Freshness und Abdeckung für A, B und C;
- Marktfilter und relevante Datenqualitätswarnungen;
- neue Kauf-, Watch- und Exit-Signale;
- offene Strategiepositionen mit Einstieg, aktuellem Kurs, Gewinn oder Verlust, Stop und Stop-Abstand;
- aktive oder ausstehende Strategieorders;
- freies Strategiekapital und Strategiegesamtwert;
- klare Handlungsempfehlung je Strategie;
- vollständige Ordervorschau, wenn eine Aktion erforderlich ist;
- genaue Fehlerbeschreibung und getroffene Wiederholungen bei technischen Problemen.

Wiederholte Tagesläufe dürfen dasselbe Signal nicht erneut als neues Signal melden oder eine zweite Ordervorschau erzeugen. Die Deduplizierung berücksichtigt Strategie, Ticker beziehungsweise ISIN, Signaltyp, Signaldatum, vorhandene Position und offene Order.

## Sicherheit und Datenschutz

- Keine Scalable-Zugangsdaten in GitHub.
- Keine persönlichen Broker-, Bestands- oder Transaktionsdaten im öffentlichen Repository.
- Keine Order ohne aktuelle Vorschau und separate Bestätigung.
- Keine automatische Wiederholung bei unbekanntem Orderstatus.
- Keine Nutzung oder Veränderung von Nicht-Strategiepositionen.
- Keine Signale aus veralteten oder unvollständigen Daten.
- Keine stillen Fehler; jeder Lauf endet mit einem vollständigen Bericht.

## Umsetzung und Verifikation

Die Umsetzung erfolgt in dieser Reihenfolge:

1. neutrale Steuerdatei anlegen;
2. daily_scan.yml um den eingeschränkten Push-Trigger ergänzen und den alten Zeitplan entfernen;
3. Repository-Tests ausführen beziehungsweise durch einen manuellen Triggerlauf verifizieren;
4. drei private Scalable-Strategiegruppen anlegen;
5. bestehende Strategiepositionen korrekt zuordnen;
6. geplanten Agenten mit den fünf Werktagszeiten erstellen;
7. einen beaufsichtigten End-to-End-Test durchführen;
8. prüfen, dass genau ein Workflow ausgelöst wird, dieser erfolgreich abgeschlossen wird und der Agent anschließend GitHub und Scalable vollständig auswertet;
9. sicherstellen, dass der Test keine Handelsorder übermittelt.

## Akzeptanzkriterien

Die Lösung ist erst fertig, wenn:

- der Agent zu jedem der fünf Werktagszeitpunkte selbst eine eindeutige Startanforderung erzeugt;
- genau der dadurch ausgelöste GitHub-Lauf identifiziert und bis zum Abschluss überwacht wird;
- Fehler nach der vereinbarten Logik behandelt und berichtet werden;
- ausschließlich aktuelle und valide A/B/C-Ergebnisse verwendet werden;
- ausschließlich private Strategiegruppen in Scalable ausgewertet werden;
- Nicht-Strategiepositionen unangetastet bleiben;
- nach jedem Lauf ein vollständiger Bericht erscheint;
- gültige Orders vollständig vorbereitet, aber niemals ohne separate Bestätigung übermittelt werden;
- wiederholte Signale und unbekannte Orderzustände keine Doppelorders erzeugen.
