# Design: Automatisierter Scalable-Invest-Agent

Datum: 2026-09-02  
Status: Implementiert und verifiziert

## Ziel

Ein Agent startet montags bis freitags um 08:30, 12:30, 15:30, 18:30 und 22:30 Uhr in der Zeitzone Europe/Berlin eigenständig einen vollständigen GitHub-Lauf für die Strategien A, B und C. Er überwacht den von ihm ausgelösten Lauf bis zum Abschluss, prüft anschließend ausschließlich die neu erzeugten Ergebnisse, gleicht sie mit dem privaten Scalable-Depot ab und liefert nach jedem Lauf eine vollständige Auswertung.

Bei einem gültigen Kauf-, Verkaufs- oder Stoppsignal erstellt der Agent eine vollständige Scalable-Ordervorschau. Eine Order darf erst nach der für genau diese Vorschau erforderlichen separaten ausdrücklichen Bestätigung des Nutzers übermittelt werden.

## Bestehende Grundlage

Repository: schnapsy85/strategy-c-hybrid  
Branch: main  
Zentraler Workflow: .github/workflows/daily_scan.yml

Der Workflow führt folgende Schritte aus:

1. Exakt den auslösenden Request-Commit auschecken.
2. Python und Abhängigkeiten einrichten.
3. Tests ausführen.
4. gemeinsame Marktdaten aktualisieren und Strategie C scannen.
5. Strategie A scannen.
6. Strategie B scannen.
7. Ergebnisse nach data und docs synchronisieren.
8. alle sechs Ergebnisdateien mit dem auslösenden Request-Commit stempeln.
9. geänderte Daten und Scanergebnisse nach main schreiben.

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

Zur eindeutigen Zuordnung filtert der Agent nach Workflow-Pfad, Push-Ereignis, Branch, Erstellungszeitpunkt und dem Commit-SHA der Startanforderung. Er prüft den Status höchstens einmal pro Minute und beendet die Überwachung nach maximal 45 Minuten als Timeout. Bei einem Timeout erfolgt keine Strategie- oder Orderentscheidung.

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
- top-level `request_commit_sha` stimmt exakt mit dem überwachten Request-Commit überein.

Ein GitHub-Lauf gilt für die Agentenauswertung nur dann als fachlich erfolgreich, wenn jede Ergebnisdatei einen top-level `request_commit_sha` trägt, dieser exakt dem überwachten Request-Commit entspricht und die jeweilige Strategie ihre eigenen Datenqualitätsregeln erfüllt. Eine Datei mit fehlendem oder abweichendem `request_commit_sha` ist nicht verwendbar.

Bei stale_data, partial_data oder einer fehlgeschlagenen Freshness-Prüfung werden Signale der betroffenen Strategie gesperrt. Andere fehlerfreie Strategien können weiterhin ausgewertet werden, sofern keine gemeinsame Datenquelle beschädigt ist.

## Private Trennung der Strategiepositionen ohne Portfolio-Gruppen

Das Repository ist öffentlich. Deshalb dürfen dort keine persönlichen Depotwerte, exakten Bestände, Broker-Portfolio-IDs, Order-IDs, Transaktionshistorien oder privaten Performancewerte gespeichert werden.

Die Zuordnung erfolgt ausschließlich über eine private Strategie-Allowlist im Agentenauftrag. Jeder Eintrag enthält intern mindestens die Strategiezuordnung, Wertpapierkennung, Lebenszykluszustand und die zugehörige bestätigte Broker-Order- beziehungsweise Transaktionsreferenz. Diese Daten werden weder in GitHub noch in Berichten veröffentlicht.

Die initiale private Allowlist wird beim Einrichten der Automation ausschließlich anhand genehmigter und verifizierter Broker-Herkunft aufgelöst. Öffentliche Dateien nennen weder Mitgliederzahl, Strategieallokation, Instrumente noch aktuelle oder historische Positionszustände.

Bei jeder Depotprüfung darf der Agent zwar den Gesamtbestand lesen, aber nur Positionen auswerten oder verändern, deren Herkunft durch einen privaten Allowlist-Eintrag und die zugehörige Scalable-Transaktion eindeutig belegt ist. Alle anderen Fonds, ETFs, Derivate, Sparpläne, Aktien und privaten Positionen werden verworfen und bleiben unverändert.

Nach einer separat bestätigten Order ergänzt der interaktive Agent den privaten Agentenauftrag um die konkrete Orderreferenz. Der private Lebenszyklus darf erst fortgeschrieben werden, wenn Scalable das Ergebnis nachweislich zeigt. Frühere Provenienz bleibt nach einem vollständig ausgeführten Ausstieg zur Abgrenzung späterer privater Käufe erhalten.

Lässt sich die Herkunft einer Position nicht eindeutig einer bestätigten Strategieorder zuordnen, bestehen gemischte private und strategische Käufe desselben Wertpapiers oder fehlen Transaktionsdaten, wird das Instrument vollständig für Strategieaktionen gesperrt und im Bericht als Zuordnungskonflikt ausgewiesen.

Alle privaten Kapital-, Allowlist- und Provenienzdaten werden ausschließlich im privaten Agentenauftrag geführt, nicht im öffentlichen Repository.

Für die technische Deduplizierung darf eine zweite öffentliche Steuerdatei verwendet werden:

- .automation/signal-state.json

Sie enthält ausschließlich Signal-Schlüssel aus ohnehin öffentlichen Scannergebnissen, bestehend aus Strategie, Ticker, Signaltyp und Signaldatum. Sie enthält keine Depotbestände, Stückzahlen, Kurse, Budgets, Order-IDs, Bestätigungen oder persönlichen Entscheidungen. Eine Änderung dieser Datei darf den Scan-Workflow nicht auslösen.

## Scalable-Prüfung

Nach validierten GitHub-Ergebnissen liest der Agent:

- die private Strategie-Allowlist;
- den Scalable-Gesamtbestand zur anschließenden strikten Filterung gegen diese Allowlist;
- eindeutig zugeordnete Strategiebestände und aktuelle Kurse;
- relevante offene, ausstehende und abgeschlossene Transaktionen;
- aktiven Stop- oder Verkaufsorders;
- den zur Strategie gehörenden Kapitalstatus.

Scalable-Zugriffe erhalten bis zu zwei Wiederholungsversuche. Bleiben Depot-, Kurs-, Transaktions- oder Budgetdaten unvollständig, wird keine Ordervorschau erstellt.

Andere Depotpositionen dürfen weder für das Strategiebudget angerechnet noch verkauft, mit Stops versehen oder anderweitig verändert werden. Eine bloße Übereinstimmung von Ticker, Name oder ISIN ohne passende private Order- oder Transaktionsreferenz reicht nicht als Strategiezuordnung.

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
4. die initiale private Allowlist beim Einrichten der Automation ausschließlich aus genehmigter, verifizierter Broker-Provenienz auflösen;
5. die Broker-Isolation ohne Offenlegung der privaten Auflösung verifizieren;
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
- ausschließlich Positionen mit einer eindeutigen privaten Allowlist- und Broker-Transaktionszuordnung ausgewertet werden;
- Nicht-Strategiepositionen unangetastet bleiben;
- nach jedem Lauf ein vollständiger Bericht erscheint;
- gültige Orders vollständig vorbereitet, aber niemals ohne separate Bestätigung übermittelt werden;
- wiederholte Signale und unbekannte Orderzustände keine Doppelorders erzeugen.
