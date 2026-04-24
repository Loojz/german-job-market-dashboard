"""
Alle DuckDB-Abfragen zentral.
Keine Schätzfaktoren — nur offizielle Daten aus den Parquets.
"""

import pandas as pd
from src.pipeline import get_db_connection, ensure_data_exists


def _con():
    ensure_data_exists()
    return get_db_connection()


# ── Arbeitslose ──────────────────────────────────────────────────────────────

def query_arbeitslose(
    bundeslaender: list[str] | None = None,
    start: str = "2015-01",
    end:   str = "2024-12",
    metrik: str = "arbeitslose_gesamt",
) -> pd.DataFrame:
    con = _con()
    al_cols = [r[0] for r in con.execute("DESCRIBE arbeitslose").fetchall()]
    bl_filter = ""
    if bundeslaender:
        bl_quoted = ", ".join(f"'{b}'" for b in bundeslaender)
        bl_filter = f"AND bundesland IN ({bl_quoted})"

    # Sicherstellen dass metrik im Parquet existiert
    if metrik not in al_cols:
        metrik = "arbeitslose_gesamt"

    ub = "unterbeschaeftigung" if "unterbeschaeftigung" in al_cols else "NULL AS unterbeschaeftigung"

    q = f"""
        SELECT datum, bundesland, bl_code,
               {metrik}    AS wert,
               arbeitslose_gesamt,
               {ub},
               quelle
        FROM   arbeitslose
        WHERE  datum BETWEEN '{start}-01' AND '{end}-01'
        {bl_filter}
        ORDER  BY datum, bundesland
    """
    return con.execute(q).df()


def query_arbeitslose_bundesweit(start: str = "2015-01", end: str = "2024-12") -> pd.DataFrame:
    q = f"""
        SELECT datum,
               SUM(arbeitslose_gesamt)          AS arbeitslose_gesamt,
               SUM(unterbeschaeftigung)          AS unterbeschaeftigung,
               SUM(unterbeschaeftigung_sb)       AS unterbeschaeftigung_sb
        FROM   arbeitslose
        WHERE  datum BETWEEN '{start}-01' AND '{end}-01'
        GROUP  BY datum
        ORDER  BY datum
    """
    return _con().execute(q).df()


def query_yoy_change(metrik: str = "arbeitslose_gesamt") -> pd.DataFrame:
    q = f"""
        WITH monatlich AS (
            SELECT datum, SUM({metrik}) AS wert
            FROM   arbeitslose
            GROUP  BY datum
        ),
        mit_vorjahr AS (
            SELECT datum, wert,
                   LAG(wert, 12) OVER (ORDER BY datum) AS vorjahr_wert
            FROM   monatlich
        )
        SELECT datum, wert, vorjahr_wert,
               ROUND(100.0 * (wert - vorjahr_wert) / NULLIF(vorjahr_wert, 0), 1) AS yoy_pct
        FROM   mit_vorjahr
        WHERE  vorjahr_wert IS NOT NULL
        ORDER  BY datum
    """
    return _con().execute(q).df()


# ── Beschäftigung ────────────────────────────────────────────────────────────

def query_beschaeftigung(
    bundeslaender: list[str] | None = None,
    start: str = "2015-01",
    end:   str = "2024-10",
) -> pd.DataFrame:
    con = _con()
    cols = [r[0] for r in con.execute("DESCRIBE beschaeftigung").fetchall()]
    bl_filter = ""
    if bundeslaender:
        bl_quoted = ", ".join(f"'{b}'" for b in bundeslaender)
        bl_filter = f"AND bundesland IN ({bl_quoted})"

    # Spalten je nach Parquet-Version
    if "beschaeftigte_svb" in cols:
        extra = "beschaeftigte_svb, beschaeftigte_svb_sb, beschaeftigte_geringfuegig,"
    else:
        extra = "beschaeftigte_gesamt, beschaeftigte_vz, beschaeftigte_tz,"

    q = f"""
        SELECT datum, bundesland, bl_code,
               {extra}
               quelle
        FROM   beschaeftigung
        WHERE  datum BETWEEN '{start}-01' AND '{end}-01'
        {bl_filter}
        ORDER  BY datum, bundesland
    """
    return con.execute(q).df()


# ── Erwerbstätige ────────────────────────────────────────────────────────────

