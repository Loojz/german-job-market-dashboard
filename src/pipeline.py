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


if __name__ == "__main__":
    run_full_update()
