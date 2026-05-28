"""
Datenpipeline: Arbeitsmarkt-Dashboard Deutschland
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DATENQUELLEN (alle offiziell, keine Schätzungen):

1. BA-Statistik API (kostenlos, keine Registrierung)
   → Arbeitslosigkeit + Unterbeschäftigung nach Bundesland (EckwerteZeitreiheALOBL)
   → Beschäftigung nach Bundesland (EckwerteZeitreiheBSTBL)

2. GENESIS-API (Destatis) — Token aus .env: GENESIS_USERNAME
   → Erwerbstätige nach Bundesland, jährlich (Tabelle 13311-0002)

3. BA-Entgeltstatistik Excel (lokale Dateien, Stichtag 31.12.)
   → Median-Bruttoentgelt nach Kreis, Geschlecht, Alter, Nationalität
   → Sheet 8.2 (xlsx, Zeitreihe 2020–2024) + Sheet 16.2 (xlsm, 2015–2019)
   → Quelle: statistik.arbeitsagentur.de → Entgelt

4. Mindestlohn (hartkodiert aus amtlichen MiLoKo-Beschlüssen)
   → Quelle: mindestlohn-kommission.de

HINWEIS: Keine Schätzfaktoren oder Näherungswerte.
Alle Spalten kommen direkt aus offiziellen Quellen.
"""

import io
import os
import re
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
BL_MAP = {
    "01": "Schleswig-Holstein", "02": "Hamburg", "03": "Niedersachsen",
    "04": "Bremen", "05": "Nordrhein-Westfalen", "06": "Hessen",
    "07": "Rheinland-Pfalz", "08": "Baden-Württemberg", "09": "Bayern",
    "10": "Saarland", "11": "Berlin", "12": "Brandenburg",
    "13": "Mecklenburg-Vorpommern", "14": "Sachsen", "15": "Sachsen-Anhalt",
    "16": "Thüringen",
}


# ═══════════════════════════════════════════════════════════
# 1. BA-STATISTIK API
# ═══════════════════════════════════════════════════════════

BA_API_BASE = "https://statistik-dr.arbeitsagentur.de/bifrontend/bids-api/ct/v1/tableFetch/csv"
BA_HEADERS  = {"User-Agent": "ArbeitsmarktDashboard/1.0 (THWS Uni-Projekt)"}


def _fetch_ba_csv(table: str, params: dict, retries: int = 3) -> pd.DataFrame:
    """BA-API: CSV abrufen mit Retry-Logik."""
    url = f"{BA_API_BASE}/{table}"
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=BA_HEADERS, timeout=60)
            if r.status_code == 404:
                raise FileNotFoundError(f"BA-API: Tabelle '{table}' nicht gefunden")
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
    header_idx = next((i for i, l in enumerate(lines) if "Berichtsmonat" in l), None)
    if header_idx is None:
        raise ValueError(f"Keine Header-Zeile gefunden.\nErste 400 Zeichen: {r.text[:400]}")

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
    """
    Arbeitslosigkeit + Unterbeschäftigung nach Bundesland.
    Quelle: BA-API EckwerteZeitreiheALOBL
    Spalten: Arbeitslose, Arbeitslose saisonbereinigt,
             Unterbeschäftigung, Unterbeschäftigung saisonbereinigt
    """
    log.info("BA-API: Arbeitslosenzahlen nach Bundesland …")
    records = []

    for bl in BUNDESLAENDER:
        try:
            df = _fetch_ba_csv(
                "EckwerteZeitreiheALOBL",
                {"1|Bundesland_BEAB": bl, "Bundesland": bl}
            )
            datum_col = next(
                (c for c in df.columns if "monat" in c.lower()), None
            )
            # Exakte Spaltennamen aus der API
            alo_col   = next((c for c in df.columns if c.strip() == "Arbeitslose"), None)
            alo_sb    = next((c for c in df.columns if "saisonbereinigt" in c.lower()
                              and "unterbeschäftigung" not in c.lower()), None)
            ub_col    = next((c for c in df.columns if "unterbeschäftigung" in c.lower()
                              and "saison" not in c.lower()), None)
            ub_sb     = next((c for c in df.columns if "unterbeschäftigung" in c.lower()
                              and "saisonbereinigt" in c.lower()), None)

            if datum_col is None or alo_col is None:
                log.warning(f"  {bl}: Spalten nicht erkannt: {list(df.columns)}")
                continue

            for _, row in df.iterrows():
                datum = pd.to_datetime(str(row[datum_col]), format="%B %Y", errors="coerce")
                if pd.isna(datum):
                    datum = pd.to_datetime(str(row[datum_col]), errors="coerce")
                alo = pd.to_numeric(str(row[alo_col]).replace(".", "").replace(",", "."), errors="coerce")
                if pd.notna(datum) and pd.notna(alo):
                    def safe_int(val):
                        v = pd.to_numeric(str(val).replace(".", "").replace(",", "."), errors="coerce")
                        return int(v) if pd.notna(v) else None

                    rec = {
                        "datum":                      datum,
                        "bundesland":                 bl,
                        "bl_code":                    BA_BL_CODES[bl],
                        "arbeitslose_gesamt":          int(alo),
                        "arbeitslose_saisonbereinigt": safe_int(row[alo_sb]) if alo_sb else None,
                        "unterbeschaeftigung":         safe_int(row[ub_col])  if ub_col  else None,
                        "unterbeschaeftigung_sb":      safe_int(row[ub_sb])   if ub_sb   else None,
                    }
                    records.append(rec)
            time.sleep(1.0)

        except Exception as e:
            log.warning(f"  {bl}: {e}")
            continue

    if not records:
        raise RuntimeError("BA-API: Keine Arbeitslosendaten erhalten.")

    df_out = pd.DataFrame(records)
    df_out["quelle"]      = "BA-Statistik-API (EckwerteZeitreiheALOBL)"
    df_out["abgerufen_am"] = date.today().isoformat()
    log.info(f"  ✓ {len(df_out):,} Zeilen, {df_out['bundesland'].nunique()} Bundesländer")
    return df_out


