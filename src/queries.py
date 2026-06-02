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
    """
    Erwerbstätige je Bundesland und Jahr.
    Defensive Aggregation: Falls das Parquet noch mehrere Zeilen pro Bundesland/Jahr
    enthält (alte Pipeline-Version mit Wirtschaftszweig-Aufgliederung), nehmen wir
    das Maximum — das entspricht immer dem 'Insgesamt' über alle Branchen.
    Werte sind in Tausend Personen (GENESIS-Einheit), für die Anzeige × 1000.
    """
    bl_filter = ""
    if bundeslaender:
        bl_quoted = ", ".join(f"'{b}'" for b in bundeslaender)
        bl_filter = f"AND bundesland IN ({bl_quoted})"
    q = f"""
        WITH agg AS (
            SELECT jahr, bundesland,
                   MAX(erwerbstaetige) AS erwerbstaetige_raw,
                   ANY_VALUE(quelle)   AS quelle
            FROM   erwerbstaetige
            WHERE  jahr BETWEEN {start_jahr} AND {end_jahr}
            {bl_filter}
            GROUP  BY jahr, bundesland
        )
        SELECT  jahr, bundesland,
                CASE WHEN erwerbstaetige_raw < 100000
                     THEN erwerbstaetige_raw * 1000
                     ELSE erwerbstaetige_raw
                END AS erwerbstaetige,
                quelle
        FROM    agg
        ORDER   BY jahr, bundesland
    """
    return _con().execute(q).df()


# ── Mindestlohn ──────────────────────────────────────────────────────────────

def query_mindestlohn() -> pd.DataFrame:
    return _con().execute("SELECT * FROM mindestlohn ORDER BY datum").df()


# ── Tariflohnindex (Destatis) ────────────────────────────────────────────────

def query_tariflohnindex(start_jahr: int = 2010, end_jahr: int = 2025) -> pd.DataFrame:
    """Index der tariflichen Monatsverdienste — Jahreswerte 2010–2025."""
    q = f"""
        SELECT jahr, index_2020, quelle
        FROM   tariflohnindex
        WHERE  jahr BETWEEN {int(start_jahr)} AND {int(end_jahr)}
        ORDER  BY jahr
    """
    try:
        return _con().execute(q).df()
    except Exception:
        return pd.DataFrame()


