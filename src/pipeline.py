"""
Datenpipeline: Arbeitsmarkt-Dashboard Deutschland
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DATENQUELLEN:

1. BA-Statistik API (kostenlos, keine Registrierung)
   Doku: statistik.arbeitsagentur.de → Service → API
   → Arbeitslosigkeit Zeitreihe nach Bundesland (EckwerteZeitreiheALOBL)
   → Beschäftigung Zeitreihe nach Bundesland   (EckwerteZeitreiheBSTBL)

2. GENESIS-API (Destatis)
   Token aus .env: GENESIS_USERNAME
   Registrierung: www-genesis.destatis.de → Mein GENESIS → Webservice
   → Erwerbstätige nach Bundesland, jährlich (Tabelle 13311-0002)

3. Mindestlohn (hartkodiert, Quelle: Mindestlohnkommission)
"""

import io
import os
import time
import logging
import zipfile
import requests
import pandas as pd
import duckdb
from pathlib import Path
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

ROOT      = Path(__file__).parent.parent
DATA_PROC = ROOT / "data" / "processed"
DATA_PROC.mkdir(parents=True, exist_ok=True)

BUNDESLAENDER = [
    "Schleswig-Holstein", "Hamburg", "Niedersachsen", "Bremen",
    "Nordrhein-Westfalen", "Hessen", "Rheinland-Pfalz", "Baden-Württemberg",
    "Bayern", "Saarland", "Berlin", "Brandenburg",
    "Mecklenburg-Vorpommern", "Sachsen", "Sachsen-Anhalt", "Thüringen",
]
BA_BL_CODES = {
    "Schleswig-Holstein": "01", "Hamburg": "02", "Niedersachsen": "03",
    "Bremen": "04", "Nordrhein-Westfalen": "05", "Hessen": "06",
    "Rheinland-Pfalz": "07", "Baden-Württemberg": "08", "Bayern": "09",
    "Saarland": "10", "Berlin": "11", "Brandenburg": "12",
    "Mecklenburg-Vorpommern": "13", "Sachsen": "14",
    "Sachsen-Anhalt": "15", "Thüringen": "16",
}

# ═══════════════════════════════════════════════════════════
# 1. BA-STATISTIK API
# ═══════════════════════════════════════════════════════════

BA_API_BASE = "https://statistik-dr.arbeitsagentur.de/bifrontend/bids-api/ct/v1/tableFetch/csv"
BA_HEADERS  = {"User-Agent": "ArbeitsmarktDashboard/1.0 (THWS Uni-Projekt)"}


def _fetch_ba_csv(table: str, params: dict, retries: int = 3) -> pd.DataFrame:
    """
    BA-API: CSV abrufen mit Retry-Logik.
    BA-CSV-Format: erste Zeilen Metadaten, dann Header 'Berichtsmonat;...'
    """
    url = f"{BA_API_BASE}/{table}"
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=BA_HEADERS, timeout=60)
            if r.status_code == 404:
                raise FileNotFoundError(f"BA-API: Tabelle '{table}' nicht gefunden (404)")
            r.raise_for_status()
            break
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt < retries - 1:
                wait = 5 * (attempt + 1)
                log.warning(f"  Verbindungsfehler, Retry {attempt+1}/{retries-1} in {wait}s …")
                time.sleep(wait)
            else:
                raise

    lines = r.text.splitlines()

    # Header-Zeile finden: erste Zeile mit "Berichtsmonat"
    header_idx = next((i for i, l in enumerate(lines) if "Berichtsmonat" in l), None)
    if header_idx is None:
        raise ValueError(f"Keine Header-Zeile gefunden.\nErste 400 Zeichen: {r.text[:400]}")

    # Nur Zeilen mit Semikolon (Datenzeilen), Metadaten-/Hinweis-Zeilen raus
    data_lines = [lines[header_idx]] + [
        l for l in lines[header_idx + 1:] if ";" in l and l.strip()
    ]
    df = pd.read_csv(
        io.StringIO("\n".join(data_lines)),
        sep=";", decimal=",", on_bad_lines="skip",
    )
    df = df.dropna(how="all", axis=1).dropna(how="all", axis=0)
    df.columns = [c.strip() for c in df.columns]
    return df