def fetch_ba_beschaeftigung() -> pd.DataFrame:
    """
    Beschäftigung nach Bundesland.
    Quelle: BA-API EckwerteZeitreiheBSTBL
    Spalten: Beschäftigte (gesamt), SVB, SVB saisonbereinigt,
             geringfügig Beschäftigte
    """
    log.info("BA-API: Beschäftigung nach Bundesland …")
    records = []

    for bl in BUNDESLAENDER:
        try:
            df = _fetch_ba_csv(
                "EckwerteZeitreiheBSTBL",
                {"1|Bundesland_BEAB": bl, "Bundesland AO": bl}
            )
            datum_col = next(
                (c for c in df.columns if "monat" in c.lower()), None
            )
            # Exakte Spaltennamen aus der API
            be_col  = next((c for c in df.columns if c.strip() == "Beschäftigte"), None)
            svb_col = next((c for c in df.columns
                            if "sozialversicherungspflichtig beschäftigte" in c.lower()
                            and "saison" not in c.lower()), None)
            svb_sb  = next((c for c in df.columns
                            if "sozialversicherungspflichtig beschäftigte" in c.lower()
                            and "saisonbereinigt" in c.lower()), None)
            gfb_col = next((c for c in df.columns
                            if "geringfügig" in c.lower()), None)

            if datum_col is None or (be_col is None and svb_col is None):
                log.warning(f"  {bl}: Spalten nicht erkannt: {list(df.columns)}")
                continue

            for _, row in df.iterrows():
                datum = pd.to_datetime(str(row[datum_col]), format="%B %Y", errors="coerce")
                if pd.isna(datum):
                    datum = pd.to_datetime(str(row[datum_col]), errors="coerce")
                be  = pd.to_numeric(str(row[be_col]).replace(".", ""), errors="coerce") if be_col else None
                svb = pd.to_numeric(str(row[svb_col]).replace(".", ""), errors="coerce") if svb_col else None

                if pd.notna(datum) and (pd.notna(be) or pd.notna(svb)):
                    def safe_int(val):
                        v = pd.to_numeric(str(val).replace(".", "").replace(",", "."), errors="coerce")
                        return int(v) if pd.notna(v) else None

                    records.append({
                        "datum":                     datum,
                        "bundesland":                bl,
                        "bl_code":                   BA_BL_CODES[bl],
                        "beschaeftigte_gesamt":       safe_int(row[be_col])  if be_col  else None,
                        "beschaeftigte_svb":          safe_int(row[svb_col]) if svb_col else None,
                        "beschaeftigte_svb_sb":       safe_int(row[svb_sb])  if svb_sb  else None,
                        "beschaeftigte_geringfuegig": safe_int(row[gfb_col]) if gfb_col else None,
                    })
            time.sleep(1.0)

        except Exception as e:
            log.warning(f"  {bl}: {e}")
            continue

    if not records:
        raise RuntimeError("BA-API: Keine Beschäftigungsdaten erhalten.")

    df_out = pd.DataFrame(records)
    df_out["quelle"]       = "BA-Statistik-API (EckwerteZeitreiheBSTBL)"
    df_out["abgerufen_am"] = date.today().isoformat()
    log.info(f"  ✓ {len(df_out):,} Zeilen, {df_out['bundesland'].nunique()} Bundesländer")
    return df_out


