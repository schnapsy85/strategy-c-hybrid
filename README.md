# Strategie C Hybrid-Scanner

Automatischer Daily-Scanner für **Strategie C v1.0 (Dynamic RSI)**.

**Datenfluss**

1. Aktuelle S&P-500-Mitglieder werden täglich geladen.
2. Massive liefert echte tägliche, split-adjustierte OHLCV-Daten.
3. Der Scanner berechnet RSI(14), Dynamic RSI, adaptive Bänder, SMA200, ATR14, C1/C2 und WATCH.
4. Das Ergebnis wird nach `docs/latest.json` geschrieben.
5. GitHub Pages kann diese JSON öffentlich bereitstellen.
6. ChatGPT liest nur die fertigen Signale und verwendet Scalable anschließend für Depot, Liquidität, Handelbarkeit und Order-Vorschauen.

Der **Massive API-Key bleibt ausschließlich als GitHub Secret** gespeichert und wird nie in die JSON-Datei geschrieben.

## Benötigte Massive-Tarife

Für den Scanner reicht zunächst:

- **Stocks Basic (Free)** – für S&P-500-Aktien und Daily Market Summary.
- Optional, aber empfohlen: **Indices Basic (Free)** – damit der Marktfilter exakt mit `I:SPX` statt ersatzweise mit `SPY` berechnet wird.

Massive Daily Market Summary:
`GET /v2/aggs/grouped/locale/us/market/stocks/{date}`

Der Free-Tarif ist auf 5 API-Aufrufe pro Minute begrenzt. Deshalb dauert der einmalige historische Backfill ungefähr eine Stunde. Danach braucht der tägliche Lauf nur sehr wenige Requests.

## Projektstruktur

```text
strategy-c-hybrid/
├─ .github/workflows/
│  ├─ backfill.yml
│  └─ daily_scan.yml
├─ data/
│  └─ ohlcv.csv.gz              # wird beim ersten Lauf erzeugt
├─ docs/
│  ├─ index.html
│  └─ latest.json
├─ scripts/
│  ├─ backfill.py
│  └─ daily_scan.py
├─ src/
│  ├─ indicators.py
│  ├─ massive_client.py
│  ├─ scanner.py
│  ├─ storage.py
│  └─ universe.py
├─ tests/
│  └─ test_indicators.py
├─ config.json
├─ requirements.txt
└─ README.md
```

## Schritt 1 – Massive einrichten

1. Massive-Konto anlegen.
2. **Stocks Basic (Free)** aktivieren.
3. Wenn möglich zusätzlich **Indices Basic (Free)** aktivieren.
4. API-Key kopieren.
5. Den Key **nicht** in Dateien und **nicht** in ChatGPT einfügen.

## Schritt 2 – GitHub-Repository anlegen

Erstelle ein Repository, z. B.:

`strategy-c-hybrid`

Für die einfachste ChatGPT-Anbindung sollte es **öffentlich** sein. Der API-Key bleibt trotzdem privat, weil GitHub Secrets niemals mit committed werden.

Entpacke dieses Projekt lokal und lade den Inhalt in das Repository.

Mit Git:

```bash
git init
git add .
git commit -m "Initial Strategy C scanner"
git branch -M main
git remote add origin https://github.com/DEIN-USER/strategy-c-hybrid.git
git push -u origin main
```

## Schritt 3 – API-Key als GitHub Secret speichern

Im Repository:

**Settings → Secrets and variables → Actions → New repository secret**

Name:

`MASSIVE_API_KEY`

Value:

dein Massive API-Key.

## Schritt 4 – Schreibrechte für GitHub Actions

Im Repository:

**Settings → Actions → General → Workflow permissions**

Wähle:

**Read and write permissions**

Speichern.

Der Scanner muss `data/ohlcv.csv.gz` und `docs/latest.json` zurück ins Repository schreiben dürfen.

## Schritt 5 – Einmaligen historischen Backfill starten

Gehe zu:

**Actions → Backfill Strategy C History → Run workflow**

Beim Free-Tarif dauert dieser Lauf typischerweise ungefähr 60–80 Minuten, da bewusst das 5-Requests-pro-Minute-Limit eingehalten wird.

Der Backfill lädt etwa 430 Kalendertage und speichert mindestens 280 Handelstage je aktuellem S&P-500-Titel, soweit Massive die Daten liefert.

Nach dem Backfill wird automatisch bereits ein erster Strategie-C-Scan ausgeführt.

## Schritt 6 – GitHub Pages aktivieren

Im Repository:

**Settings → Pages**

- Source: **Deploy from a branch**
- Branch: **main**
- Folder: **/docs**

Danach entsteht typischerweise:

`https://DEIN-USER.github.io/strategy-c-hybrid/latest.json`

Diese URL enthält **nur Scan-Ergebnisse, niemals den API-Key**.

Wenn du die URL hast, schick sie mir. Dann kann der ChatGPT-Workflow für Strategie C auf genau diese Datei umgestellt werden.