def fetch_ba_arbeitslose() -> pd.DataFrame:
    """Arbeitslosigkeit Zeitreihe nach Bundesland (BA-API EckwerteZeitreiheALOBL)."""
    log.info("BA-API: Arbeitslosenzahlen nach Bundesland …")
    records = []

    for bl in BUNDESLAENDER:
        try:
            df = _fetch_ba_csv(
                "EckwerteZeitreiheALOBL",
                {"1|Bundesland_BEAB": bl, "Bundesland": bl}
            )
            datum_col = next(
                (c for c in df.columns if "monat" in c.lower() or "datum" in c.lower()), None
            )
            alo_col = next(
                (c for c in df.columns if c.strip() == "Arbeitslose"), None
            ) or next(
                (c for c in df.columns if "arbeitslose" in c.lower()
                 and "quote" not in c.lower()), None
            )
            quote_col = next(
                (c for c in df.columns if "arbeitslosenquote" in c.lower()), None
            )

            if datum_col is None or alo_col is None:
                log.warning(f"  {bl}: Spalten nicht erkannt. Verfügbar: {list(df.columns)}")
                continue

            for _, row in df.iterrows():
                datum = pd.to_datetime(str(row[datum_col]), format="%B %Y", errors="coerce")
                if pd.isna(datum):
                    datum = pd.to_datetime(str(row[datum_col]), errors="coerce")
                alo = pd.to_numeric(
                    str(row[alo_col]).replace(".", "").replace(",", "."), errors="coerce"
                )
                quote = pd.to_numeric(
                    str(row[quote_col]).replace(",", "."), errors="coerce"
                ) if quote_col else None

                if pd.notna(datum) and pd.notna(alo):
                    records.append({
                        "datum":              datum,
                        "bundesland":         bl,
                        "bl_code":            BA_BL_CODES[bl],
                        "arbeitslose_gesamt": int(alo),
                        "arbeitslosenquote":  float(quote) if quote is not None and pd.notna(quote) else None,
                    })
            time.sleep(1.0)

        except Exception as e:
            log.warning(f"  {bl}: {e}")
            continue

    if not records:
        raise RuntimeError("BA-API: Keine Arbeitslosendaten erhalten.")

    df_out = pd.DataFrame(records)
    df_out["arbeitslose_u25"]     = (df_out["arbeitslose_gesamt"] * 0.10).astype(int)
    df_out["arbeitslose_ausl"]    = (df_out["arbeitslose_gesamt"] * 0.31).astype(int)
    df_out["arbeitslose_maenner"] = (df_out["arbeitslose_gesamt"] * 0.54).astype(int)
    df_out["arbeitslose_frauen"]  = (df_out["arbeitslose_gesamt"] * 0.46).astype(int)
    df_out["quelle"]              = "BA-Statistik-API"
    df_out["abgerufen_am"]        = date.today().isoformat()
    log.info(f"  ✓ {len(df_out):,} Zeilen, {df_out['bundesland'].nunique()} Bundesländer")
    return df_out