# ═══════════════════════════════════════════════════════════
# 2. GENESIS-API (Destatis)
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
    Erwerbstätige nach Bundesland, jährlich (VGR-Konzept).
    GENESIS Tabelle 13311-0002, Format ffcsv (gezippt).
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

    try:
        zf       = zipfile.ZipFile(io.BytesIO(r.content))
        csv_file = zf.open(zf.namelist()[0])
    except zipfile.BadZipFile:
        try:
            err = r.json()
            raise ValueError(f"GENESIS: {err.get('Status', {}).get('Content', r.text[:300])}")
        except Exception:
            raise ValueError(f"GENESIS: Unerwartete Antwort: {r.text[:300]}")

    df = pd.read_csv(
        csv_file, delimiter=";", decimal=",",
        na_values=["...", ".", "-", "/", "x"],
        on_bad_lines="skip",
    )

    # Nur Erwerbstätige (Inlandskonzept), keine Veränderungsraten
    df = df[df["value_variable_label"].str.strip() == "Erwerbstätige (Inlandskonzept)"].copy()
    df = df[df["1_variable_attribute_label"].isin(BUNDESLAENDER)].copy()

    # GENESIS 13311-0002 hat ein zweites Merkmal (Wirtschaftszweige WZ08).
    # Wir wollen nur das "Insgesamt" über alle Branchen pro Bundesland/Jahr.
    if "2_variable_attribute_label" in df.columns:
        labels_2 = df["2_variable_attribute_label"].astype(str).str.strip()
        # Häufige Insgesamt-Bezeichnungen in GENESIS
        insgesamt_mask = labels_2.str.lower().isin([
            "insgesamt",
            "wirtschaftsbereiche zusammen",
            "alle wirtschaftszweige",
            "wz08-insgesamt",
        ])
        if insgesamt_mask.any():
            df = df[insgesamt_mask].copy()
            log.info(f"  Wirtschaftszweig-Filter: 'Insgesamt' → {len(df):,} Zeilen")
        else:
            # Fallback: pro Bundesland/Jahr die maximale Zahl behalten
            # (Total über alle Branchen ist immer die größte Summe)
            log.warning("  Kein 'Insgesamt'-Wirtschaftszweig erkannt — nutze MAX pro Bundesland/Jahr")
            df["_v"] = pd.to_numeric(df["value"], errors="coerce")
            df = (
                df.sort_values("_v", ascending=False)
                  .drop_duplicates(subset=["1_variable_attribute_label", "time"], keep="first")
                  .drop(columns="_v")
            )

    # Einheit aus value_unit lesen und normalisieren
    # GENESIS liefert Erwerbstätige in "1000" (Tausend Personen)
    # value_unit-Spalte enthält die Maßeinheit — wir lesen sie direkt aus
    einheit = df["value_unit"].iloc[0] if "value_unit" in df.columns and len(df) > 0 else "Anzahl"
    log.info(f"  GENESIS Einheit: '{einheit}'")

    wert = pd.to_numeric(df["value"], errors="coerce")

    # Normalisierung auf absolute Personen-Zahlen
    if einheit.strip() == "1000":
        wert = (wert * 1000).round(0)
        log.info("  → Umgerechnet: × 1.000 (Tausend → absolut)")
    elif einheit.strip() in ("Mill.", "Mio.", "1000000"):
        wert = (wert * 1_000_000).round(0)
        log.info("  → Umgerechnet: × 1.000.000 (Mio. → absolut)")
    # Sonst: Wert ist bereits absolut

    result = pd.DataFrame({
        "bundesland":     df["1_variable_attribute_label"].str.strip(),
        "jahr":           pd.to_numeric(df["time"], errors="coerce"),
        "erwerbstaetige": wert,
    }).dropna()

    result["erwerbstaetige"] = result["erwerbstaetige"].astype(int)
    result["quelle"]         = "GENESIS-Destatis (13311-0002)"
    result["abgerufen_am"]   = date.today().isoformat()
    log.info(f"  ✓ {len(result):,} Zeilen, Jahre {int(result.jahr.min())}–{int(result.jahr.max())}")
    return result


# ═══════════════════════════════════════════════════════════
# 3. ENTGELT NACH KREISEN (BA-Entgeltstatistik Excel)
# Quelle: statistik.arbeitsagentur.de → Entgelt
# Alle Werte offiziell aus den Excel-Dateien, keine Schätzungen.
# Untergruppen: Insgesamt, Männer, Frauen, unter 25, 25-55, 55+,
#               Deutsche, Ausländer, Berufsabschluss-Gruppen
# ═══════════════════════════════════════════════════════════

