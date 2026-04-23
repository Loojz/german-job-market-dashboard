---
title: Arbeitsmarkt Dashboard Deutschland
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.35.0
app_file: app.py
pinned: false
license: mit
---

# Arbeitsmarkt-Dashboard Deutschland

Interaktives Dashboard zur Visualisierung des deutschen Arbeitsmarkts.  
**THWS Business School** | Bachelor Business Analytics | Projekt SS 2026  
Team: Bildiren · Höhn · Prokopf | Betreuer: Prof. Dr. Marcus Klemm

---

## Sofort lokal starten (ohne API-Keys, mit Demo-Daten)

```bash
# 1. Repository klonen
git clone https://github.com/DEIN_NAME/arbeitsmarkt-dashboard.git
cd arbeitsmarkt-dashboard

# 2. Python-Umgebung einrichten (Python 3.11+ empfohlen)
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Abhängigkeiten installieren
pip install -r requirements.txt

# 4. Datenpipeline einmalig ausführen
#    → ohne API-Keys werden realistische Demo-Daten erzeugt
python -m src.pipeline

# 5. Dashboard starten
streamlit run app.py
```

Das Dashboard öffnet sich automatisch unter **http://localhost:8501**

> **Hinweis Demo-Daten:** Ohne echte API-Keys läuft alles mit realistisch
> kalibrierten Fallback-Daten. Die Größenordnungen stimmen, aber es sind keine
> echten BA/Destatis-Werte. Sobald API-Zugänge eingerichtet sind, einfach
> `python -m src.pipeline` erneut ausführen – die Parquets werden überschrieben.

---

## Echte Daten: API-Zugänge einrichten

### 1. GENESIS-API (Destatis) — für Erwerbstätige & Bruttolöhne

**Registrierung (kostenlos, ~2 Minuten):**
1. https://www-genesis.destatis.de öffnen
2. Oben rechts: **"Registrierung"** klicken
3. Formular ausfüllen (Name, E-Mail, gewünschter Benutzername)
4. Bestätigungs-E-Mail anklicken → fertig

**Zugangsdaten eintragen:**
```bash
# Lokal: .env-Datei anlegen (wird nicht committed – steht in .gitignore)
cp .env.example .env
# .env mit Editor öffnen und ausfüllen:
GENESIS_USER=dein_benutzername
GENESIS_PASSWORD=dein_passwort
```

**Für GitHub Actions (Deployment):**  
Unter GitHub → Repository → Settings → Secrets and Variables → Actions → **New repository secret**:
- Name: `GENESIS_USER`, Wert: dein Benutzername
- Name: `GENESIS_PASSWORD`, Wert: dein Passwort

---

### 2. Regionalstatistik.de — für Kreisebene (optional, Ausbaustufe)

**Registrierung (kostenlos, seit Mai 2025 erforderlich):**
1. https://www.regionalstatistik.de öffnen
2. **"Registrierung"** oben rechts
3. Gleicher Prozess wie GENESIS — dieselben Zugangsdaten funktionieren **nicht**,
   man braucht einen separaten Account

Eintragen in `.env`:
```
REGIO_USER=dein_benutzername_regio
REGIO_PASSWORD=dein_passwort_regio
```

> **Tipp:** GENESIS und Regionalstatistik verwenden beide die GENESIS-API-Syntax.
> Nur die Base-URL unterscheidet sich (`www-genesis.destatis.de` vs.
> `www.regionalstatistik.de`).

---

### 3. BA-Statistik — kein Account nötig

Die BA-Daten (Arbeitslose, Beschäftigte nach Bundesland) werden als **direkter
CSV/Excel-Download** abgerufen. Dafür ist keine Registrierung nötig.

Die BA bietet seit Dezember 2025 eine neue Statistik-API an
(https://statistik.arbeitsagentur.de → Service → API). Diese ist noch im
Aufbau. Der Direktdownload ist stabiler und von der BA selbst für maschinelle
Verarbeitung empfohlen.

---

## Projektstruktur

```
arbeitsmarkt-dashboard/
│
├── app.py                  ← Streamlit-Hauptdatei (Einstiegspunkt)
├── requirements.txt
├── .env.example            ← Vorlage für API-Zugangsdaten
├── .gitignore
│
├── src/
│   ├── pipeline.py         ← Datenabruf, Parquet-Speicherung, Fallback-Daten
│   ├── queries.py          ← DuckDB-SQL-Abfragen
│   └── charts.py           ← Plotly-Visualisierungen
│
├── data/
│   └── processed/          ← Parquet-Dateien (werden von Pipeline erzeugt)
│       ├── arbeitslose.parquet
│       ├── beschaeftigung.parquet
│       ├── erwerbstaetige.parquet
│       └── mindestlohn.parquet
│
└── .github/
    └── workflows/
        └── deploy.yml      ← GitHub Actions: Daten-Update + HF-Sync
```

---

## Deployment auf Hugging Face Spaces

### Einmalig einrichten:

1. Account auf https://huggingface.co anlegen (kostenlos)
2. Neuen Space erstellen: https://huggingface.co/new-space
   - SDK: **Streamlit**
   - Sichtbarkeit: **Public**

3. GitHub Secrets setzen (Settings → Secrets → Actions):
   - `HF_TOKEN`: dein HF-Access-Token (https://huggingface.co/settings/tokens → Write)

4. GitHub Repository Variables setzen (Settings → Secrets → Variables):
   - `HF_USERNAME`: dein HF-Benutzername
   - `HF_SPACE_NAME`: Name des Spaces (z. B. `arbeitsmarkt-dashboard`)

5. Beim nächsten `git push main` deployt die GitHub Action automatisch.

### Funktionsweise des Deployments:
```
git push → GitHub Actions → git push → Hugging Face Spaces → App live
```
Der HF Space ist ein eigenes Git-Repository. Die Action spiegelt deinen
`main`-Branch dorthin. HF Spaces baut dann automatisch neu.

---

## Datenpipeline manuell auslösen

```bash
# Lokal
python -m src.pipeline

# Oder als GitHub Action:
# GitHub → Actions → "Datenpipeline & Deployment" → "Run workflow"
```

Die Pipeline läuft außerdem jeden Montag um 06:00 UTC automatisch.

---

## Datenquellen & Lizenzen

| Quelle | Inhalt | Lizenz |
|--------|--------|--------|
| [Bundesagentur für Arbeit](https://statistik.arbeitsagentur.de) | Arbeitslose, Beschäftigte (Bundesland) | Datenlizenz Deutschland 2.0 |
| [Destatis GENESIS](https://www-genesis.destatis.de) | Erwerbstätige (VGR), Löhne | Datenlizenz Deutschland 2.0 |
| [Regionalstatistik.de](https://www.regionalstatistik.de) | Kreis- und Gemeindeebene | Datenlizenz Deutschland 2.0 |
| Mindestlohnkommission | Anpassungshistorie | öffentlich |

Alle Daten stehen unter der
[Datenlizenz Deutschland 2.0](https://www.govdata.de/dl-de/by-2-0) und dürfen
mit Quellenangabe frei weiterverwendet werden.

---

## Empfohlene Zitation

> Bundesagentur für Arbeit / Statistisches Bundesamt (Destatis) (2024/2025):
> Arbeitsmarktdaten Deutschland, abgerufen via Arbeitsmarkt-Dashboard,
> THWS Business School – Bachelor Business Analytics, Sommersemester 2026.
> Code: https://github.com/DEIN_NAME/arbeitsmarkt-dashboard