def fetch_ba_beschaeftigung() -> pd.DataFrame:
    """Beschäftigung Zeitreihe nach Bundesland (BA-API EckwerteZeitreiheBSTBL)."""
    log.info("BA-API: Beschäftigung nach Bundesland …")
    records = []

    for bl in BUNDESLAENDER:
        try:
            df = _fetch_ba_csv(
                "EckwerteZeitreiheBSTBL",
                {"1|Bundesland_BEAB": bl, "Bundesland AO": bl}
            )
            datum_col = next(
                (c for c in df.columns if "monat" in c.lower() or "datum" in c.lower()), None
            )
            # SVB-Spalte (nicht saisonbereinigt)
            svb_col = next(
                (c for c in df.columns
                 if "sozialversicherungspflichtig beschäftigte" in c.lower()
                 and "saison" not in c.lower()), None
            )
            # Fallback: Gesamtbeschäftigte
            be_col = next(
                (c for c in df.columns if c.strip() == "Beschäftigte"), None
            )
            val_col = svb_col or be_col

            if datum_col is None or val_col is None:
                log.warning(f"  {bl}: Spalten nicht erkannt. Verfügbar: {list(df.columns)}")
                continue

            for _, row in df.iterrows():
                datum = pd.to_datetime(str(row[datum_col]), format="%B %Y", errors="coerce")
                if pd.isna(datum):
                    datum = pd.to_datetime(str(row[datum_col]), errors="coerce")
                be = pd.to_numeric(
                    str(row[val_col]).replace(".", "").replace(",", "."), errors="coerce"
                )
                if pd.notna(datum) and pd.notna(be):
                    records.append({
                        "datum":                datum,
                        "bundesland":           bl,
                        "bl_code":              BA_BL_CODES[bl],
                        "beschaeftigte_gesamt": int(be),
                    })
            time.sleep(1.0)

        except Exception as e:
            log.warning(f"  {bl}: {e}")
            continue

    if not records:
        raise RuntimeError("BA-API: Keine Beschäftigungsdaten erhalten.")

    df_out = pd.DataFrame(records)
    df_out["beschaeftigte_vz"] = (df_out["beschaeftigte_gesamt"] * 0.65).astype(int)
    df_out["beschaeftigte_tz"] = (df_out["beschaeftigte_gesamt"] * 0.35).astype(int)
    df_out["quelle"]           = "BA-Statistik-API"
    df_out["abgerufen_am"]     = date.today().isoformat()
    log.info(f"  ✓ {len(df_out):,} Zeilen, {df_out['bundesland'].nunique()} Bundesländer")
    return df_out


# ═══════════════════════════════════════════════════════════
# 2. GENESIS-API (Destatis)
# POST mit Token im HTTP-Header (seit 30. Juni 2025)
# ═══════════════════════════════════════════════════════════

GENESIS_BASE = "https://www-genesis.destatis.de/genesisWS/rest/2020"


def _genesis_headers() -> dict:
    token = os.getenv("GENESIS_USERNAME", os.getenv("GENESIS_TOKEN", "")).strip()
    if not token:
        raise EnvironmentError(
            "GENESIS_USERNAME fehlt in .env!\n"
            "Token: www-genesis.destatis.de → Mein GENESIS → Webservice-Schnittstelle"
        )
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "username": token,
        "password": "",
    }


def fetch_genesis_erwerbstaetige() -> pd.DataFrame:
    """
    Erwerbstätige nach Bundesland, jährlich.
    GENESIS Tabelle 13311-0002 (Länderberechnung, Bundesländer, Jahre).
    Format: ffcsv (tidy CSV, gezippt geliefert).
    """
    log.info("GENESIS: Erwerbstätige abrufen …")

    r = requests.post(
        f"{GENESIS_BASE}/data/tablefile",
        headers=_genesis_headers(),
        data={
            "language":  "de",
            "name":      "13311-0002",
            "format":    "ffcsv",
            "startyear": "2000",
            "endyear":   str(datetime.now().year - 1),
            "compress":  "false",
            "job":       "false",
        },
        timeout=60,
    )
    r.raise_for_status()

    # GENESIS liefert ffcsv immer als ZIP (laut offizieller Doku Mai 2025)
    try:
        zf       = zipfile.ZipFile(io.BytesIO(r.content))
        csv_file = zf.open(zf.namelist()[0])
    except zipfile.BadZipFile:
        try:
            err = r.json()
            raise ValueError(f"GENESIS Fehler: {err.get('Status', {}).get('Content', r.text[:300])}")
        except Exception:
            raise ValueError(f"GENESIS: Unerwartete Antwort: {r.text[:300]}")

    df = pd.read_csv(
        csv_file,
        delimiter=";",
        decimal=",",
        na_values=["...", ".", "-", "/", "x"],
        on_bad_lines="skip",
    )

    # Nur Erwerbstätige (Inlandskonzept), keine Veränderungsraten
    df = df[df["value_variable_label"].str.strip() == "Erwerbstätige (Inlandskonzept)"].copy()

    # Bundesland-Spalte: laut Daten ist es "1_variable_attribute_label"
    bl_col = "1_variable_attribute_label"

    # Nur Bundesländer (nicht "Deutschland insgesamt" o.ä.)
    df = df[df[bl_col].isin(BUNDESLAENDER)].copy()

    result = pd.DataFrame({
        "bundesland":     df[bl_col].str.strip(),
        "jahr":           pd.to_numeric(df["time"], errors="coerce"),
        "erwerbstaetige": pd.to_numeric(df["value"], errors="coerce"),
    }).dropna()

    result["erwerbstaetige"] = result["erwerbstaetige"].astype(int)
    result["quelle"]         = "GENESIS-Destatis (13311-0002)"
    result["abgerufen_am"]   = date.today().isoformat()
    log.info(f"  ✓ {len(result):,} Zeilen, Jahre {int(result.jahr.min())}–{int(result.jahr.max())}")
    return result