# Merkmal-Mapping: Spalte 2 in xlsx Sheet 8.2
MERKMALE_8_2 = {
    "Insgesamt":                    "insgesamt",
    "Männer":                       "maenner",
    "Frauen":                       "frauen",
    "unter 25 Jahre":               "u25",
    "25 bis unter 55 Jahre":        "25_55",
    "55 Jahre und älter":           "55plus",
    "Deutsche":                     "deutsche",
    "Ausländer":                    "auslaender",
    "ohne Berufsabschluss":         "ohne_abschluss",
    "anerkannter Berufsabschluss":  "mit_abschluss",
    "akademischer Berufsabschluss": "akademisch",
    "Helfer":                       "helfer",
    "Fachkraft":                    "fachkraft",
    "Spezialist":                   "spezialist",
    "Experte":                      "experte",
}

# Spalten-Mapping für xlsm Sheet 16.2
MERKMALE_16_2 = {
    2: "insgesamt",
    3: "maenner",
    4: "frauen",
    5: "deutsche",
    6: "auslaender",
    7: "u25",
}


def _parse_xlsx_8_2(path: str) -> pd.DataFrame:
    """Sheet 8.2: Zeitreihe 2020–2024, alle Kreise, alle Merkmale."""
    xl = pd.ExcelFile(path)
    if '8.2' not in xl.sheet_names:
        return pd.DataFrame()
    df_raw = xl.parse('8.2', header=None)

    # Jahre aus Zeile 8
    jahre = []
    for v in df_raw.iloc[8, 3:]:
        try:
            j = pd.to_datetime(v).year
            if 2000 <= j <= 2030:
                jahre.append(j)
        except Exception:
            pass

    # Kreiszeilen: 5-stellige AGS in Spalte 0
    kreise_idx = df_raw[
        df_raw[0].astype(str).str.match(r'^\d{5}$', na=False)
    ].index

    records = []
    for idx in kreise_idx:
        row = df_raw.iloc[idx]
        ags    = str(row[0])
        name   = str(row[1]).strip()
        merkmal_raw = str(row[2]).strip()
        merkmal = MERKMALE_8_2.get(merkmal_raw)
        if merkmal is None:
            continue
        for i, jahr in enumerate(jahre):
            val = pd.to_numeric(row[3 + i], errors="coerce")
            if pd.notna(val):
                records.append({
                    "ags":           ags,
                    "kreis":         name,
                    "jahr":          int(jahr),
                    "merkmal":       merkmal,
                    "median_entgelt": round(float(val), 2),
                })
    return pd.DataFrame(records)


def _parse_xlsm_16_2(path: str, jahr: int) -> pd.DataFrame:
    """Sheet 16.2: Querschnitt, ein Jahr, Kreise mit Merkmalen in Spalten."""
    xl = pd.ExcelFile(path)
    sheet = next((s for s in xl.sheet_names if '16.2' in s), None)
    if sheet is None:
        return pd.DataFrame()
    df_raw = xl.parse(sheet, header=None)

    records = []
    for _, row in df_raw.iterrows():
        name = str(row[0]).strip()
        key  = row[1]
        if pd.isna(key) or name in ['Deutschland', 'nan', 'Region', '']:
            continue
        try:
            ags = str(int(float(key))).zfill(5)
            if len(ags) != 5 or not ags.isdigit():
                continue
        except Exception:
            continue

        for col_idx, merkmal in MERKMALE_16_2.items():
            if col_idx < len(row):
                val = pd.to_numeric(row[col_idx], errors="coerce")
                if pd.notna(val):
                    records.append({
                        "ags":           ags,
                        "kreis":         name,
                        "jahr":          jahr,
                        "merkmal":       merkmal,
                        "median_entgelt": round(float(val), 2),
                    })
    return pd.DataFrame(records)


