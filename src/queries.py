"""
Alle DuckDB-Abfragen zentral – das App-Layer ruft nur diese Funktionen auf.
"""

import pandas as pd
from functools import lru_cache
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
    bl_filter = ""
    if bundeslaender:
        bl_quoted = ", ".join(f"'{b}'" for b in bundeslaender)
        bl_filter = f"AND bundesland IN ({bl_quoted})"
    q = f"""
        SELECT datum, bundesland, bl_code,
               {metrik}           AS wert,
               arbeitslose_gesamt,
               arbeitslosenquote,
               arbeitslose_u25,
               arbeitslose_ausl,
               quelle
        FROM   arbeitslose
        WHERE  datum BETWEEN '{start}-01' AND '{end}-01'
        {bl_filter}
        ORDER  BY datum, bundesland
    """
    return _con().execute(q).df()


def query_arbeitslose_bundesweit(start: str = "2015-01", end: str = "2024-12") -> pd.DataFrame:
    q = f"""
        SELECT datum,
               SUM(arbeitslose_gesamt)            AS arbeitslose_gesamt,
               ROUND(AVG(arbeitslosenquote), 1)   AS arbeitslosenquote,
               SUM(arbeitslose_u25)               AS arbeitslose_u25,
               SUM(arbeitslose_ausl)              AS arbeitslose_ausl
        FROM   arbeitslose
        WHERE  datum BETWEEN '{start}-01' AND '{end}-01'
        GROUP  BY datum
        ORDER  BY datum
    """
    return _con().execute(q).df()


def query_yoy_change(metrik: str = "arbeitslose_gesamt") -> pd.DataFrame:
    """Vorjahresvergleich in % (bundesweit)."""
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
    bl_filter = ""
    if bundeslaender:
        bl_quoted = ", ".join(f"'{b}'" for b in bundeslaender)
        bl_filter = f"AND bundesland IN ({bl_quoted})"
    q = f"""
        SELECT datum, bundesland, bl_code,
               beschaeftigte_gesamt, beschaeftigte_vz, beschaeftigte_tz, quelle
        FROM   beschaeftigung
        WHERE  datum BETWEEN '{start}-01' AND '{end}-01'
        {bl_filter}
        ORDER  BY datum, bundesland
    """
    return _con().execute(q).df()


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
    """Aktuellster Wert je Bundesland – für Karte & Ranking."""
    q = """
        WITH latest_al AS (
            SELECT bundesland, bl_code,
                   MAX(datum) AS max_datum
            FROM   arbeitslose
            GROUP  BY bundesland, bl_code
        ),
        latest_be AS (
            SELECT bundesland,
                   beschaeftigte_gesamt,
                   ROW_NUMBER() OVER (PARTITION BY bundesland ORDER BY datum DESC) AS rn
            FROM   beschaeftigung
        )
        SELECT  a.bundesland,
                a.bl_code,
                a.datum,
                a.arbeitslose_gesamt,
                a.arbeitslosenquote,
                a.arbeitslose_u25,
                b.beschaeftigte_gesamt
        FROM    arbeitslose       a
        JOIN    latest_al         l  ON a.bundesland = l.bundesland
                                    AND a.datum      = l.max_datum
        LEFT JOIN latest_be       b  ON b.bundesland = a.bundesland
                                    AND b.rn = 1
        ORDER   BY a.arbeitslosenquote DESC
    """
    return _con().execute(q).df()