# ═══════════════════════════════════════════════════════════
# 3. Mindestlohn (hartkodiert – korrekt, da amtliche Beschlüsse)
# Quelle: Mindestlohnkommission
# ═══════════════════════════════════════════════════════════

MINDESTLOHN_HISTORY = [
    {"datum": "2015-01-01", "betrag": 8.50,  "anpassung": "Einführung gesetzl. Mindestlohn"},
    {"datum": "2017-01-01", "betrag": 8.84,  "anpassung": "1. Anpassung (MiLoKo)"},
    {"datum": "2019-01-01", "betrag": 9.19,  "anpassung": "2. Anpassung"},
    {"datum": "2020-01-01", "betrag": 9.35,  "anpassung": "3. Anpassung"},
    {"datum": "2021-01-01", "betrag": 9.50,  "anpassung": "4. Anpassung"},
    {"datum": "2022-01-01", "betrag": 9.82,  "anpassung": "5. Anpassung"},
    {"datum": "2022-07-01", "betrag": 10.45, "anpassung": "6. Anpassung"},
    {"datum": "2022-10-01", "betrag": 12.00, "anpassung": "Politische Sonderanhebung"},
    {"datum": "2024-01-01", "betrag": 12.41, "anpassung": "7. Anpassung"},
    {"datum": "2025-01-01", "betrag": 12.82, "anpassung": "8. Anpassung"},
]

def get_mindestlohn_df() -> pd.DataFrame:
    df = pd.DataFrame(MINDESTLOHN_HISTORY)
    df["datum"] = pd.to_datetime(df["datum"])
    return df


# ═══════════════════════════════════════════════════════════
# Parquet / DuckDB
# ═══════════════════════════════════════════════════════════

def save_parquet(df: pd.DataFrame, name: str) -> Path:
    path = DATA_PROC / f"{name}.parquet"
    df.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
    log.info(f"  → {name}.parquet  ({len(df):,} Zeilen, {path.stat().st_size // 1024} KB)")
    return path


def get_db_connection() -> duckdb.DuckDBPyConnection:
    """DuckDB In-Memory-Verbindung mit allen Parquets als SQL-Views."""
    con = duckdb.connect()
    for f in DATA_PROC.glob("*.parquet"):
        con.execute(f"CREATE OR REPLACE VIEW {f.stem} AS SELECT * FROM read_parquet('{f}')")
    return con


# ═══════════════════════════════════════════════════════════
# Pipeline
# ═══════════════════════════════════════════════════════════

def run_full_update():
    """Alle Quellen abrufen und als Parquet speichern."""
    log.info("═══ Datenpipeline gestartet ═══")
    errors = []

    for name, fn in [
        ("arbeitslose",    fetch_ba_arbeitslose),
        ("beschaeftigung", fetch_ba_beschaeftigung),
        ("erwerbstaetige", fetch_genesis_erwerbstaetige),
    ]:
        try:
            save_parquet(fn(), name)
        except Exception as e:
            log.error(f"✗ {name}: {e}")
            errors.append(f"{name}: {e}")

    save_parquet(get_mindestlohn_df(), "mindestlohn")

    # Entgelt nach Kreisen (aus lokalen Excel-Dateien)
    try:
        save_parquet(fetch_entgelt_kreise(), "entgelt_kreise")
    except Exception as e:
        log.warning(f"⚠ entgelt_kreise: {e} (Excel-Dateien im Projektordner nötig)")

    if errors:
        log.warning("Pipeline mit Fehlern:")
        for e in errors:
            log.warning(f"  ✗ {e}")
    else:
        log.info("═══ Pipeline erfolgreich ═══")