## Agent-triggered weekday runs

Scheduled Strategy A/B/C runs are initiated by the private ChatGPT automation.
At each configured weekday slot, the agent updates
`.automation/run-request.json`. The path-filtered push starts
`Daily Strategy A/B/C Scan`.

GitHub no longer owns the recurring clock schedule. Manual
`workflow_dispatch` remains available for diagnostics. Updates to scan output
files and `.automation/signal-state.json` do not trigger another scan.

## Strategie-C-Regeln im Code

### Trendfilter

Marktfilter:

- S&P 500 (`I:SPX`, falls Indices Basic aktiv) Schlusskurs > SMA200
- Fallback: `SPY` > SMA200

Aktienfilter:

- Schlusskurs > SMA200
- SMA200 heute > SMA200 vor 20 Handelstagen
- Adaptive Midline > 50
- Adaptive Midline heute > Adaptive Midline vor 5 Handelstagen

### RSI

RSI(14) wird nach Wilder berechnet.

Dynamic RSI:

```text
(4 × RSI heute + 3 × RSI gestern + 2 × RSI vor 2 Tagen + 1 × RSI vor 3 Tagen) / 10
```

Über den 60-Tage-RSI-Lookback:

```text
HighestRSI = höchster RSI(14)
LowestRSI  = niedrigster RSI(14)

AdaptiveMidline = 0,5 × WMA14(HighestRSI − LowestRSI)
                  + WMA14(LowestRSI)

Upper = HighestRSI − 0,20 × AdaptiveMidline
Lower = LowestRSI  + 0,20 × AdaptiveMidline
```

### C1 Pullback

- gestern DynamicRSI ≤ Lower
- heute DynamicRSI > Lower
- heute DynamicRSI > gestern
- alle Trendfilter erfüllt

### C2 Momentum Breakout

- gestern DynamicRSI ≤ Upper
- heute DynamicRSI > Upper
- Schlusskurs > höchstes Tageshoch der vorherigen 20 Handelstage
- heutiges Volumen > Durchschnittsvolumen der vorherigen 20 Handelstage
- alle Trendfilter erfüllt

C1 wird vor C2 priorisiert.

### Gap-Filter

Kein Einstieg, wenn der Open des Folgetages größer ist als:

```text
Signal-Schlusskurs + 0,75 × ATR14
```

Die JSON enthält deshalb `max_next_open`.

### Risiko

Standard in `config.json`:

- Referenzkapital Strategie C: 1.000 EUR
- Risiko je Trade: 1 %
- Initialstop: Entry − 2 × ATR14
- Maximal 20 % Kapital je Aktie

Die vom Scanner berechnete Positionsgröße ist **nur eine Referenz**. Vor einer tatsächlichen Order soll ChatGPT mit Scalable das reale Strategie-C-Kapital und den ausführbaren Kurs neu prüfen.

## Was steht in `latest.json`?

Unter anderem:

```json
{
  "coverage": {
    "members_total": 503,
    "members_with_min_history": 501,
    "ratio": 0.996
  },
  "market_filter": {
    "ticker_used": "I:SPX",
    "pass": true
  },
  "signals": [
    {
      "ticker": "XYZ",
      "signal": "C1",
      "close": 123.45,
      "atr14": 3.21,
      "max_next_open": 125.8575
    }
  ]
}
```

Zusätzlich enthält `metrics_by_ticker` die aktuellen Strategie-C-Indikatoren für alle Titel mit ausreichender Datenhistorie. Das ist wichtig, damit bestehende Strategie-C-Positionen später auch auf Exit-Bedingungen geprüft werden können.

## Datenabdeckung

Der Scanner behauptet niemals stillschweigend einen vollständigen Scan.

Wenn weniger als 98 % der aktuellen S&P-500-Titel mindestens die konfigurierte Historie haben, erhält `latest.json`:

```json
"status": "partial_data"
```

und listet fehlende/zu kurze Ticker explizit auf.

## Sicherheit

- Kein API-Key im Repository.
- Kein API-Key in `latest.json`.
- Keine Broker-Zugangsdaten in GitHub.
- GitHub trifft keine Kaufentscheidung bei Scalable.
- Die Order-Vorschau und Bestätigung bleiben im ChatGPT/Scalable-Workflow.
- Jede Kauf- und Stop-Order benötigt weiterhin die separate ausdrückliche Bestätigung.

## Nächster Schritt nach dem Setup

Schick mir anschließend nur deine GitHub-Pages-URL, z. B.:

`https://DEIN-USER.github.io/strategy-c-hybrid/latest.json`

Dann kann ich den bestehenden Strategie-C-Task so umstellen, dass er täglich:

1. `latest.json` liest,
2. nur C1/C2/EXIT-relevante Signale verarbeitet,
3. Scalable auf Handelbarkeit, Kapital und Positionen prüft,
4. dir bei einem echten Trade die konkrete Order zur Bestätigung vorlegt.