def query_erwerbstaetige(
    bundeslaender: list[str] | None = None,
    start_jahr: int = 2000,
    end_jahr:   int = 2023,
) -> pd.DataFrame:
    bl_filter = ""
    if bundeslaender:
        bl_quoted = ", ".join(f"'{b}'" for b in bundeslaender)
        bl_filter = f"AND bundesland IN ({bl_quoted})"
    q = f"""
        SELECT jahr, bundesland, erwerbstaetige, quelle
        FROM   erwerbstaetige
        WHERE  jahr BETWEEN {start_jahr} AND {end_jahr}
        {bl_filter}
        ORDER  BY jahr, bundesland
    """
    return _con().execute(q).df()


# ── Mindestlohn ──────────────────────────────────────────────────────────────

def query_mindestlohn() -> pd.DataFrame:
    return _con().execute("SELECT * FROM mindestlohn ORDER BY datum").df()


# ── Regional-Snapshot ────────────────────────────────────────────────────────

def query_regional_snapshot() -> pd.DataFrame:
    """Aktuellster Wert je Bundesland — für Karte & Ranking."""
    con = _con()

    # Prüfe welche Spalten im beschaeftigung-Parquet vorhanden sind
    cols = [r[0] for r in con.execute("DESCRIBE beschaeftigung").fetchall()]

    # Kompatibel mit alter (beschaeftigte_gesamt) und neuer (beschaeftigte_svb) Struktur
    if "beschaeftigte_svb" in cols:
        be_col  = "beschaeftigte_svb"
        gfb_col = "beschaeftigte_geringfuegig" if "beschaeftigte_geringfuegig" in cols else "NULL"
    else:
        be_col  = "beschaeftigte_gesamt"
        gfb_col = "NULL"

    # Prüfe arbeitslose-Spalten
    al_cols  = [r[0] for r in con.execute("DESCRIBE arbeitslose").fetchall()]
    ub_col   = "unterbeschaeftigung" if "unterbeschaeftigung" in al_cols else "NULL"

    q = f"""
        WITH latest_al AS (
            SELECT bundesland, bl_code, MAX(datum) AS max_datum
            FROM   arbeitslose
            GROUP  BY bundesland, bl_code
        ),
        latest_be AS (
            SELECT bundesland,
                   {be_col}  AS beschaeftigte_gesamt,
                   {gfb_col} AS beschaeftigte_geringfuegig,
                   ROW_NUMBER() OVER (PARTITION BY bundesland ORDER BY datum DESC) AS rn
            FROM   beschaeftigung
        )
        SELECT  a.bundesland, a.bl_code, a.datum,
                a.arbeitslose_gesamt,
                {ub_col} AS unterbeschaeftigung,
                b.beschaeftigte_gesamt,
                b.beschaeftigte_geringfuegig
        FROM    arbeitslose  a
        JOIN    latest_al    l ON a.bundesland = l.bundesland AND a.datum = l.max_datum
        LEFT JOIN latest_be  b ON b.bundesland = a.bundesland AND b.rn = 1
        ORDER   BY a.arbeitslose_gesamt DESC
    """
    df = con.execute(q).df()

    # Arbeitslosenquote: AL / (SVB + AL) * 100
    df["arbeitslosenquote"] = (
        df["arbeitslose_gesamt"] /
        (df["beschaeftigte_gesamt"] + df["arbeitslose_gesamt"]) * 100
    ).round(1)

    return df.sort_values("arbeitslosenquote", ascending=False).reset_index(drop=True)


# ── Entgelt Kreise ────────────────────────────────────────────────────────────

def query_entgelt_kreise(
    merkmal: str = "insgesamt",
    bundeslaender: list[str] | None = None,
) -> pd.DataFrame:
    """
    Median-Entgelt nach Kreis und Jahr.
    merkmal: 'insgesamt' | 'maenner' | 'frauen' | 'u25' | '25_55' |
             '55plus' | 'deutsche' | 'auslaender' | 'akademisch' etc.
    """
    bl_filter = ""
    if bundeslaender:
        bl_quoted = ", ".join(f"'{b}'" for b in bundeslaender)
        bl_filter = f"AND bundesland IN ({bl_quoted})"
    q = f"""
        SELECT ags, kreis, bundesland, jahr, merkmal,
               median_entgelt, quantil_gruppe
        FROM   entgelt_kreise
        WHERE  merkmal = '{merkmal}'
        {bl_filter}
        ORDER  BY ags, jahr
    """
    return _con().execute(q).df()


def query_entgelt_kreis_detail(ags: str) -> pd.DataFrame:
    """Alle Merkmale für einen Kreis — für Detailansicht."""
    q = f"""
        SELECT jahr, merkmal, median_entgelt
        FROM   entgelt_kreise
        WHERE  ags = '{ags}'
        ORDER  BY jahr, merkmal
    """
    return _con().execute(q).df()