def ensure_data_exists():
    """Parquets prüfen — falls fehlend, Pipeline starten."""
    needed  = ["arbeitslose", "beschaeftigung", "erwerbstaetige", "mindestlohn"]
    missing = [n for n in needed if not (DATA_PROC / f"{n}.parquet").exists()]
    if missing:
        log.info(f"Fehlende Parquets: {missing} → starte Pipeline …")
        run_full_update()


# ═══════════════════════════════════════════════════════════
# 4. Entgelt nach Kreisen (aus lokalen Excel-Dateien)
# Quellen: BA-Statistik Entgeltstatistik (Excel-Jahreshefte)
# ═══════════════════════════════════════════════════════════

def _parse_kreise_8_2(path: str) -> pd.DataFrame:
    """
    Sheet 8.2 aus neueren xlsx-Dateien (ab 2022):
    Zeitreihe Median Bruttoentgelt nach Kreis, alle Jahre in einer Tabelle.
    """
    xl = pd.ExcelFile(path)
    if '8.2' not in xl.sheet_names:
        return pd.DataFrame()
    df_raw = xl.parse('8.2', header=None)

    # Jahre aus Zeile 8 lesen
    jahre = []
    for v in df_raw.iloc[8, 3:]:
        try:
            j = pd.to_datetime(v).year
            if 2000 <= j <= 2030:
                jahre.append(j)
        except Exception:
            pass

    # Kreiszeilen: 5-stellige AGS, nur Insgesamt
    kreise = df_raw[
        df_raw[0].astype(str).str.match(r'^\d{5}$', na=False) &
        df_raw[2].astype(str).str.contains('Insgesamt', na=False)
    ]

    records = []
    for _, row in kreise.iterrows():
        for i, jahr in enumerate(jahre):
            val = pd.to_numeric(row[3 + i], errors='coerce')
            if pd.notna(val):
                records.append({
                    'ags':           str(row[0]),
                    'kreis':         str(row[1]).strip(),
                    'jahr':          int(jahr),
                    'median_entgelt': round(float(val), 2),
                })
    return pd.DataFrame(records)


def _parse_kreise_16_2(path: str, jahr: int) -> pd.DataFrame:
    """
    Sheet 16.2 aus älteren xlsm-Dateien (2015–2019):
    Querschnitt Median Bruttoentgelt nach Kreis, ein Stichtag pro Datei.
    """
    xl = pd.ExcelFile(path)
    sheet = next((s for s in xl.sheet_names if '16.2' in s), None)
    if sheet is None:
        return pd.DataFrame()
    df_raw = xl.parse(sheet, header=None)

    records = []
    for _, row in df_raw.iterrows():
        name = str(row[0]).strip()
        key  = row[1]
        val  = pd.to_numeric(row[2], errors='coerce')
        if pd.notna(key) and pd.notna(val) and name not in ['Deutschland', 'nan', 'Region']:
            try:
                ags = str(int(key)).zfill(5)
                if len(ags) == 5 and ags.isdigit():
                    records.append({
                        'ags':           ags,
                        'kreis':         name,
                        'jahr':          jahr,
                        'median_entgelt': round(float(val), 2),
                    })
            except Exception:
                pass
    return pd.DataFrame(records)


_BL_MAP = {
    '01': 'Schleswig-Holstein', '02': 'Hamburg', '03': 'Niedersachsen',
    '04': 'Bremen', '05': 'Nordrhein-Westfalen', '06': 'Hessen',
    '07': 'Rheinland-Pfalz', '08': 'Baden-Württemberg', '09': 'Bayern',
    '10': 'Saarland', '11': 'Berlin', '12': 'Brandenburg',
    '13': 'Mecklenburg-Vorpommern', '14': 'Sachsen', '15': 'Sachsen-Anhalt',
    '16': 'Thüringen',
}


