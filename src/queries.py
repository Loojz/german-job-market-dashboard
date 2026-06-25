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

    # ALQ aus alq_kreise (offizielle BA-Werte je Kreis) auf Bundesland aggregieren?
    has_alq_kreise = "alq_kreise" in [
        r[0] for r in con.execute("SHOW TABLES").fetchall()
    ]

    if has_alq_kreise:
        alq_bl_cte = """,
        latest_alq_jahr AS (SELECT MAX(jahr) AS j FROM alq_kreise),
        alq_bl AS (
            SELECT SUBSTR(ags, 1, 2) AS bl_code,
                   ROUND(AVG(alq), 1) AS alq_offiziell
            FROM   alq_kreise
            WHERE  jahr = (SELECT j FROM latest_alq_jahr)
            GROUP  BY SUBSTR(ags, 1, 2)
        )"""
        alq_select   = ", q.alq_offiziell"
        alq_join     = "LEFT JOIN alq_bl q ON q.bl_code = LPAD(CAST(a.bl_code AS VARCHAR), 2, '0')"
    else:
        alq_bl_cte = ""
        alq_select = ", NULL AS alq_offiziell"
        alq_join   = ""

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
        ){alq_bl_cte}
        SELECT  a.bundesland, a.bl_code, a.datum,
                a.arbeitslose_gesamt,
                {ub_col} AS unterbeschaeftigung,
                b.beschaeftigte_gesamt,
                b.beschaeftigte_geringfuegig,
                e.erwerbstaetige
                {alq_select}
        FROM    arbeitslose  a
        JOIN    latest_al    l ON a.bundesland = l.bundesland AND a.datum = l.max_datum
        LEFT JOIN latest_be  b ON b.bundesland = a.bundesland AND b.rn = 1
        LEFT JOIN latest_et  e ON e.bundesland = a.bundesland AND e.rn = 1
        {alq_join}
        ORDER   BY a.arbeitslose_gesamt DESC
    """
    df = con.execute(q).df()

    # Arbeitslosenquote in dieser Reihenfolge:
    #   1. Offizielle BA-Werte (Mittel der Kreis-ALQs aus alq_kreise)
    #   2. Näherung mit VGR-Erwerbstätigen
    #   3. Notfall-Näherung mit SVB
    def _quote(row):
        if pd.notna(row.get("alq_offiziell")):
            return float(row["alq_offiziell"])
        al = row["arbeitslose_gesamt"]
        if pd.notna(row.get("erwerbstaetige")) and row["erwerbstaetige"] > 0:
            return round(al / (row["erwerbstaetige"] + al) * 100, 1)
        if pd.notna(row.get("beschaeftigte_gesamt")) and row["beschaeftigte_gesamt"] > 0:
            return round(al / (row["beschaeftigte_gesamt"] + al) * 100, 1)
        return None

    df["arbeitslosenquote"] = df.apply(_quote, axis=1)

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


# ── MiLo-Evaluation: flexible Kreiskategorisierung + ALQ-Aggregation ────────

def query_alq_kreise(
    jahr: int | None = None,
    start_jahr: int = 2007,
    end_jahr: int = 2025,
) -> pd.DataFrame:
    """
    ALQ je Kreis aus BA-Bulk-Excel.
    - Ohne Argument: alle Jahre (für MiLo-Evaluation, query_milo_evaluation).
    - jahr=YYYY: Snapshot eines Jahres + zusätzliche Spalten für Karten/Ranking
      (bl_code, bundesland, arbeitslosenquote als Alias zu alq).
    """
    try:
        if jahr is not None:
            q = f"""
                SELECT ags, kreis,
                       LEFT(ags, 2) AS bl_code,
                       alq           AS arbeitslosenquote,
                       alq,
                       jahr,
                       ''            AS bundesland
                FROM   alq_kreise
                WHERE  jahr = {int(jahr)}
                ORDER  BY ags
            """
        else:
            q = f"""
                SELECT ags, kreis, jahr, alq
                FROM   alq_kreise
                WHERE  jahr BETWEEN {int(start_jahr)} AND {int(end_jahr)}
                ORDER  BY ags, jahr
            """
        return _con().execute(q).df()
    except Exception:
        return pd.DataFrame()


def query_alq_kreise_snapshot(jahr: int = 2024) -> pd.DataFrame:
    """Alias für query_alq_kreise(jahr=…) — explizite Single-Year-API."""
    return query_alq_kreise(jahr=jahr)


def query_arbeitslose_kreise(start_jahr: int = 1998, end_jahr: int = 2025) -> pd.DataFrame:
    """Bestand an Arbeitslosen (Jahresdurchschnitt) je Kreis und Jahr."""
    q = f"""
        SELECT ags, kreis, jahr, arbeitslose
        FROM   arbeitslose_kreise
        WHERE  jahr BETWEEN {int(start_jahr)} AND {int(end_jahr)}
        ORDER  BY ags, jahr
    """
    try:
        return _con().execute(q).df()
    except Exception:
        return pd.DataFrame()


def klassifiziere_kreise(
    df_entgelt_stichjahr: pd.DataFrame,
    modus: str = "quintil",
    abs_unter: float | None = None,
    abs_ober:  float | None = None,
) -> pd.DataFrame:
    """
    Klassifiziert Kreise nach Median-Entgelt-Stichjahr in Gruppen.
    Modus:
      'quintil'        → 5 Gruppen je 20 %
      'top_bottom_10'  → 'Untere 10 %', 'Mittlere 80 %', 'Obere 10 %'
      'top_bottom_20'  → 'Untere 20 %', 'Mittlere 60 %', 'Obere 20 %'
      'top_bottom_25'  → 'Untere 25 %', 'Mittlere 50 %', 'Obere 25 %'
      'absolut'        → '< abs_unter €', 'Mittel', '>= abs_ober €'
    Erwartet df mit Spalten: ags, kreis, median_entgelt
    Liefert df mit zusätzlicher Spalte: gruppe
    """
    df = df_entgelt_stichjahr.dropna(subset=["median_entgelt"]).copy().sort_values("median_entgelt").reset_index(drop=True)
    n = len(df)
    if n == 0:
        df["gruppe"] = pd.Series(dtype=str)
        return df

    if modus == "quintil":
        labels = ["Ärmste 20%", "Unteres Mittel", "Mittleres Mittel",
                  "Oberes Mittel", "Reichste 20%"]
        df["gruppe"] = pd.qcut(df["median_entgelt"], q=5, labels=labels,
                                duplicates="drop")
    elif modus.startswith("top_bottom_"):
        pct = int(modus.split("_")[-1])   # 10, 20, 25
        labels = [f"Untere {pct} %", f"Mittlere {100-2*pct} %", f"Obere {pct} %"]
        q1 = df["median_entgelt"].quantile(pct/100)
        q2 = df["median_entgelt"].quantile(1 - pct/100)
        df["gruppe"] = pd.cut(
            df["median_entgelt"],
            bins=[-float("inf"), q1, q2, float("inf")],
            labels=labels, include_lowest=True,
        )
    elif modus == "absolut":
        if abs_unter is None or abs_ober is None or abs_unter >= abs_ober:
            raise ValueError("absolut benötigt abs_unter < abs_ober")
        labels = [f"< {int(abs_unter)} €",
                  f"{int(abs_unter)}–{int(abs_ober)} €",
                  f">= {int(abs_ober)} €"]
        df["gruppe"] = pd.cut(
            df["median_entgelt"],
            bins=[-float("inf"), abs_unter, abs_ober, float("inf")],
            labels=labels, include_lowest=True,
        )
    else:
        raise ValueError(f"Unbekannter Modus: {modus}")

    df["gruppe"] = df["gruppe"].astype(str)
    return df


# Verfügbare Indikatoren für die MiLo-Evaluation
MILO_INDIKATOREN = {
    "alq":            "Arbeitslosenquote (%)",
    "arbeitslose":    "Arbeitslose (Bestand)",
    "erwerbspersonen": "Zivile Erwerbspersonen",
    "entgelt":        "Median-Entgelt (€/Monat)",
}


def query_milo_evaluation(
    modus: str = "quintil",
    stichjahr: int = 2014,
    abs_unter: float | None = None,
    abs_ober:  float | None = None,
    merkmal:   str = "insgesamt",
    indikator: str = "alq",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Klassifiziert Kreise im Stichjahr nach Entgelt und aggregiert einen
    wählbaren Indikator pro Gruppe und Jahr.

    indikator:
      'alq'            → Gruppen-ALQ = Σ Arbeitslose / Σ Erwerbspersonen × 100
                          (korrekt gewichtet, konsistent mit den Komponenten)
      'arbeitslose'    → Σ Arbeitslose der Gruppe (Zähler der ALQ)
      'erwerbspersonen'→ Σ zivile Erwerbspersonen (Nenner, abgeleitet aus
                          Arbeitslose × 100 / ALQ je Kreis)
      'entgelt'        → Ø Median-Entgelt der Gruppe

    Returns (df_aggregat, df_klassifizierung):
      df_aggregat: jahr, gruppe, wert, n_kreise
      df_klassifizierung: ags, kreis, median_entgelt, gruppe
    """
    # 1. Entgelt-Stichjahr-Snapshot — Fallback auf nächstes verfügbares Jahr
    df_e = query_entgelt_snapshot(stichjahr, merkmal)
    if df_e.empty:
        verfuegbar = _con().execute(
            "SELECT DISTINCT jahr FROM entgelt_kreise ORDER BY jahr"
        ).df()["jahr"].tolist()
        if not verfuegbar:
            return pd.DataFrame(), pd.DataFrame()
        fallback = next((j for j in verfuegbar if j >= stichjahr), verfuegbar[0])
        df_e = query_entgelt_snapshot(fallback, merkmal)
        if df_e.empty:
            return pd.DataFrame(), pd.DataFrame()
    df_class = klassifiziere_kreise(df_e, modus, abs_unter, abs_ober)
    klass_cols = df_class[["ags", "gruppe"]]

    # 2. Indikator-spezifische Zeitreihe je Kreis holen + auf Gruppe aggregieren
    if indikator == "entgelt":
        df_val = query_entgelt_kreise(merkmal)          # ags, jahr, median_entgelt
        if df_val.empty:
            return pd.DataFrame(), df_class
        merged = df_val.merge(klass_cols, on="ags", how="inner")
        agg = (
            merged.groupby(["jahr", "gruppe"], observed=True)["median_entgelt"]
                  .agg(wert="mean", n_kreise="count").reset_index()
        )
    else:
        # ALQ + Arbeitslose je Kreis zusammenführen, Erwerbspersonen ableiten
        df_alq = query_alq_kreise()                     # ags, jahr, alq
        df_al  = query_arbeitslose_kreise()             # ags, jahr, arbeitslose
        if df_alq.empty or df_al.empty:
            return pd.DataFrame(), df_class
        komp = df_alq.merge(df_al[["ags", "jahr", "arbeitslose"]],
                            on=["ags", "jahr"], how="inner")
        # Erwerbspersonen = Arbeitslose × 100 / ALQ (ALQ>0)
        komp = komp[komp["alq"] > 0].copy()
        komp["erwerbspersonen"] = komp["arbeitslose"] * 100.0 / komp["alq"]
        merged = komp.merge(klass_cols, on="ags", how="inner")

        grp = merged.groupby(["jahr", "gruppe"], observed=True)
        summe = grp.agg(
            arbeitslose=("arbeitslose", "sum"),
            erwerbspersonen=("erwerbspersonen", "sum"),
            n_kreise=("ags", "count"),
        ).reset_index()
        if indikator == "arbeitslose":
            summe["wert"] = summe["arbeitslose"]
        elif indikator == "erwerbspersonen":
            summe["wert"] = summe["erwerbspersonen"]
        else:  # 'alq' — korrekt gewichtet
            summe["wert"] = (summe["arbeitslose"] * 100.0
                             / summe["erwerbspersonen"])
        agg = summe[["jahr", "gruppe", "wert", "n_kreise"]]

    agg = agg.copy()
    agg["wert"] = agg["wert"].round(2)
    return agg.reset_index(drop=True), df_class


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