def query_mindestlohn_vs_tariflohn(basis_jahr: int = 2015) -> pd.DataFrame:
    """
    Vergleicht Mindestlohn und Tariflohnindex auf einer gemeinsamen Index-Basis.
    Standard-Basis: 2015 (Einführung des gesetzlichen Mindestlohns) = 100.
    Liefert pro Jahr: Mindestlohn €/Std., Tariflohnindex (Original 2020=100),
    und beide auf basis_jahr = 100 normalisiert.
    """
    by = int(basis_jahr)
    q = f"""
        WITH ml AS (
            SELECT EXTRACT(YEAR FROM datum) AS jahr,
                   AVG(betrag) AS mindestlohn_eur
            FROM   mindestlohn
            GROUP  BY EXTRACT(YEAR FROM datum)
        ),
        ml_full AS (
            -- Jeden Wert auf das ganze Jahr extrapolieren (forward fill)
            SELECT y.jahr,
                   LAST_VALUE(m.mindestlohn_eur IGNORE NULLS)
                       OVER (ORDER BY y.jahr ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
                       AS mindestlohn_eur
            FROM   (SELECT DISTINCT jahr FROM tariflohnindex) y
            LEFT   JOIN ml m USING (jahr)
        ),
        ml_basis AS (SELECT mindestlohn_eur FROM ml_full WHERE jahr = {by}),
        tl_basis AS (SELECT index_2020      FROM tariflohnindex WHERE jahr = {by})
        SELECT  t.jahr,
                m.mindestlohn_eur,
                t.index_2020                                                    AS tariflohn_idx2020,
                ROUND(100.0 * m.mindestlohn_eur / (SELECT mindestlohn_eur FROM ml_basis), 1) AS mindestlohn_idx,
                ROUND(100.0 * t.index_2020      / (SELECT index_2020      FROM tl_basis), 1) AS tariflohn_idx
        FROM    tariflohnindex t
        JOIN    ml_full m USING (jahr)
        WHERE   m.mindestlohn_eur IS NOT NULL
        ORDER   BY t.jahr
    """
    try:
        return _con().execute(q).df()
    except Exception:
        return pd.DataFrame()


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
        ),
        et_raw AS (
            -- Defensive Aggregation analog query_erwerbstaetige
            SELECT jahr, bundesland, MAX(erwerbstaetige) AS et_raw
            FROM   erwerbstaetige
            GROUP  BY jahr, bundesland
        ),
        latest_et AS (
            SELECT bundesland,
                   CASE WHEN et_raw < 100000 THEN et_raw * 1000 ELSE et_raw END AS erwerbstaetige,
                   ROW_NUMBER() OVER (PARTITION BY bundesland ORDER BY jahr DESC) AS rn
            FROM   et_raw
        )
        SELECT  a.bundesland, a.bl_code, a.datum,
                a.arbeitslose_gesamt,
                {ub_col} AS unterbeschaeftigung,
                b.beschaeftigte_gesamt,
                b.beschaeftigte_geringfuegig,
                e.erwerbstaetige
        FROM    arbeitslose  a
        JOIN    latest_al    l ON a.bundesland = l.bundesland AND a.datum = l.max_datum
        LEFT JOIN latest_be  b ON b.bundesland = a.bundesland AND b.rn = 1
        LEFT JOIN latest_et  e ON e.bundesland = a.bundesland AND e.rn = 1
        ORDER   BY a.arbeitslose_gesamt DESC
    """
    df = con.execute(q).df()

    # Arbeitslosenquote = AL / Zivile Erwerbspersonen × 100
    # Ziv. Erwerbspersonen ≈ Erwerbstätige (VGR) + Arbeitslose
    # Fallback (falls keine ET-Daten): AL / (SVB + AL) — bekanntermaßen zu hoch
    df["arbeitslosenquote"] = df.apply(
        lambda r: (
            round(r["arbeitslose_gesamt"] / (r["erwerbstaetige"] + r["arbeitslose_gesamt"]) * 100, 1)
            if pd.notna(r.get("erwerbstaetige")) and r["erwerbstaetige"] > 0
            else round(r["arbeitslose_gesamt"] / (r["beschaeftigte_gesamt"] + r["arbeitslose_gesamt"]) * 100, 1)
            if pd.notna(r.get("beschaeftigte_gesamt")) and r["beschaeftigte_gesamt"] > 0
            else None
        ),
        axis=1,
    )

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


def query_quintil_verlauf(merkmal: str = "insgesamt") -> pd.DataFrame:
    """Ø Entgelt je Quantil-Gruppe und Jahr — für Trendvergleich über die Zeit."""
    m = merkmal.replace("'", "")
    q = f"""
        WITH basis AS (
            SELECT ags, jahr, quantil_gruppe
            FROM   entgelt_kreise
            WHERE  merkmal = 'insgesamt' AND quantil_gruppe IS NOT NULL
        )
        SELECT  e.jahr,
                b.quantil_gruppe,
                ROUND(AVG(e.median_entgelt), 0) AS avg_entgelt,
                COUNT(DISTINCT e.ags)            AS n_kreise
        FROM    entgelt_kreise e
        JOIN    basis b ON e.ags = b.ags AND e.jahr = b.jahr
        WHERE   e.merkmal = '{m}'
        GROUP   BY e.jahr, b.quantil_gruppe
        ORDER   BY e.jahr, b.quantil_gruppe
    """
    try:
        return _con().execute(q).df()
    except Exception:
        return pd.DataFrame()


def _quintil_filter(gruppe: str, andere: str | None = None) -> str:
    """SQL-Filter-Fragment für eine Quintil-Gruppe.
       'Alle anderen' = alle Quintile außer 'andere'."""
    g = str(gruppe).replace("'", "")
    if g == "Alle anderen" and andere:
        a = str(andere).replace("'", "")
        return f"(b.quantil_gruppe IS NOT NULL AND b.quantil_gruppe <> '{a}')"
    return f"b.quantil_gruppe = '{g}'"


def query_gruppen_vergleich(
    merkmal: str = "insgesamt",
    gruppe_a: str = "Ärmste 20%",
    gruppe_b: str = "Reichste 20%",
) -> pd.DataFrame:
    """
    Vergleicht die Entgeltentwicklung zweier frei wählbarer Quintil-Gruppen.
    'Alle anderen' als Wert für gruppe_b bedeutet: alle Quintile außer gruppe_a.
    """
    m         = str(merkmal).replace("'", "")
    filter_a  = _quintil_filter(gruppe_a)
    filter_b  = _quintil_filter(gruppe_b, andere=gruppe_a)
    q = f"""
        WITH basis AS (
            SELECT ags, jahr, quantil_gruppe
            FROM   entgelt_kreise
            WHERE  merkmal = 'insgesamt' AND quantil_gruppe IS NOT NULL
        ),
        a AS (
            SELECT e.jahr,
                   ROUND(AVG(e.median_entgelt), 0) AS entgelt_a,
                   COUNT(DISTINCT e.ags)            AS n_a
            FROM   entgelt_kreise e
            JOIN   basis b ON e.ags = b.ags AND e.jahr = b.jahr
            WHERE  e.merkmal = '{m}' AND {filter_a}
            GROUP  BY e.jahr
        ),
        b AS (
            SELECT e.jahr,
                   ROUND(AVG(e.median_entgelt), 0) AS entgelt_b,
                   COUNT(DISTINCT e.ags)            AS n_b
            FROM   entgelt_kreise e
            JOIN   basis b ON e.ags = b.ags AND e.jahr = b.jahr
            WHERE  e.merkmal = '{m}' AND {filter_b}
            GROUP  BY e.jahr
        )
        SELECT  a.jahr,
                a.entgelt_a,
                b.entgelt_b,
                (b.entgelt_b - a.entgelt_a)                                       AS gap_absolut,
                ROUND(100.0 * (b.entgelt_b - a.entgelt_a)
                      / NULLIF(a.entgelt_a, 0), 1)                                AS gap_pct,
                a.n_a,
                b.n_b
        FROM    a
        JOIN    b ON a.jahr = b.jahr
        ORDER   BY a.jahr
    """
    try:
        return _con().execute(q).df()
    except Exception:
        return pd.DataFrame()


# Backward-compat Alias — falls anderswo noch genutzt
def query_armste_vs_rest(merkmal: str = "insgesamt",
                         vergleichs_gruppe: str = "Reichste 20%") -> pd.DataFrame:
    vg = "Alle anderen" if vergleichs_gruppe == "Restliche 80%" else vergleichs_gruppe
    df = query_gruppen_vergleich(merkmal, "Ärmste 20%", vg)
    if df.empty:
        return df
    return df.rename(columns={
        "entgelt_a": "entgelt_armste", "entgelt_b": "entgelt_vergleich",
        "n_a": "n_armste", "n_b": "n_vergleich",
    })


def query_kreis_story(ags: str, merkmal: str = "insgesamt") -> pd.DataFrame:
    """
    Zeitverlauf eines Kreises: Lohn, Quintil-Gruppe und Rang über alle Jahre.
    - Lohn-Rang bezieht sich auf das gewählte Merkmal
    - Quintil-Gruppe immer auf Basis 'insgesamt' (stabile Klassifizierung)
    - n_kreise = Anzahl gerankter Kreise im jeweiligen Jahr
    """
    a = str(ags).replace("'", "")
    m = str(merkmal).replace("'", "")
    q = f"""
        WITH lohn AS (
            SELECT jahr, ags, kreis, bundesland, median_entgelt,
                   RANK() OVER (PARTITION BY jahr ORDER BY median_entgelt DESC) AS rang,
                   COUNT(*) OVER (PARTITION BY jahr)                            AS n_kreise
            FROM   entgelt_kreise
            WHERE  merkmal = '{m}' AND median_entgelt IS NOT NULL
        ),
        quintil AS (
            SELECT jahr, ags, quantil_gruppe
            FROM   entgelt_kreise
            WHERE  merkmal = 'insgesamt' AND quantil_gruppe IS NOT NULL
        )
        SELECT  l.jahr, l.kreis, l.bundesland,
                l.median_entgelt, q.quantil_gruppe,
                l.rang, l.n_kreise
        FROM    lohn l
        LEFT JOIN quintil q ON l.ags = q.ags AND l.jahr = q.jahr
        WHERE   l.ags = '{a}'
        ORDER   BY l.jahr
    """
    try:
        return _con().execute(q).df()
    except Exception:
        return pd.DataFrame()


def query_kreis_liste() -> pd.DataFrame:
    """AGS + Kreis + Bundesland (eindeutig) für Kreis-Dropdowns."""
    q = """
        SELECT DISTINCT ags, kreis, bundesland
        FROM   entgelt_kreise
        WHERE  merkmal = 'insgesamt'
        ORDER  BY bundesland, kreis
    """
    try:
        return _con().execute(q).df()
    except Exception:
        return pd.DataFrame()


def query_entgelt_snapshot(jahr: int, merkmal: str = "insgesamt") -> pd.DataFrame:
    """Entgelt-Querschnitt je Kreis für ein Jahr — Basis für Choropleth-Karte."""
    m = str(merkmal).replace("'", "")
    q = f"""
        SELECT  ags, kreis, bundesland, median_entgelt, quantil_gruppe
        FROM    entgelt_kreise
        WHERE   jahr = {int(jahr)} AND merkmal = '{m}'
        ORDER   BY ags
    """
    try:
        return _con().execute(q).df()
    except Exception:
        return pd.DataFrame()