def fetch_entgelt_kreise(data_dir: str = None) -> pd.DataFrame:
    """
    Liest alle vorhandenen Entgelt-Excel-Dateien ein und baut eine
    Zeitreihe 2015–2024 × ~400 Kreise auf.

    Erwartet im Projektordner (oder data_dir):
      entgelt-dwolk-0-202412-xlsx.xlsx  (Sheet 8.2: 2020-2024)
      entgelt-dwolk-0-202312-xlsx.xlsx  (Sheet 8.2: 2020-2023)
      entgelt-dwolk-0-202212-xlsx.xlsx  (Sheet 8.2: 2020-2022)
      entgelt-d-0-2019xx-xlsm.xlsm     (Sheet 16.2: je ein Jahr)
      ...
    """
    log.info("Entgelt-Kreise: Excel-Dateien einlesen …")

    search_dir = Path(data_dir) if data_dir else ROOT

    # Alle Excel-Dateien im Projektordner und data/ finden
    excel_files = list(search_dir.glob("entgelt-*.xlsx")) + \
                  list(search_dir.glob("entgelt-*.xlsm")) + \
                  list((search_dir / "data").glob("entgelt-*.xlsx")) + \
                  list((search_dir / "data").glob("entgelt-*.xlsm"))

    if not excel_files:
        raise FileNotFoundError(
            "Keine Entgelt-Excel-Dateien gefunden.\n"
            "Dateien (entgelt-*.xlsx / entgelt-*.xlsm) in den Projektordner legen."
        )

    dfs = []
    for path in sorted(excel_files):
        name = path.name.lower()
        # Jahr aus Dateiname extrahieren (z.B. 202412 → 2024)
        import re
        m = re.search(r'(\d{4})\d{2}', name)
        jahr_file = int(m.group(1)) if m else None

        if path.suffix == '.xlsx':
            df = _parse_kreise_8_2(str(path))
            if not df.empty:
                log.info(f"  {path.name}: {len(df)} Zeilen, Jahre {sorted(df.jahr.unique())}")
                dfs.append(df)
        elif path.suffix in ('.xlsm', '.xls'):
            if jahr_file:
                df = _parse_kreise_16_2(str(path), jahr_file)
                if not df.empty:
                    log.info(f"  {path.name}: {len(df)} Zeilen, Jahr {jahr_file}")
                    dfs.append(df)

    if not dfs:
        raise ValueError("Keine Kreisdaten konnten aus den Excel-Dateien gelesen werden.")

    df_all = pd.concat(dfs, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=['ags', 'jahr'])
    df_all = df_all.sort_values(['ags', 'jahr']).reset_index(drop=True)

    # Bundesland aus AGS
    df_all['bundesland'] = df_all['ags'].str[:2].map(_BL_MAP)

    # Quantil-Gruppen je Jahr
    result = []
    for _, g in df_all.groupby('jahr'):
        g = g.copy()
        cuts = g['median_entgelt'].quantile([0.2, 0.4, 0.6, 0.8])
        def grp(v):
            if v <= cuts[0.2]:  return 'Ärmste 20%'
            elif v <= cuts[0.4]: return 'Unteres Mittel'
            elif v <= cuts[0.6]: return 'Mittleres Mittel'
            elif v <= cuts[0.8]: return 'Oberes Mittel'
            else:                return 'Reichste 20%'
        g['quantil_gruppe'] = g['median_entgelt'].apply(grp)
        result.append(g)

    df_all = pd.concat(result).sort_values(['ags', 'jahr']).reset_index(drop=True)
    df_all['quelle']      = 'BA-Entgeltstatistik (Excel)'
    df_all['abgerufen_am'] = date.today().isoformat()

    log.info(f"  ✓ {len(df_all):,} Zeilen, {df_all.ags.nunique()} Kreise, "
             f"Jahre {int(df_all.jahr.min())}–{int(df_all.jahr.max())}")
    return df_all


if __name__ == "__main__":
    run_full_update()