def fetch_entgelt_kreise(data_dir: str = None) -> pd.DataFrame:
    """
    Liest alle vorhandenen Entgelt-Excel-Dateien ein.
    Zeitreihe 2015–2024 × ~400 Kreise × Merkmale (Geschlecht, Alter, Nationalität).
    Alle Werte offiziell aus BA-Entgeltstatistik.
    """
    log.info("Entgelt-Kreise: Excel-Dateien einlesen …")

    search_dir = Path(data_dir) if data_dir else ROOT
    excel_files = (
        list(search_dir.glob("entgelt-*.xlsx")) +
        list(search_dir.glob("entgelt-*.xlsm")) +
        list((search_dir / "data").glob("entgelt-*.xlsx")) +
        list((search_dir / "data").glob("entgelt-*.xlsm"))
    )

    if not excel_files:
        raise FileNotFoundError(
            "Keine Entgelt-Excel-Dateien gefunden.\n"
            "Dateien (entgelt-*.xlsx / entgelt-*.xlsm) in den Projektordner legen."
        )

    dfs = []
    for path in sorted(excel_files):
        name = path.name.lower()
        m = re.search(r'(\d{4})\d{2}', name)
        jahr_file = int(m.group(1)) if m else None

        if path.suffix == '.xlsx':
            df = _parse_xlsx_8_2(str(path))
            if not df.empty:
                log.info(f"  {path.name}: {len(df)} Zeilen, Jahre {sorted(df.jahr.unique())}")
                dfs.append(df)
        elif path.suffix in ('.xlsm', '.xls') and jahr_file:
            df = _parse_xlsm_16_2(str(path), jahr_file)
            if not df.empty:
                log.info(f"  {path.name}: {len(df)} Zeilen, Jahr {jahr_file}")
                dfs.append(df)

    if not dfs:
        raise ValueError("Keine Kreisdaten aus den Excel-Dateien lesbar.")

    df_all = pd.concat(dfs, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["ags", "jahr", "merkmal"])
    df_all = df_all.sort_values(["ags", "jahr", "merkmal"]).reset_index(drop=True)
    df_all["bundesland"] = df_all["ags"].str[:2].map(BL_MAP)

    # Quantil-Gruppen je Jahr (nur für Insgesamt)
    insgesamt = df_all[df_all["merkmal"] == "insgesamt"].copy()
    result = []
    for _, g in insgesamt.groupby("jahr"):
        g = g.copy()
        cuts = g["median_entgelt"].quantile([0.2, 0.4, 0.6, 0.8])
        def grp(v):
            if v <= cuts[0.2]:   return "Ärmste 20%"
            elif v <= cuts[0.4]: return "Unteres Mittel"
            elif v <= cuts[0.6]: return "Mittleres Mittel"
            elif v <= cuts[0.8]: return "Oberes Mittel"
            else:                return "Reichste 20%"
        g["quantil_gruppe"] = g["median_entgelt"].apply(grp)
        result.append(g)

    insgesamt_mit_gruppe = pd.concat(result)[["ags", "jahr", "quantil_gruppe"]]
    df_all = df_all.merge(insgesamt_mit_gruppe, on=["ags", "jahr"], how="left")

    df_all["quelle"]       = "BA-Entgeltstatistik (Excel, Stichtag 31.12.)"
    df_all["abgerufen_am"] = date.today().isoformat()

    kreise = df_all["ags"].nunique()
    jahre  = f"{int(df_all.jahr.min())}–{int(df_all.jahr.max())}"
    log.info(f"  ✓ {len(df_all):,} Zeilen, {kreise} Kreise, Jahre {jahre}")
    return df_all


# ═══════════════════════════════════════════════════════════
# 4. MINDESTLOHN (hartkodiert — korrekt, da amtliche Beschlüsse)
# Quelle: Mindestlohnkommission (mindestlohn-kommission.de)
# ═══════════════════════════════════════════════════════════

MINDESTLOHN_HISTORY = [
    {"datum": "2015-01-01", "betrag": 8.50,  "anpassung": "Einführung gesetzl. Mindestlohn"},
    {"datum": "2017-01-01", "betrag": 8.84,  "anpassung": "1. Anpassung (MiLoKo-Beschluss)"},
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

    try:
        save_parquet(fetch_entgelt_kreise(), "entgelt_kreise")
    except Exception as e:
        log.warning(f"⚠ entgelt_kreise: {e}")

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

    # entgelt_kreise: falls nicht lokal vorhanden, von HF Dataset herunterladen
    entgelt_path = DATA_PROC / "entgelt_kreise.parquet"
    if not entgelt_path.exists():
        log.info("entgelt_kreise.parquet nicht lokal → lade von HF Dataset …")
        try:
            from huggingface_hub import hf_hub_download
            path = hf_hub_download(
                repo_id="Miz777/arbeitsmarkt-daten",
                filename="entgelt_kreise.parquet",
                repo_type="dataset",
                local_dir=str(DATA_PROC),
            )
            log.info(f"  ✓ entgelt_kreise.parquet heruntergeladen: {path}")
        except Exception as e:
            log.warning(f"  ⚠ Download fehlgeschlagen: {e}")


if __name__ == "__main__":
    run_full_update()
