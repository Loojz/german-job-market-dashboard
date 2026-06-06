"""
Arbeitsmarkt-Dashboard Deutschland
────────────────────────────────────
Lokal starten: streamlit run app.py
"""

import io
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent

from src.pipeline import ensure_data_exists, MERKMALE_8_2
from src.queries import (
    query_arbeitslose,
    query_arbeitslose_bundesweit,
    query_beschaeftigung,
    query_entgelt_snapshot,
    query_erwerbstaetige,
    query_gruppen_vergleich,
    query_alq_kreise,
    query_kreis_liste,
    query_kreis_story,
    query_milo_evaluation,
    query_mindestlohn,
    query_mindestlohn_vs_tariflohn,
    query_quintil_verlauf,
    query_regional_snapshot,
    query_tariflohnindex,
    query_yoy_change,
)
from src.charts import (
    chart_zeitreihe,
    chart_yoy,
    chart_beschaeftigung_stack,
    chart_gap_verlauf,
    chart_gruppen_vergleich,
    chart_karte,
    chart_karte_kreise,
    chart_kreis_im_kontext,
    chart_kreis_im_kontext_multi,
    chart_kreise_topbottom_bar,
    chart_milo_balken_stichtage,
    chart_milo_tabelle,
    chart_milo_zeitreihe,
    chart_mindestlohn,
    chart_mindestlohn_vs_tariflohn,
    chart_quintil_bahn,
    chart_quintil_bahn_multi,
    chart_quintil_verlauf,
    chart_rang_sparkline,
    chart_rang_sparkline_multi,
    format_ranking,
)

# ─── Seiten-Setup ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Arbeitsmarkt-Dashboard — THWS",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False


def _inject_css(dark: bool) -> None:
    if dark:
        app_bg      = "#000000"
        sidebar_bg  = "#1C1C1E"
        sidebar_brd = "#2C2C2E"
        sidebar_txt = "#F5F5F7"
        sidebar_sub = "#8E8E93"
        sidebar_hr  = "#3A3A3C"
        radio_brd   = "#48484A"
        text        = "#F5F5F7"
        text2       = "#8E8E93"
        text3       = "#EBEBF5"
        heading     = "#F5F5F7"
        hr_col      = "#3A3A3C"
        card_bg     = "#1C1C1E"
        card_txt    = "#EBEBF5"
        metric_bg   = "#1C1C1E"
        lit_brd     = "#2C2C2E"
        source_col  = "#636366"
    else:
        app_bg      = "#FFFFFF"
        sidebar_bg  = "#F5F5F7"
        sidebar_brd = "#E5E5EA"
        sidebar_txt = "#1D1D1F"
        sidebar_sub = "#6E6E73"
        sidebar_hr  = "#E5E5EA"
        radio_brd   = "#C7C7CC"
        text        = "#1D1D1F"
        text2       = "#6E6E73"
        text3       = "#3A3A3C"
        heading     = "#1D1D1F"
        hr_col      = "#E5E5EA"
        card_bg     = "#F5F5F7"
        card_txt    = "#3A3A3C"
        metric_bg   = "#F5F5F7"
        lit_brd     = "#F2F2F7"
        source_col  = "#AEAEB2"

    st.markdown(f"""
<style>
html, body, [class*="css"] {{
    font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue",
                 system-ui, sans-serif !important;
    -webkit-font-smoothing: antialiased;
}}
#MainMenu {{ visibility: hidden; }}
footer    {{ visibility: hidden; }}
header[data-testid="stHeader"] {{ background: transparent; border-bottom: none; }}

.stApp, [data-testid="stAppViewContainer"], .main {{
    background-color: {app_bg} !important;
}}
.main .block-container {{
    padding-top: 1.75rem;
    padding-bottom: 3rem;
}}

h1, h2 {{
    font-weight: 700 !important;
    letter-spacing: -0.03em !important;
    color: {heading} !important;
}}
h3 {{
    font-size: 1.05rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
    color: {heading} !important;
}}
p, span, div, label {{
    color: {text};
}}
hr {{
    border: none;
    border-top: 1px solid {hr_col};
    margin: 1.5rem 0;
}}

section[data-testid="stSidebar"] {{
    background: {sidebar_bg} !important;
    border-right: 1px solid {sidebar_brd} !important;
}}
section[data-testid="stSidebar"] * {{
    color: {sidebar_txt} !important;
}}
section[data-testid="stSidebar"] hr {{
    border-color: {sidebar_hr} !important;
}}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label {{
    font-size: 0.875rem !important;
    font-weight: 400 !important;
    letter-spacing: -0.01em !important;
}}
section[data-testid="stSidebar"] [data-baseweb="radio"] [data-checked="true"] > div {{
    background-color: #F07000 !important;
    border-color: #F07000 !important;
}}
section[data-testid="stSidebar"] [data-baseweb="radio"] > div:first-child {{
    border-color: {radio_brd} !important;
}}

[data-testid="metric-container"] {{
    background: {metric_bg} !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 1.25rem 1.5rem !important;
    border-top: 3px solid #F07000 !important;
}}
[data-testid="stMetricValue"] {{
    font-size: 1.9rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.04em !important;
    color: {text} !important;
    line-height: 1.1 !important;
}}
[data-testid="stMetricLabel"] {{
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: {text2} !important;
}}

.stDownloadButton > button {{
    background: #F07000 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    letter-spacing: -0.01em !important;
    width: 100%;
    transition: opacity 0.15s ease !important;
}}
.stDownloadButton > button:hover {{ opacity: 0.85 !important; }}

.page-hero {{
    padding: 0.5rem 0 2rem 0;
    max-width: 680px;
}}
.eyebrow {{
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #F07000 !important;
    margin: 0 0 0.5rem 0;
}}
.hero-title {{
    font-size: 2.4rem;
    font-weight: 700;
    letter-spacing: -0.04em;
    color: {heading} !important;
    line-height: 1.15;
    margin: 0 0 0.65rem 0;
}}
.hero-body {{
    font-size: 1.05rem;
    color: {text2} !important;
    font-weight: 400;
    line-height: 1.6;
    letter-spacing: -0.015em;
    margin: 0;
}}

.info-card {{
    background: {card_bg} !important;
    border-left: 3px solid #F07000;
    border-radius: 0 8px 8px 0;
    padding: 1rem 1.25rem;
    margin: 1rem 0;
}}
.info-card-label {{
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #F07000 !important;
    display: block;
    margin-bottom: 0.35rem;
}}
.info-card p {{
    font-size: 0.9rem;
    color: {card_txt} !important;
    line-height: 1.6;
    margin: 0;
}}
.info-card a {{ color: #F07000; text-decoration: none; }}
.info-card a:hover {{ text-decoration: underline; }}

.lit-entry {{
    line-height: 1.75;
    padding: 0.75rem 0;
    border-bottom: 1px solid {lit_brd};
    font-size: 0.9rem;
    color: {card_txt} !important;
}}
.lit-entry a {{ color: #F07000; text-decoration: none; }}
.lit-entry a:hover {{ text-decoration: underline; }}

.source-note {{
    font-size: 0.7rem;
    color: {source_col} !important;
    padding-top: 0.75rem;
    margin-top: 1.5rem;
    border-top: 1px solid {hr_col};
    letter-spacing: 0.01em;
}}
</style>
""", unsafe_allow_html=True)


_inject_css(st.session_state.dark_mode)


# ─── Hilfsfunktion: Hero-Header ───────────────────────────────────────────────
def hero(eyebrow: str, title: str, body: str = ""):
    body_html = f'<p class="hero-body">{body}</p>' if body else ""
    st.markdown(
        f'<div class="page-hero">'
        f'<p class="eyebrow">{eyebrow}</p>'
        f'<h1 class="hero-title">{title}</h1>'
        f'{body_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─── Daten sicherstellen ─────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Daten werden geladen …")
def _snapshot():    return query_regional_snapshot()

@st.cache_data(ttl=3600, show_spinner=False)
def _mindestlohn(): return query_mindestlohn()


# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:0.5rem 0 1.25rem 0">
        <div style="font-size:1.35rem;font-weight:800;letter-spacing:-0.03em;
                    color:#F07000;line-height:1">THWS</div>
        <div style="font-size:0.7rem;font-weight:600;text-transform:uppercase;
                    letter-spacing:0.1em;color:#8E8E93;margin-top:3px">
            Arbeitsmarkt-Dashboard
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    seite = st.radio(
        "Navigation",
        [
            "Überblick",
            "Zeitreihen",
            "Beschäftigung",
            "Mindestlohn",
            "MiLo-Evaluation",
            "Entgelt nach Kreisen",
            "Kreis-Story",
            "Download",
            "Literatur",
        ],
        label_visibility="collapsed",
    )
    st.divider()

    st.markdown(
        '<p style="font-size:0.65rem;font-weight:700;text-transform:uppercase;'
        'letter-spacing:0.1em;color:#8E8E93;margin-bottom:0.5rem">Filter</p>',
        unsafe_allow_html=True,
    )
    st.caption("Gilt für: Zeitreihen, Beschäftigung, Mindestlohn, Kreise")

    ALLE_BL = [
        "Schleswig-Holstein", "Hamburg", "Niedersachsen", "Bremen",
        "Nordrhein-Westfalen", "Hessen", "Rheinland-Pfalz", "Baden-Württemberg",
        "Bayern", "Saarland", "Berlin", "Brandenburg",
        "Mecklenburg-Vorpommern", "Sachsen", "Sachsen-Anhalt", "Thüringen",
    ]
    sel_bl = st.multiselect(
        "Bundesländer", ALLE_BL,
        default=["Bayern", "Nordrhein-Westfalen", "Berlin", "Sachsen"],
        help="Leer lassen = alle Bundesländer",
    )
    if not sel_bl:
        sel_bl = ALLE_BL

    c1, c2 = st.columns(2)
    _years = list(range(2007, 2026))
    start_j = c1.selectbox("Von", _years, index=_years.index(2015))
    end_j   = c2.selectbox("Bis", _years, index=_years.index(2024))
    if start_j > end_j:
        st.error("'Von' muss kleiner oder gleich 'Bis' sein.")
    if start_j < 2015:
        st.caption("ℹ️ Daten vor 2015 nur für Arbeitslose / Beschäftigung verfügbar.")

    start_s = f"{start_j}-01"
    end_s   = f"{end_j}-12"

    st.divider()

    dark_toggle = st.toggle(
        "Dark Mode",
        value=st.session_state.dark_mode,
        key="dm_toggle",
    )
    if dark_toggle != st.session_state.dark_mode:
        st.session_state.dark_mode = dark_toggle
        st.rerun()

    st.divider()
    st.caption(
        f"Stand: {datetime.now().strftime('%d.%m.%Y')}\n\n"
        "Quellen: [BA-Statistik](https://statistik.arbeitsagentur.de) · "
        "[GENESIS](https://www-genesis.destatis.de)"
    )


# ─── Download-Buttons ────────────────────────────────────────────────────────
def dl_buttons(df: pd.DataFrame, name: str, label: str = ""):
    if label:
        st.caption(f"**{label}** — {len(df):,} Zeilen")
    ca, cb = st.columns(2)
    with ca:
        st.download_button(
            "CSV herunterladen",
            df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            file_name=f"{name}.csv", mime="text/csv",
            use_container_width=True,
        )
    with cb:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="Daten")
            pd.DataFrame({
                "Feld":  ["Exportiert", "Quelle", "Zeilen"],
                "Wert":  [datetime.now().strftime("%d.%m.%Y %H:%M"),
                          "BA-Statistik / GENESIS Destatis", len(df)],
            }).to_excel(w, index=False, sheet_name="Metadaten")
        st.download_button(
            "Excel herunterladen",
            buf.getvalue(),
            file_name=f"{name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ÜBERBLICK
# ═══════════════════════════════════════════════════════════════════════════════
if seite == "Überblick":
    hero(
        eyebrow="Bundesrepublik Deutschland",
        title="Der Arbeitsmarkt auf einen Blick.",
        body="Aktuelle Kennzahlen zu Arbeitslosigkeit, Beschäftigung und Mindestlohn — "
             "monatlich aktualisiert aus offiziellen Quellen der Bundesagentur für Arbeit "
             "und des Statistischen Bundesamts.",
    )

    with st.expander("Was kannst du hier machen?", expanded=False):
        st.markdown("""
**Diese Seite (Überblick)** zeigt die aktuellen bundesweiten Kennzahlen plus eine interaktive Deutschland-Karte (umschaltbar zwischen Bundesländern und Kreisen, je Kreise wahlweise ALQ oder Median-Entgelt) und ein Ranking der Bundesländer nach Arbeitslosenquote.

**Weitere Seiten in der linken Navigation:**
- **Zeitreihen** — monatliche Verläufe von Arbeitslosigkeit und Beschäftigung, nach Bundesland filterbar, mit Mindestlohn-Markierungen. Daten ab 2007 (vor Mindestlohn-Einführung).
- **Beschäftigung** — sozialversicherungspflichtig Beschäftigte und Erwerbstätige (VGR) nach Bundesland, mit gestapelten Ansichten.
- **Mindestlohn** — Anpassungshistorie seit 2015, Indexvergleich mit dem allgemeinen Tariflohn (Destatis).
- **Entgelt nach Kreisen** — Median-Bruttoentgelte für rund 405 Kreise, mit Quintil-Klassifizierung, Gruppen-Vergleich und Kartenvergleich zwischen zwei Zeitpunkten.
- **Kreis-Story** — Lohnentwicklung einzelner oder mehrerer Kreise über die Zeit: in welchem Quintil waren sie, sind sie auf- oder abgestiegen, welche Platzierung unter allen Kreisen. Bei mehreren Kreisen direkter Vergleich mit überlagerten Trajektorien.
- **Download** — alle Datensätze als CSV oder Excel.
- **Literatur** — kuratierte Auswahl wissenschaftlicher Studien und Policy-Berichte.

**Bedienhinweise:** Im linken Seitenmenü stellst du Bundesländer-Filter und Jahresbereich ein (gilt für Zeitreihen, Beschäftigung und Entgelt). Unten links kannst du zwischen Light- und Dark-Mode wechseln. Bei kleinen Fragezeichen-Icons (`?`) findest du Definitionen und Methodik-Hinweise.
        """)

    with st.expander("Glossar — Fachbegriffe in einem Satz", expanded=False):
        st.markdown("""
| Begriff | Bedeutung |
|---|---|
| **Arbeitslosenquote (ALQ)** | Arbeitslose ÷ zivile Erwerbspersonen × 100. Auf Kreisebene direkt von der BA, auf Bundesland aggregiert als arithmetisches Mittel über alle Kreise. |
| **Arbeitslose** | Beim Arbeitsamt im engeren Sinn (SGB III/II) gemeldet, ohne Personen in Maßnahmen oder Kurzarbeit. |
| **Unterbeschäftigung** | Arbeitslose **plus** Personen in arbeitsmarktpolitischen Maßnahmen, Trainings und kurzzeitig arbeitsunfähige Arbeitslose. Bessere Annäherung an die tatsächliche Arbeitsmarktlücke. *Ohne* Kurzarbeit — diese ist Beschäftigung. |
| **SVB / SV-pflichtig Beschäftigte** | Arbeitnehmer mit Beiträgen zur Sozialversicherung (Renten-, Kranken-, Pflege- und Arbeitslosenversicherung). Schließt Beamte, Selbständige und Minijobs **nicht** ein. |
| **Geringfügig Beschäftigte (GeB)** | Minijob bis 538 €/Monat (Stand 2024) oder kurzfristig. Werden statistisch separat geführt. |
| **Erwerbstätige (VGR)** | Alle erwerbstätigen Personen am Wohnsitz/Arbeitsort nach Volkswirtschaftlicher Gesamtrechnung: SVB + Beamte + Selbständige + GeB. Quelle: Destatis. |
| **Median-Entgelt** | Median-Bruttomonatsverdienst SV-pflichtig Vollzeitbeschäftigter (Kerngruppe der BA-Entgeltstatistik). Stichtag 31.12. |
| **Quintil / Quantil-Gruppe** | Klassifizierung in 5 gleich große Gruppen nach Median-Entgelt: Ärmste 20 % / Unteres Mittel / Mittleres Mittel / Oberes Mittel / Reichste 20 % — je etwa 80 Kreise. |
| **AGS** | Amtlicher Gemeindeschlüssel (5-stellig auf Kreisebene). Eindeutige Kennung jedes Kreises/jeder kreisfreien Stadt. |
| **Tariflohnindex** | Index der tariflichen Monatsverdienste (Destatis, Basis 2020 = 100). Misst Tariflohnentwicklung in der Gesamtwirtschaft. |
| **Mindestlohn** | Gesetzlicher Mindestlohn seit 01.01.2015 (zuletzt 12,82 €/Std., 2025). Beschlossen durch Mindestlohnkommission, festgesetzt per Verordnung. |
| **Saisonbereinigt** | Statistisch bereinigt um regelmäßige Schwankungen (Sommer/Winter, Ferienzeiten). Erlaubt sauberere Trendaussagen. |
| **BA** | Bundesagentur für Arbeit (Nürnberg) — Hauptquelle für Arbeitslosen-, Beschäftigten- und Entgeltdaten. |
| **VGR** | Volkswirtschaftliche Gesamtrechnung — methodischer Rahmen des Statistischen Bundesamts für Erwerbstätige, BIP etc. |
| **GENESIS** | Destatis-Online-Datenbank (`www-genesis.destatis.de`). Hier holen wir die Erwerbstätigen-Daten. |
        """)

    snap = _snapshot()
    ml   = _mindestlohn()

    # ─ Bundesweite Aggregate ─
    bund_al    = int(snap["arbeitslose_gesamt"].sum())
    bund_ub    = (
        int(snap["unterbeschaeftigung"].sum())
        if "unterbeschaeftigung" in snap.columns and snap["unterbeschaeftigung"].notna().any()
        else None
    )
    bund_be    = snap["beschaeftigte_gesamt"].sum()
    bund_et    = (
        snap["erwerbstaetige"].sum()
        if "erwerbstaetige" in snap.columns and snap["erwerbstaetige"].notna().any()
        else None
    )
    # ALQ deutschlandweit: gewichteter Mittelwert der BL-Quoten mit
    # Erwerbstätigen als Gewicht (kleine BL ziehen sonst nach oben).
    # Wir nehmen die offizielle BA-Quote, die in snap["arbeitslosenquote"] steht.
    if (
        "arbeitslosenquote" in snap.columns
        and "erwerbstaetige"   in snap.columns
        and snap["arbeitslosenquote"].notna().any()
        and snap["erwerbstaetige"].notna().any()
    ):
        valid = snap.dropna(subset=["arbeitslosenquote", "erwerbstaetige"])
        bund_quote = round(
            (valid["arbeitslosenquote"] * valid["erwerbstaetige"]).sum()
            / valid["erwerbstaetige"].sum(),
            1,
        )
    elif bund_et and bund_et > 0:
        bund_quote = round(bund_al / (bund_et + bund_al) * 100, 1)
    else:
        bund_quote = round(bund_al / (bund_be + bund_al) * 100, 1)
    ml_aktuell = float(ml.iloc[-1]["betrag"])

    # ─ Reihe 1: Bestände (groß → klein) ─
    k1, k2, k3 = st.columns(3)
    k1.metric(
        "Erwerbstätige (VGR)",
        f"{bund_et/1e6:.1f} Mio." if bund_et else "—",
        help="Alle Erwerbstätigen nach VGR-Konzept (Inlandskonzept), inkl. Selbständige, Beamte und geringfügig Beschäftigte. Quelle: Destatis GENESIS.",
    )
    k2.metric(
        "Sozialvers. Beschäftigte",
        f"{bund_be/1e6:.1f} Mio." if pd.notna(bund_be) else "—",
        help="Sozialversicherungspflichtig Beschäftigte (SVB) — Teilmenge der Erwerbstätigen ohne Selbständige, Beamte und ausschließlich geringfügig Beschäftigte. Quelle: BA-Statistik.",
    )
    k3.metric(
        "Arbeitslose gesamt",
        f"{bund_al:,}".replace(",", "."),
        help="Registrierte Arbeitslose laut BA-Statistik.",
    )

    # ─ Reihe 2: Quoten und Marken ─
    k4, k5, k6 = st.columns(3)
    k4.metric(
        "Arbeitslosenquote*",
        f"{bund_quote:.1f} %",
        help="Arithmetisches Mittel der offiziellen BA-Kreis-Arbeitslosenquoten (Jahresdurchschnitt). Stadtstaaten exakt, Flächenländer minimale Abweichung möglich.",
    )
    k5.metric(
        "Unterbeschäftigung",
        f"{bund_ub:,}".replace(",", ".") if bund_ub else "—",
        help="Arbeitslose + Personen in arbeitsmarktpolitischen Maßnahmen, kurzfristig arbeitsunfähig etc. Weiter gefasstes Maß als die reine Arbeitslosenzahl. Quelle: BA-Statistik (ohne Kurzarbeit).",
    )
    k6.metric(
        "Mindestlohn",
        f"€ {ml_aktuell:.2f} / Std.",
        help="Aktueller gesetzlicher Mindestlohn (BMAS).",
    )

    st.divider()

    col_karte, col_rank = st.columns([3, 2])

    with col_karte:
        ebene = st.radio(
            "Ebene",
            ["Bundesländer", "Kreise"],
            horizontal=True,
            help=(
                "Bundesländer: Choropleth-Karte mit Arbeitsmarktdaten (ALQ, "
                "Beschäftigte, Arbeitslose). "
                "Kreise: Choropleth-Karte mit Wahl zwischen Arbeitslosenquote "
                "und Median-Entgelt; Hover zeigt beide Werte gleichzeitig."
            ),
            key="ueberblick_ebene",
        )

        if ebene == "Bundesländer":
            metrik_k = st.selectbox(
                "Karte zeigt",
                ["arbeitslosenquote", "arbeitslose_gesamt", "beschaeftigte_gesamt"],
                format_func=lambda x: {
                    "arbeitslosenquote":    "Arbeitslosenquote (%)",
                    "arbeitslose_gesamt":   "Arbeitslose (absolut)",
                    "beschaeftigte_gesamt": "Sozialvers. Beschäftigte",
                }[x],
                key="ueberblick_metrik_bl",
                help=(
                    "Relativ: AL-Quote eignet sich für Vergleiche zwischen großen "
                    "und kleinen Bundesländern. Absolut: zeigt das Mengen-Gewicht "
                    "(NRW vs. Saarland sind direkt vergleichbar)."
                ),
            )
            st.plotly_chart(chart_karte(snap, metrik_k), use_container_width=True)
        else:
            # Echte Kreis-Choropleth (mapbox-basiert) mit ALQ/Entgelt-Toggle
            jahre_k = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]
            cj1, cj2 = st.columns([1, 1])
            sel_jahr_k = cj1.selectbox(
                "Jahr", jahre_k, index=len(jahre_k) - 1,
                key="ueberblick_jahr_kreise",
                help="Stichtag 31.12. (Entgelt) bzw. Jahresdurchschnitt (ALQ).",
            )
            metrik_kreise = cj2.selectbox(
                "Karte zeigt",
                ["arbeitslosenquote", "median_entgelt"],
                format_func=lambda x: {
                    "arbeitslosenquote": "Arbeitslosenquote (%)",
                    "median_entgelt":    "Median-Entgelt €/Monat",
                }[x],
                key="ueberblick_metrik_kreise",
                help="ALQ aus BA-Bulk-Excel · Entgelt aus BA-Entgeltstatistik.",
            )

            # Beide Datensätze laden und mergen (Hover zeigt dann beide Werte)
            df_alq_k     = query_alq_kreise(jahr=sel_jahr_k)
            df_entgelt_k = query_entgelt_snapshot(sel_jahr_k, "insgesamt")
            if metrik_kreise == "arbeitslosenquote":
                df_kreis_snap = df_alq_k.merge(
                    df_entgelt_k[["ags", "bundesland", "median_entgelt"]],
                    on="ags", how="left",
                )
                # bundesland aus dem Entgelt-Snapshot übernehmen
                df_kreis_snap["bundesland"] = (
                    df_kreis_snap["bundesland"].fillna("").replace("", "—")
                )
            else:
                df_kreis_snap = df_entgelt_k.merge(
                    df_alq_k[["ags", "arbeitslosenquote"]],
                    on="ags", how="left",
                )

            if df_kreis_snap.empty:
                st.info("Keine Kreisdaten für dieses Jahr verfügbar.")
            else:
                st.plotly_chart(
                    chart_karte_kreise(
                        df_kreis_snap, metrik_kreise,
                        titel=(
                            f"Arbeitslosenquote {sel_jahr_k}" if metrik_kreise == "arbeitslosenquote"
                            else f"Median-Entgelt {sel_jahr_k}"
                        ),
                    ),
                    use_container_width=True,
                )
                st.caption(
                    f"{len(df_kreis_snap):,} Kreise · {sel_jahr_k} · "
                    "Quelle: BA-Statistik (ALQ) und BA-Entgeltstatistik. "
                    "Hover zeigt beide Werte gleichzeitig."
                )

    with col_rank:
        st.subheader("Ranking nach Arbeitslosenquote")
        st.dataframe(
            format_ranking(snap),
            use_container_width=True, hide_index=True, height=420,
            column_config={
                "AL-Quote (%)*": st.column_config.ProgressColumn(
                    "AL-Quote (%)*", min_value=0, max_value=15, format="%.1f"
                )
            },
        )
        st.caption(
            "* Offizielle BA-Arbeitslosenquote, aggregiert aus den Kreis-Werten "
            "(arithmetisches Mittel der Kreise je Bundesland). Stadtstaaten exakt; "
            "Flächenländer mit ≤ 1 pp Abweichung möglich, da die Aggregation alle "
            "Kreise gleich gewichtet."
        )
        dl_buttons(snap, "regional_snapshot", "Snapshot exportieren")

    st.markdown(
        '<p class="source-note">Bundesagentur für Arbeit (statistik.arbeitsagentur.de) · '
        'Destatis GENESIS · Datenlizenz Deutschland 2.0</p>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ZEITREIHEN
# ═══════════════════════════════════════════════════════════════════════════════
elif seite == "Zeitreihen":
    hero(
        eyebrow="Analyse",
        title="Wie hat sich der Arbeitsmarkt entwickelt?",
        body="Monatliche Zeitreihen nach Bundesland — mit optionalen "
             "Mindestlohn-Markierungen für jeden Anpassungszeitpunkt.",
    )

    col_m, col_ml = st.columns([2, 1])
    with col_m:
        metrik = st.selectbox(
            "Indikator",
            ["arbeitslose_gesamt", "unterbeschaeftigung"],
            format_func=lambda x: {
                "arbeitslose_gesamt":  "Arbeitslose (absolut)",
                "unterbeschaeftigung": "Unterbeschäftigung (ohne Kurzarbeit)",
            }[x],
            help=(
                "Arbeitslose = im engeren Sinn gemeldete Arbeitslose (SGB III/II). "
                "Unterbeschäftigung = Arbeitslose + Personen in arbeitsmarktpolitischen "
                "Maßnahmen + kurzfristig Arbeitsunfähige. Zeigt das tatsächliche "
                "Stellen-Defizit besser als die reine Arbeitslosenzahl."
            ),
        )
    with col_ml:
        zeige_ml = st.toggle(
            "Mindestlohn-Markierungen", value=True,
            help="Zeigt jede Mindestlohn-Anpassung als vertikale Linie im Chart — "
                 "hilft Effekte auf den Arbeitsmarkt direkt im Zeitverlauf zu erkennen.",
        )

    ml_df = _mindestlohn() if zeige_ml else None

    df_ts = query_arbeitslose(sel_bl, start_s, end_s, metrik)
    if df_ts.empty:
        st.warning("Keine Daten für diese Auswahl.")
    else:
        st.plotly_chart(chart_zeitreihe(df_ts, metrik, ml_df), use_container_width=True)
        dl_buttons(df_ts, f"arbeitslose_{metrik}_{start_j}_{end_j}", "Zeitreihendaten")

    st.divider()

    col_b, col_y = st.columns(2)
    with col_b:
        st.subheader("Bundesweit gesamt")
        df_bund = query_arbeitslose_bundesweit(start_s, end_s)
        df_bund_plot = df_bund.copy()
        df_bund_plot["bundesland"] = "Deutschland gesamt"
        df_bund_plot["wert"]       = df_bund_plot[metrik]
        st.plotly_chart(
            chart_zeitreihe(df_bund_plot, metrik, ml_df),
            use_container_width=True,
        )

    with col_y:
        st.subheader("Vorjahresveränderung (bundesweit)")
        df_yoy = query_yoy_change(metrik)
        mask   = (df_yoy["datum"] >= f"{start_s}-01") & (df_yoy["datum"] <= f"{end_s}-01")
        st.plotly_chart(chart_yoy(df_yoy[mask]), use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# BESCHÄFTIGUNG
# ═══════════════════════════════════════════════════════════════════════════════
elif seite == "Beschäftigung":
    hero(
        eyebrow="Beschäftigung",
        title="Wer arbeitet wo?",
        body="Sozialversicherungspflichtig Beschäftigte und Erwerbstätige nach Bundesland "
             "— auf Basis offizieller Daten der BA-Statistik und des VGR-Konzepts.",
    )

    df_be = query_beschaeftigung(sel_bl, start_s, end_s)

    if df_be.empty:
        st.warning("Keine Beschäftigungsdaten verfügbar.")
    else:
        import plotly.express as px

        svb_col = "beschaeftigte_svb" if "beschaeftigte_svb" in df_be.columns else "beschaeftigte_gesamt"

        ansicht = st.radio(
            "Darstellung",
            ["Linienvergleich (alle gewählten Länder)", "Gestapelt (aggregiert)"] + sel_bl[:4],
            horizontal=True,
            help=(
                "Linienvergleich: alle gewählten Bundesländer als eigene Linie. "
                "Gestapelt: SVB + geringfügig Beschäftigte als zwei Schichten, "
                "über alle gewählten Länder summiert. "
                "Einzelnes Bundesland: nur dieses Land, Schichten getrennt."
            ),
        )

        if "Linienvergleich" in ansicht:
            fig_be = px.line(
                df_be, x="datum", y=svb_col, color="bundesland",
                labels={"datum": "", svb_col: "SVB-Beschäftigte", "bundesland": "Bundesland"},
                color_discrete_sequence=px.colors.qualitative.Plotly,
                title="Sozialversicherungspflichtig Beschäftigte nach Bundesland",
            )
            fig_be.update_layout(
                plot_bgcolor="white", hovermode="x unified",
                margin=dict(l=55, r=25, t=50, b=50),
                yaxis=dict(tickformat=",d", gridcolor="#F0F0F0"),
                xaxis=dict(gridcolor="#F0F0F0"),
                font=dict(family="-apple-system, BlinkMacSystemFont, 'Helvetica Neue', system-ui"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_be, use_container_width=True)
        elif "Gestapelt" in ansicht:
            st.plotly_chart(chart_beschaeftigung_stack(df_be, ""), use_container_width=True)
        else:
            st.plotly_chart(chart_beschaeftigung_stack(df_be, ansicht), use_container_width=True)

        st.caption(
            "SVB = Sozialversicherungspflichtig Beschäftigte (ohne Beamte, Selbständige). "
            "Quelle: BA-Statistik-API (EckwerteZeitreiheBSTBL)."
        )
        dl_buttons(df_be, f"beschaeftigung_{start_j}_{end_j}", "Beschäftigungsdaten")

    st.divider()
    st.subheader("Erwerbstätige nach VGR-Konzept")
    st.caption("Jahreswerte inkl. Selbständige. Quelle: GENESIS-Destatis (Tabelle 13311-0002)")
    df_et = query_erwerbstaetige(sel_bl, start_j, end_j)
    if not df_et.empty:
        import plotly.express as px
        fig_et = px.line(
            df_et, x="jahr", y="erwerbstaetige", color="bundesland",
            markers=True,
            labels={"jahr": "Jahr", "erwerbstaetige": "Erwerbstätige",
                    "bundesland": "Bundesland"},
            color_discrete_sequence=px.colors.qualitative.Plotly,
            title="Erwerbstätige nach Bundesland (VGR-Konzept)",
        )
        fig_et.update_layout(
            plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=55, r=25, t=50, b=50), hovermode="x unified",
            font=dict(family="-apple-system, BlinkMacSystemFont, 'Helvetica Neue', system-ui"),
            yaxis=dict(tickformat=",d", gridcolor="#F0F0F0"),
            xaxis=dict(gridcolor="#F0F0F0", dtick=1),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_et, use_container_width=True)
        dl_buttons(df_et, f"erwerbstaetige_{start_j}_{end_j}", "Erwerbstätige (GENESIS)")


# ═══════════════════════════════════════════════════════════════════════════════
# MINDESTLOHN
# ═══════════════════════════════════════════════════════════════════════════════
elif seite == "Mindestlohn":
    hero(
        eyebrow="Mindestlohn-Monitoring",
        title="Zehn Jahre gesetzlicher Mindestlohn.",
        body="Von 8,50 € (2015) auf 12,82 € (2025) — jede Anpassung im Kontext "
             "der Arbeitsmarktentwicklung nach Bundesland.",
    )

    ml_df = _mindestlohn()

    col_t, col_c = st.columns([1, 2])
    with col_t:
        st.subheader("Anpassungshistorie")
        st.dataframe(
            ml_df.assign(datum=ml_df["datum"].dt.strftime("%d.%m.%Y"))
                 .rename(columns={"datum": "Ab", "betrag": "€/Std.", "anpassung": "Anlass"})
                 [["Ab", "€/Std.", "Anlass"]],
            hide_index=True, use_container_width=True,
        )
        dl_buttons(ml_df, "mindestlohn_historie")
    with col_c:
        st.plotly_chart(chart_mindestlohn(ml_df), use_container_width=True)

    st.divider()

    st.subheader("Arbeitslosigkeit mit Mindestlohn-Markierungen")
    metrik_ml = st.selectbox(
        "Indikator",
        ["arbeitslose_gesamt", "unterbeschaeftigung"],
        format_func=lambda x: {
            "arbeitslose_gesamt":  "Arbeitslose (absolut)",
            "unterbeschaeftigung": "Unterbeschäftigung (ohne Kurzarbeit)",
        }[x],
        key="ml_sel",
        help=(
            "Unterbeschäftigung erfasst über die reinen Arbeitslosen hinaus auch "
            "Personen in arbeitsmarktpolitischen Maßnahmen, Trainings und kurzzeitig "
            "arbeitsunfähige Arbeitslose — bessere Annäherung an die tatsächliche "
            "Arbeitsmarktlücke (ohne Kurzarbeit, da diese Beschäftigung ist)."
        ),
    )
    df_ts_ml = query_arbeitslose(sel_bl, "2015-01", "2024-12", metrik_ml)
    if not df_ts_ml.empty:
        st.plotly_chart(
            chart_zeitreihe(df_ts_ml, metrik_ml, ml_df,
                            titel="Arbeitslosigkeit und Mindestlohn-Anpassungen"),
            use_container_width=True,
        )

    st.divider()

    # ── Vergleich Mindestlohn vs. Tariflohnindex ─────────────────────────────
    st.subheader("Mindestlohn vs. allgemeiner Tariflohn")
    st.caption(
        "Wie stark ist der gesetzliche Mindestlohn relativ zum durchschnittlichen "
        "Tariflohn gestiegen? Indizes beider Reihen auf ein gemeinsames Basisjahr "
        "normalisiert — eine wachsende Lücke zwischen den Linien zeigt, dass der "
        "Mindestlohn schneller steigt als das allgemeine Tarifgefüge."
    )

    col_b, col_m = st.columns([1, 1])
    with col_b:
        basis_jahr = st.selectbox(
            "Basisjahr (= 100)",
            [2015, 2010, 2020],
            index=0,
            help="2015 = Mindestlohn-Einführung. 2010 = Pre-Mindestlohn-Kontext.",
        )

    df_milt = query_mindestlohn_vs_tariflohn(basis_jahr)

    if df_milt.empty:
        st.info("Vergleichsdaten nicht verfügbar.")
    else:
        # Kennzahlen letztes Jahr
        last = df_milt.iloc[-1]
        ml_growth = last["mindestlohn_idx"] - 100
        tl_growth = last["tariflohn_idx"]   - 100
        gap       = ml_growth - tl_growth

        k1, k2, k3 = st.columns(3)
        k1.metric(
            f"Mindestlohn seit {basis_jahr}",
            f"+{ml_growth:.1f} %",
            help=f"Wachstum gegenüber dem Basisjahr {basis_jahr}.",
        )
        k2.metric(
            f"Tariflohnindex seit {basis_jahr}",
            f"+{tl_growth:.1f} %",
            help="Durchschnittliche Tariflohnentwicklung in Gesamtdeutschland.",
        )
        k3.metric(
            "Mindestlohn-Vorsprung",
            f"+{gap:.1f} pp",
            help="Zusätzliches Wachstum des Mindestlohns ggü. Tariflöhnen in Prozentpunkten.",
        )

        st.plotly_chart(
            chart_mindestlohn_vs_tariflohn(df_milt, basis_jahr),
            use_container_width=True,
        )

        if gap > 5:
            st.caption(
                f"Der Mindestlohn ist seit {basis_jahr} um **{gap:.1f} Prozentpunkte** "
                "stärker gewachsen als der durchschnittliche Tariflohn — politisch "
                "gewollte Aufholbewegung im unteren Lohnsegment."
            )
        elif gap < -5:
            st.caption(
                "Tariflöhne wachsen schneller als der Mindestlohn — der Mindestlohn "
                "verliert relativ an Bedeutung als Untergrenze."
            )

    st.divider()

    st.markdown("""
    <div class="info-card">
        <span class="info-card-label">Referenz</span>
        <p>
            Die Bundesagentur für Arbeit hat bis 2023 einen eigenen
            <strong>Mindestlohn-Monitor</strong> veröffentlicht (eingestellt).
            Die dortigen Standardvisualisierungen dienen als Vergleichsreferenz
            für die Indikatorauswahl dieses Dashboards.<br>
            <a href="https://statistik.arbeitsagentur.de/SiteGlobals/Forms/Suche/Einzelheftsuche_Formular.html?nn=1523076&topic_f=mindestlohn-monitor"
               target="_blank">BA Mindestlohn-Monitor — Archiv</a>
        </p>
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# MILO-EVALUATION (Kreise nach Entgelt klassifiziert → ALQ-Vergleich)
# ═══════════════════════════════════════════════════════════════════════════════
elif seite == "MiLo-Evaluation":
    hero(
        eyebrow="MiLo-Evaluation",
        title="Wer hat vom Mindestlohn profitiert?",
        body="Kreise werden anhand ihres Lohnniveaus in einem Stichjahr in Gruppen "
             "eingeteilt — danach vergleichen wir, wie sich die Arbeitslosenquote "
             "jeder Gruppe über die Zeit entwickelt hat. Konvergieren ärmere Kreise "
             "zum Niveau der reichen, oder bleibt die Lücke?",
    )

    with st.expander("Methodik kurz erklärt", expanded=False):
        st.markdown("""
**Logik dieser Analyse:**

1. **Klassifizierung:** Alle ~400 deutschen Kreise werden anhand ihres Median-Bruttoentgelts
   in einem **Stichjahr** in Gruppen sortiert. Du wählst den Modus:
   - **Quintile** — 5 gleich große Gruppen je 20 %
   - **Top/Bottom 10/20/25 %** — Drittel-Klassifizierung mit klarem Fokus auf Ränder
   - **Absolut** — eigene €-Schwellen (z. B. *< 2.500 €* / *2.500–3.500 €* / *> 3.500 €*)

2. **Auswertung:** Für jede so definierte Gruppe wird die Arbeitslosenquote
   (offiziell von der BA) Jahr für Jahr aggregiert (Mittelwert über alle Kreise der Gruppe).

3. **Ergebnis:** Zeitreihen + Stichtagsvergleich + Tabelle. Die Frage, ob der Mindestlohn
   wirklich Niedriglohnregionen stärker geholfen hat, kann man hier direkt ablesen —
   sind die unteren Gruppen relativ stärker gefallen?

> Datenquellen: BA-Statistik (ALQ je Kreis 1998+) und BA-Entgeltstatistik (Median-Entgelt 2015+).
        """)

    # ── Klassifizierungs-Filter ──────────────────────────────────────────────
    col_m1, col_m2, col_m3 = st.columns([1.3, 1, 1])
    with col_m1:
        modus = st.radio(
            "Klassifizierungs-Modus",
            ["Quintile (5 × 20 %)", "Top/Bottom 10 %", "Top/Bottom 20 %",
             "Top/Bottom 25 %", "Absolute €-Grenzen"],
            help=(
                "Quintile: 5 gleich große Gruppen — Standard für ungleichheits-orientierte "
                "Analysen. Top/Bottom: fokussiert auf Ränder + Mitte. Absolut: für "
                "Sensitivitätsanalysen mit eigenen Schwellen."
            ),
            key="milo_modus",
        )
    with col_m2:
        # Stichjahr — Entgeltdaten gibt es ab 2015
        stichjahr = st.selectbox(
            "Stichjahr für Klassifizierung",
            list(range(2015, 2025)),
            index=0,
            help=(
                "Jahr, an dem die Gruppen festgelegt werden. Ein Kreis kann zwar "
                "über die Zeit das Quintil wechseln — für diese Analyse bleibt die "
                "Gruppen-Zuordnung jedoch im Stichjahr eingefroren ('Cohort-Logik')."
            ),
            key="milo_stichjahr",
        )
    with col_m3:
        merkmal_milo = st.selectbox(
            "Entgelt-Merkmal",
            ["insgesamt", "maenner", "frauen", "u25", "55plus",
             "ohne_abschluss", "mit_abschluss", "akademisch"],
            format_func=lambda x: {
                "insgesamt":      "Insgesamt",
                "maenner":        "Männer",
                "frauen":         "Frauen",
                "u25":            "Unter 25 Jahre",
                "55plus":         "55 Jahre und älter",
                "ohne_abschluss": "Ohne Berufsabschluss",
                "mit_abschluss":  "Mit Berufsabschluss",
                "akademisch":     "Akademisch",
            }.get(x, x),
            help=(
                "Welche Lohngruppe bestimmt die Klassifizierung? 'Insgesamt' ist der "
                "Standard — alternativ z. B. nur 'Ohne Berufsabschluss' falls man "
                "MiLo-Betroffenheit gezielter abbilden will."
            ),
            key="milo_merkmal",
        )

    # Modus-Konfiguration
    abs_unter, abs_ober = None, None
    if modus == "Quintile (5 × 20 %)":
        modus_code = "quintil"
    elif modus == "Top/Bottom 10 %":
        modus_code = "top_bottom_10"
    elif modus == "Top/Bottom 20 %":
        modus_code = "top_bottom_20"
    elif modus == "Top/Bottom 25 %":
        modus_code = "top_bottom_25"
    else:  # Absolut
        modus_code = "absolut"
        col_au, col_ao = st.columns(2)
        with col_au:
            abs_unter = st.number_input(
                "Untergrenze (€ Median-Monatsentgelt)",
                min_value=1500, max_value=5000, value=2500, step=100,
                help="Kreise unterhalb dieser Schwelle gelten als 'Niedriglohnregion'.",
            )
        with col_ao:
            abs_ober = st.number_input(
                "Obergrenze (€ Median-Monatsentgelt)",
                min_value=2000, max_value=6000, value=3500, step=100,
                help="Kreise oberhalb dieser Schwelle gelten als 'Hochlohnregion'.",
            )
        if abs_unter >= abs_ober:
            st.error("Untergrenze muss kleiner als Obergrenze sein.")
            st.stop()

    # ── Berechnung ───────────────────────────────────────────────────────────
    @st.cache_data(ttl=3600, show_spinner="MiLo-Evaluation berechnen …")
    def _milo_run(modus_code, stichjahr, abs_unter, abs_ober, merkmal_milo):
        return query_milo_evaluation(modus_code, stichjahr, abs_unter, abs_ober, merkmal_milo)

    agg_milo, klass_milo = _milo_run(modus_code, stichjahr, abs_unter, abs_ober, merkmal_milo)

    if agg_milo.empty:
        st.warning("Keine Daten für diese Konfiguration. Andere Klassifizierung wählen.")
        st.stop()

    st.divider()

    # ── Klassifizierungs-Zusammenfassung ─────────────────────────────────────
    st.subheader("Klassifizierungs-Zusammenfassung")
    gruppen_counts = klass_milo.groupby("gruppe", observed=True).agg(
        n_kreise=("ags", "count"),
        median_entgelt_ø=("median_entgelt", "mean"),
    ).round(0).reset_index()

    cols_gruppen = st.columns(len(gruppen_counts))
    for i, row in gruppen_counts.iterrows():
        cols_gruppen[i].metric(
            row["gruppe"],
            f"{int(row['n_kreise'])} Kreise",
            f"Ø {int(row['median_entgelt_ø']):,} €".replace(",", "."),
            delta_color="off",
        )

    st.divider()

    # ── Zeitreihe ────────────────────────────────────────────────────────────
    st.subheader("Zeitreihe — Arbeitslosenquote nach Gruppe")
    st.caption(
        "Ø ALQ aller Kreise einer Gruppe. Vertikale Linien markieren "
        "Mindestlohn-Anpassungen. Schließt sich die Lücke?"
    )
    ml_for_chart = _mindestlohn()
    st.plotly_chart(
        chart_milo_zeitreihe(agg_milo, "Arbeitslosenquote (%)", ml_for_chart),
        use_container_width=True,
    )

    st.divider()

    # ── Stichtagsvergleich ───────────────────────────────────────────────────
    st.subheader("Stichtagsvergleich (Säulen)")
    st.caption("Wähle Jahre für den direkten Vergleich — Default: vor MiLo, Einführung, nach Corona, aktuell.")
    jahre_verfuegbar = sorted(agg_milo["jahr"].unique())
    default_stichjahre = [j for j in [2014, 2015, 2020, 2025] if j in jahre_verfuegbar]
    if not default_stichjahre:
        default_stichjahre = jahre_verfuegbar[:4]

    sel_stichjahre = st.multiselect(
        "Stichjahre",
        jahre_verfuegbar,
        default=default_stichjahre,
        help="Üblich: 2014 (vor MiLo), 2015 (Einführung), 2020 (Pre-Corona), 2025 (aktuell).",
    )
    if sel_stichjahre:
        st.plotly_chart(
            chart_milo_balken_stichtage(agg_milo, sorted(sel_stichjahre), "Arbeitslosenquote (%)"),
            use_container_width=True,
        )

    st.divider()

    # ── Tabellarischer Überblick ─────────────────────────────────────────────
    st.subheader("Tabellarischer Überblick")
    st.caption("Ø ALQ pro Gruppe und Stichjahr + absolute Veränderung in Prozentpunkten.")
    if sel_stichjahre:
        tab = chart_milo_tabelle(agg_milo, sorted(sel_stichjahre))
        st.dataframe(tab, use_container_width=True, hide_index=True)

        # Story-Caption
        if len(sel_stichjahre) >= 2 and "Δ " in tab.columns[-1]:
            delta_col = tab.columns[-1]
            min_g = tab.loc[tab[delta_col].idxmin()]
            max_g = tab.loc[tab[delta_col].idxmax()]
            differenz = min_g[delta_col] - max_g[delta_col]
            if differenz < -1.0:  # min ist deutlich niedriger (= mehr gefallen)
                st.caption(
                    f"**Befund:** Gruppe **{min_g['gruppe']}** hat ihre ALQ um "
                    f"{abs(min_g[delta_col]):.1f} pp reduziert — Gruppe "
                    f"**{max_g['gruppe']}** dagegen nur um {abs(max_g[delta_col]):.1f} pp "
                    f"(bzw. +{max_g[delta_col]:.1f} pp gestiegen). "
                    f"Die regionale Konvergenz zwischen den Lohngruppen beträgt "
                    f"**{abs(differenz):.1f} Prozentpunkte** — Hinweis auf eine "
                    f"differenzierte Wirkung von Mindestlohn und Konjunktur auf "
                    f"Niedrig- vs. Hochlohnregionen."
                )

    st.divider()

    # ── Downloads ────────────────────────────────────────────────────────────
    dl_buttons(agg_milo, f"milo_eval_aggregat_{modus_code}_{stichjahr}", "Aggregat exportieren")
    dl_buttons(klass_milo[["ags", "kreis", "bundesland", "median_entgelt", "gruppe"]],
               f"milo_eval_klassifizierung_{modus_code}_{stichjahr}",
               "Klassifizierung exportieren")

    st.markdown(
        '<p class="source-note">ALQ: Bundesagentur für Arbeit — '
        '"Arbeitslosenquote bezogen auf alle zivilen Erwerbspersonen" (Jahresdurchschnitt). '
        'Entgelt-Klassifizierung: BA-Entgeltstatistik (Vollzeitbeschäftigte Kerngruppe). '
        'Beide Datenlizenz Deutschland 2.0.</p>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ENTGELT NACH KREISEN
# ═══════════════════════════════════════════════════════════════════════════════
elif seite == "Entgelt nach Kreisen":
    hero(
        eyebrow="Regionale Löhne",
        title="Was verdient Deutschland?",
        body="Median-Bruttoentgelte sozialversicherungspflichtig Vollzeitbeschäftigter "
             "in rund 400 Kreisen — nach Geschlecht, Alter und Qualifikation, 2015–2024.",
    )

    entgelt_path = ROOT / "data" / "processed" / "entgelt_kreise.parquet"
    if not entgelt_path.exists():
        st.warning(
            "Kreisdaten nicht vorhanden. "
            "Bitte `python -m src.pipeline` ausführen und "
            "die Excel-Dateien (entgelt-*.xlsx / entgelt-*.xlsm) im Projektordner ablegen."
        )
        st.stop()

    import plotly.express as px

    @st.cache_data(ttl=3600)
    def _load_entgelt():
        return pd.read_parquet(entgelt_path)

    df_ek = _load_entgelt()

    # ── Filter ──────────────────────────────────────────────────────────────
    alle_bl_ek   = sorted(df_ek["bundesland"].dropna().unique())
    alle_gruppen = ["Alle", "Ärmste 20%", "Unteres Mittel",
                    "Mittleres Mittel", "Oberes Mittel", "Reichste 20%"]
    jahre_ek     = sorted(df_ek["jahr"].unique())

    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        sel_bl_ek = st.multiselect(
            "Bundesland", alle_bl_ek, default=[],
            help="Leer = alle Bundesländer",
        )
    with col_f2:
        sel_merkmal = st.selectbox(
            "Merkmal",
            list(MERKMALE_8_2.values()),
            format_func=lambda x: {
                "insgesamt":      "Insgesamt",
                "maenner":        "Männer",
                "frauen":         "Frauen",
                "u25":            "Unter 25 Jahre",
                "25_55":          "25 bis unter 55 Jahre",
                "55plus":         "55 Jahre und älter",
                "deutsche":       "Deutsche",
                "auslaender":     "Ausländer",
                "ohne_abschluss": "Ohne Berufsabschluss",
                "mit_abschluss":  "Anerkannter Berufsabschluss",
                "akademisch":     "Akademischer Berufsabschluss",
                "helfer":         "Helfer",
                "fachkraft":      "Fachkraft",
                "spezialist":     "Spezialist",
                "experte":        "Experte",
            }.get(x, x),
            help=(
                "Untergruppen aus der BA-Entgeltstatistik (Sheet 8.2/16.2): "
                "demografisch (Geschlecht, Alter, Herkunft), Qualifikation (mit/ohne "
                "Berufsabschluss, akademisch) oder Anforderungsniveau (Helfer bis "
                "Experte). Der Median bezieht sich nur auf SV-pflichtig Vollzeit-"
                "Beschäftigte der jeweiligen Gruppe (Stichtag 31.12.)."
            ),
        )
    with col_f3:
        sel_gruppe = st.selectbox(
            "Quantil-Gruppe", alle_gruppen,
            help=(
                "Klassifizierung der Kreise nach Median-Entgelt (Merkmal Insgesamt). "
                "Ärmste/Reichste 20 % = je 80 Kreise mit dem niedrigsten bzw. höchsten "
                "Lohnniveau. Wird pro Jahr neu berechnet (Kreise können wandern)."
            ),
        )
    with col_f4:
        referenzjahr = st.selectbox(
            "Referenzjahr", jahre_ek, index=len(jahre_ek) - 1,
            help=(
                "Basis für Ranking, Quintil-Zuordnung und die Karte rechts. "
                "Zeitreihen unterhalb zeigen weiterhin den ganzen Zeitraum."
            ),
        )

    df_filtered = df_ek[df_ek["merkmal"] == sel_merkmal].copy()
    if sel_bl_ek:
        df_filtered = df_filtered[df_filtered["bundesland"].isin(sel_bl_ek)]
    if sel_gruppe != "Alle":
        kreise_in_gruppe = df_ek[
            (df_ek["jahr"] == referenzjahr) &
            (df_ek["merkmal"] == "insgesamt") &
            (df_ek["quantil_gruppe"] == sel_gruppe)
        ]["kreis"].unique()
        df_filtered = df_filtered[df_filtered["kreis"].isin(kreise_in_gruppe)]

    st.divider()

    # ── 1. Ranking + Top/Bottom Chart ────────────────────────────────────────
    st.subheader(f"Ranking {referenzjahr}")

    df_rank = (
        df_filtered[df_filtered["jahr"] == referenzjahr]
        .copy()
        .sort_values("median_entgelt", ascending=False)
        .reset_index(drop=True)
    )
    df_rank.index += 1

    col_rank, col_chart = st.columns([1, 2])
    with col_rank:
        st.dataframe(
            df_rank[["kreis", "bundesland", "median_entgelt", "quantil_gruppe"]]
            .rename(columns={
                "kreis": "Kreis", "bundesland": "Bundesland",
                "median_entgelt": "Median €", "quantil_gruppe": "Gruppe",
            }),
            use_container_width=True, height=420, hide_index=False,
        )

    with col_chart:
        df_bar = pd.concat([df_rank.head(10), df_rank.tail(10)]).drop_duplicates()
        fig_bar = px.bar(
            df_bar,
            x="median_entgelt", y="kreis", orientation="h",
            color="quantil_gruppe",
            color_discrete_map={
                "Ärmste 20%":       "#1B4F72",
                "Unteres Mittel":   "#2980B9",
                "Mittleres Mittel": "#85C1E9",
                "Oberes Mittel":    "#D4690A",
                "Reichste 20%":     "#F07000",
            },
            labels={"median_entgelt": "Median €/Monat", "kreis": "",
                    "quantil_gruppe": "Gruppe"},
            title=f"Top 10 & Bottom 10 Kreise — Medianentgelt {referenzjahr}",
        )
        fig_bar.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=10, r=20, t=50, b=30),
            height=max(400, len(df_bar) * 28),
            font=dict(family="-apple-system, BlinkMacSystemFont, 'Helvetica Neue', system-ui"),
            yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
            xaxis=dict(tickformat=",d"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        xanchor="right", x=1, font=dict(size=11)),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    st.divider()

    # ── 2. Quintil-Trendanalyse ───────────────────────────────────────────────
    st.subheader("Lohnentwicklung nach Entgelt-Quintil")
    st.caption(
        "Durchschnittliches Medianentgelt aller Kreise je Quintil-Gruppe über die Zeit. "
        "Quintile auswählen, um nur einzelne Gruppen direkt zu vergleichen."
    )

    quintil_alle = ["Ärmste 20%", "Unteres Mittel", "Mittleres Mittel",
                    "Oberes Mittel", "Reichste 20%"]
    sel_quintile_qv = st.multiselect(
        "Quintile anzeigen",
        quintil_alle,
        default=quintil_alle,
        key="qv_quintile",
        help="Standard: alle 5 — reduziere die Auswahl für gezielten Vergleich.",
    )

    df_qv = query_quintil_verlauf(sel_merkmal)
    if not df_qv.empty:
        if sel_bl_ek:
            kreise_bl = df_ek[
                (df_ek["bundesland"].isin(sel_bl_ek)) & (df_ek["merkmal"] == "insgesamt")
            ]["ags"].unique()
            df_qv_basis = df_ek[
                (df_ek["ags"].isin(kreise_bl)) &
                (df_ek["merkmal"] == sel_merkmal) &
                df_ek["quantil_gruppe"].notna()
            ]
            if not df_qv_basis.empty:
                df_qv = (
                    df_qv_basis
                    .groupby(["jahr", "quantil_gruppe"])["median_entgelt"]
                    .mean().round(0).reset_index()
                    .rename(columns={"median_entgelt": "avg_entgelt"})
                )
        # Quintil-Filter anwenden
        if sel_quintile_qv:
            df_qv_plot = df_qv[df_qv["quantil_gruppe"].isin(sel_quintile_qv)]
            if df_qv_plot.empty:
                st.info("Keine Daten für die ausgewählten Quintile.")
            else:
                st.plotly_chart(chart_quintil_verlauf(df_qv_plot), use_container_width=True)
        else:
            st.info("Bitte mindestens ein Quintil auswählen.")
    else:
        st.info("Quintil-Daten nicht verfügbar — bitte Pipeline neu ausführen.")

    st.divider()

    # ── 2b. Gruppen-Vergleich (zwei frei wählbare Quintile) ──────────────────
    st.subheader("Vergleich zweier Gruppen")
    st.caption(
        "Direkter Lohnvergleich zwischen zwei frei wählbaren Quintil-Gruppen. "
        "\"Alle anderen\" als Gruppe B bedeutet: alle Quintile außer Gruppe A. "
        "Der Slider zeigt die Lücke zu einem konkreten Jahr."
    )

    quintil_optionen = ["Ärmste 20%", "Unteres Mittel", "Mittleres Mittel",
                        "Oberes Mittel", "Reichste 20%"]

    col_a, col_b, col_jahr = st.columns([1, 1, 1])
    with col_a:
        gruppe_a = st.selectbox(
            "Gruppe A (orange)",
            quintil_optionen,
            index=0,
            key="gv_gruppe_a",
        )
    with col_b:
        # Gruppe B: alle Quintile außer Gruppe A + "Alle anderen"
        optionen_b = [q for q in quintil_optionen if q != gruppe_a] + ["Alle anderen"]
        # Default: erstes nicht-A oder Reichste falls A ≠ Reichste
        default_b = "Reichste 20%" if gruppe_a != "Reichste 20%" else "Ärmste 20%"
        gruppe_b = st.selectbox(
            "Gruppe B (blau)",
            optionen_b,
            index=optionen_b.index(default_b) if default_b in optionen_b else 0,
            key="gv_gruppe_b",
        )
    with col_jahr:
        jahre_avr = sorted(df_ek["jahr"].unique())
        highlight_jahr = st.select_slider(
            "Zeitpunkt-Markierung",
            options=jahre_avr,
            value=jahre_avr[-1],
            help="Markiert den Lohnabstand im Chart und in den Kennzahlen darunter.",
        )

    df_avr = query_gruppen_vergleich(sel_merkmal, gruppe_a, gruppe_b)

    if df_avr.empty:
        st.info("Keine Vergleichsdaten verfügbar.")
    else:
        row_h = df_avr[df_avr["jahr"] == highlight_jahr].iloc[0]
        row_0 = df_avr.iloc[0]
        gap_change = row_h["gap_pct"] - row_0["gap_pct"]

        # Vorzeichen-bewusste Trend-Beschreibung
        if abs(gap_change) < 0.05:
            trend_txt = f"Lücke unverändert seit {int(row_0['jahr'])}"
        elif (row_h["gap_pct"] >= 0 and gap_change < 0) or (row_h["gap_pct"] < 0 and gap_change > 0):
            trend_txt = f"Lücke um {abs(gap_change):.1f} pp geschrumpft seit {int(row_0['jahr'])} — Annäherung"
        else:
            trend_txt = f"Lücke um {abs(gap_change):.1f} pp gewachsen seit {int(row_0['jahr'])} — Auseinanderdriften"

        m1, m2, m3, m4 = st.columns(4)
        m1.metric(
            f"{gruppe_a} ({int(highlight_jahr)})",
            f"{row_h['entgelt_a']:,.0f} €".replace(",", "."),
        )
        m2.metric(
            f"{gruppe_b} ({int(highlight_jahr)})",
            f"{row_h['entgelt_b']:,.0f} €".replace(",", "."),
        )
        m3.metric(
            "Absoluter Abstand",
            f"{abs(row_h['gap_absolut']):,.0f} €".replace(",", "."),
            help="Differenz Gruppe B − Gruppe A (Betrag).",
        )
        # Vorzeichen erklärt Richtung: + heißt B>A, − heißt A>B
        sign_h = "+" if row_h["gap_pct"] >= 0 else "−"
        m4.metric(
            "Relativer Vorsprung",
            f"{sign_h}{abs(row_h['gap_pct']):.1f} %",
            delta=f"{gap_change:+.1f} pp ggü. {int(row_0['jahr'])}",
            delta_color="inverse",   # Lücke schließt sich = grün
            help="Positiv: Gruppe B liegt vor Gruppe A. Negativ: A liegt vor B.",
        )

        col_l, col_r = st.columns([3, 2])
        with col_l:
            st.plotly_chart(
                chart_gruppen_vergleich(df_avr, gruppe_a, gruppe_b, highlight_jahr),
                use_container_width=True,
            )
        with col_r:
            st.plotly_chart(
                chart_gap_verlauf(df_avr, gruppe_a, gruppe_b),
                use_container_width=True,
            )

        st.caption(trend_txt + ".")

    st.divider()

    # ── 3. Kartenvergleich zwei Zeitpunkte (echte Choropleth) ────────────────
    st.subheader("Kartenvergleich — zwei Zeitpunkte")
    st.caption(
        "Medianentgelt auf Kreisebene als Choropleth-Karte im direkten Vergleich. "
        "Dunklere Farbe = höheres Lohnniveau. Hover zeigt zusätzlich die ALQ."
    )

    vj_options = [y for y in jahre_ek if y < referenzjahr]
    if vj_options:
        vergleichsjahr = st.selectbox(
            "Vergleichsjahr (linke Karte)",
            vj_options,
            index=max(0, len(vj_options) - 1),
            key="vergleichsjahr_map",
            help=(
                "Linke Karte zeigt diesen Zeitpunkt, rechte Karte das Referenzjahr "
                "aus dem oberen Filter. Tabellen darunter listen Kreise mit dem "
                "stärksten bzw. schwächsten Lohnwachstum dazwischen."
            ),
        )

        col_k1, col_k2 = st.columns(2)
        with col_k1:
            df_k1 = query_entgelt_snapshot(vergleichsjahr, sel_merkmal)
            if sel_bl_ek:
                df_k1 = df_k1[df_k1["bundesland"].isin(sel_bl_ek)]
            # ALQ hinzufügen für Hover
            alq_k1 = query_alq_kreise(jahr=vergleichsjahr)
            if not alq_k1.empty:
                df_k1 = df_k1.merge(alq_k1[["ags", "arbeitslosenquote"]], on="ags", how="left")
            if not df_k1.empty:
                st.plotly_chart(
                    chart_karte_kreise(df_k1, "median_entgelt",
                                       f"Medianentgelt {vergleichsjahr}"),
                    use_container_width=True,
                )
        with col_k2:
            df_k2 = query_entgelt_snapshot(referenzjahr, sel_merkmal)
            if sel_bl_ek:
                df_k2 = df_k2[df_k2["bundesland"].isin(sel_bl_ek)]
            alq_k2 = query_alq_kreise(jahr=referenzjahr)
            if not alq_k2.empty:
                df_k2 = df_k2.merge(alq_k2[["ags", "arbeitslosenquote"]], on="ags", how="left")
            if not df_k2.empty:
                st.plotly_chart(
                    chart_karte_kreise(df_k2, "median_entgelt",
                                       f"Medianentgelt {referenzjahr}"),
                    use_container_width=True,
                )

        if not df_k1.empty and not df_k2.empty:
            merged = df_k1[["ags", "kreis", "median_entgelt"]].merge(
                df_k2[["ags", "median_entgelt"]].rename(
                    columns={"median_entgelt": "median_entgelt_neu"}),
                on="ags",
            )
            merged["wachstum_pct"] = (
                (merged["median_entgelt_neu"] - merged["median_entgelt"])
                / merged["median_entgelt"] * 100
            ).round(1)

            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.caption(f"**Stärkstes Lohnwachstum** ({vergleichsjahr} → {referenzjahr})")
                st.dataframe(
                    merged.nlargest(5, "wachstum_pct")[["kreis", "wachstum_pct"]]
                    .rename(columns={"kreis": "Kreis", "wachstum_pct": "Wachstum %"}),
                    hide_index=True, use_container_width=True,
                )
            with col_d2:
                st.caption(f"**Schwächstes Lohnwachstum** ({vergleichsjahr} → {referenzjahr})")
                st.dataframe(
                    merged.nsmallest(5, "wachstum_pct")[["kreis", "wachstum_pct"]]
                    .rename(columns={"kreis": "Kreis", "wachstum_pct": "Wachstum %"}),
                    hide_index=True, use_container_width=True,
                )
    else:
        st.info("Für den Kartenvergleich wird mindestens ein zweites Datenjahr benötigt.")

    st.divider()

    # ── 4. Zeitreihe: Kreis-Dropdown mit Quintil-Filter ──────────────────────
    st.subheader("Zeitreihe — Kreisvergleich")
    st.caption(
        "Wähle einzelne Kreise oder filtere zunächst nach Quintil-Gruppe. "
        "Die Quintil-Zuordnung basiert auf dem Referenzjahr im oberen Filter."
    )

    col_qf, col_kf = st.columns([1, 2])
    with col_qf:
        quintil_optionen_ts = ["Ärmste 20%", "Unteres Mittel", "Mittleres Mittel",
                               "Oberes Mittel", "Reichste 20%"]
        sel_quintile_ts = st.multiselect(
            "Quintil-Filter",
            quintil_optionen_ts,
            default=quintil_optionen_ts,
            help="Schränkt die wählbaren Kreise auf die gewählten Quintil-Gruppen ein.",
            key="ts_quintile",
        )

    # Kreis-Pool anhand Quintil-Auswahl im Referenzjahr eingrenzen
    if sel_quintile_ts and len(sel_quintile_ts) < 5:
        kreise_im_quintil = df_ek[
            (df_ek["merkmal"] == "insgesamt") &
            (df_ek["jahr"] == referenzjahr) &
            (df_ek["quantil_gruppe"].isin(sel_quintile_ts))
        ]["kreis"].unique()
        df_ts_pool = df_filtered[df_filtered["kreis"].isin(kreise_im_quintil)]
    else:
        df_ts_pool = df_filtered

    wunsch        = ["Würzburg", "Würzburg, Stadt", "Schweinfurt",
                     "Schweinfurt, Stadt", "Kitzingen"]
    verfuegb      = sorted(df_ts_pool["kreis"].unique())
    default_k     = [k for k in wunsch if k in verfuegb] or verfuegb[:5]

    with col_kf:
        sel_kreise = st.multiselect(
            f"Kreise auswählen (max. 10) — {len(verfuegb)} verfügbar",
            verfuegb,
            default=default_k, max_selections=10,
            key="ts_kreise",
        )

    if sel_kreise:
        df_ts_ek = df_ts_pool[df_ts_pool["kreis"].isin(sel_kreise)]
        fig_ts_ek = px.line(
            df_ts_ek, x="jahr", y="median_entgelt", color="kreis",
            markers=True,
            labels={"jahr": "Jahr", "median_entgelt": "Median €/Monat", "kreis": "Kreis"},
            title="Medianentgelt-Entwicklung nach Kreis",
            color_discrete_sequence=px.colors.qualitative.Plotly,
        )
        fig_ts_ek.update_layout(
            plot_bgcolor="white", margin=dict(l=55, r=25, t=50, b=50),
            font=dict(family="-apple-system, BlinkMacSystemFont, 'Helvetica Neue', system-ui"),
            yaxis=dict(gridcolor="#F0F0F0", tickformat=",.0f"),
            xaxis=dict(gridcolor="#F0F0F0", dtick=1),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_ts_ek, use_container_width=True)

    st.divider()

    # ── 5. Bundesland-Boxplot ─────────────────────────────────────────────────
    st.subheader(f"Regionale Verteilung {referenzjahr}")
    df_box = df_ek[df_ek["jahr"] == referenzjahr].sort_values("median_entgelt", ascending=False)

    fig_box = px.box(
        df_box, x="bundesland", y="median_entgelt", color="bundesland",
        labels={"bundesland": "Bundesland", "median_entgelt": "Median €/Monat"},
        title=f"Entgelt-Verteilung nach Bundesland — Kreisebene {referenzjahr}",
        color_discrete_sequence=px.colors.qualitative.Plotly,
    )
    fig_box.update_layout(
        plot_bgcolor="white", margin=dict(l=55, r=25, t=50, b=100),
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Helvetica Neue', system-ui"),
        xaxis=dict(tickangle=-45), showlegend=False,
        yaxis=dict(gridcolor="#F0F0F0", tickformat=",.0f"),
    )
    st.plotly_chart(fig_box, use_container_width=True)

    st.divider()
    dl_buttons(df_filtered, f"entgelt_kreise_{referenzjahr}", "Kreisdaten exportieren")

    st.markdown(
        '<p class="source-note">Bundesagentur für Arbeit — Entgeltstatistik '
        '(Vollzeitbeschäftigte Kerngruppe, Stichtag 31.12.) · '
        'Datenlizenz Deutschland 2.0</p>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# KREIS-STORY
# ═══════════════════════════════════════════════════════════════════════════════
elif seite == "Kreis-Story":
    hero(
        eyebrow="Kreis-Story",
        title="Wie haben sich die Kreise entwickelt?",
        body="Wähle einen Kreis für die volle Story-Ansicht oder mehrere Kreise "
             "für den direkten Vergleich — Quintil-Trajektorien, Lohnverlauf und "
             "Rang-Entwicklung übereinandergelegt.",
    )

    entgelt_path_ks = ROOT / "data" / "processed" / "entgelt_kreise.parquet"
    if not entgelt_path_ks.exists():
        st.warning("Kreisdaten nicht vorhanden — bitte `python -m src.pipeline` ausführen.")
        st.stop()

    @st.cache_data(ttl=3600)
    def _kreis_liste():
        return query_kreis_liste()

    @st.cache_data(ttl=3600)
    def _quintil_verlauf(merkmal):
        return query_quintil_verlauf(merkmal)

    liste_kreise = _kreis_liste()
    if liste_kreise.empty:
        st.error("Keine Kreis-Daten verfügbar.")
        st.stop()

    # ── Kreis-Auswahl ────────────────────────────────────────────────────────
    col_ks1, col_ks2 = st.columns([2, 1])
    with col_ks1:
        # Anzeige: "Kreis (Bundesland)" — sortiert nach Bundesland/Kreis
        liste_kreise = liste_kreise.copy()
        liste_kreise["label"] = liste_kreise["kreis"] + " (" + liste_kreise["bundesland"] + ")"
        # Default: Würzburg, Stadt + Schweinfurt zum Demo-Vergleich
        defaults = [
            l for l in liste_kreise["label"]
            if l.startswith(("Würzburg, Stadt", "Schweinfurt, Stadt"))
        ][:2] or [liste_kreise["label"].iloc[0]]
        sel_labels = st.multiselect(
            "Kreise auswählen (1–5)",
            liste_kreise["label"].tolist(),
            default=defaults,
            max_selections=5,
            help=(
                f"{len(liste_kreise)} Kreise verfügbar. Ein Kreis → klassische "
                "Story-Ansicht mit Trend-Header und Kennzahlen. Mehrere Kreise "
                "→ Vergleichsmodus mit überlagerten Trajektorien und Vergleichs-"
                "tabelle."
            ),
        )
        if not sel_labels:
            st.info("Bitte mindestens einen Kreis auswählen.")
            st.stop()
        sel_kreise_rows = [
            liste_kreise[liste_kreise["label"] == lbl].iloc[0]
            for lbl in sel_labels
        ]
    with col_ks2:
        sel_merkmal_ks = st.selectbox(
            "Merkmal",
            list(MERKMALE_8_2.values()),
            format_func=lambda x: {
                "insgesamt":      "Insgesamt",
                "maenner":        "Männer",
                "frauen":         "Frauen",
                "u25":            "Unter 25 Jahre",
                "25_55":          "25 bis unter 55 Jahre",
                "55plus":         "55 Jahre und älter",
                "deutsche":       "Deutsche",
                "auslaender":     "Ausländer",
                "ohne_abschluss": "Ohne Berufsabschluss",
                "mit_abschluss":  "Anerkannter Berufsabschluss",
                "akademisch":     "Akademischer Berufsabschluss",
                "helfer":         "Helfer",
                "fachkraft":      "Fachkraft",
                "spezialist":     "Spezialist",
                "experte":        "Experte",
            }.get(x, x),
            key="ks_merkmal",
            help=(
                "Welcher Lohn-Indikator wird angezeigt: gesamter Median, oder "
                "differenziert nach Geschlecht/Alter/Qualifikation. Die Quintil-"
                "Zuordnung bleibt immer auf Basis 'Insgesamt' — du siehst also den "
                "Lohn dieser Untergruppe und kannst gleichzeitig die Position des "
                "Kreises in der Gesamt-Verteilung erkennen."
            ),
        )

    # Daten für alle gewählten Kreise holen
    stories = {}  # label -> df_story
    for row in sel_kreise_rows:
        df = query_kreis_story(row["ags"], sel_merkmal_ks)
        if not df.empty:
            stories[row["label"]] = df
    if not stories:
        st.warning("Keine Daten für die ausgewählten Kreise.")
        st.stop()

    df_qv_ks = _quintil_verlauf(sel_merkmal_ks)
    is_multi = len(stories) > 1
    pos_map = {"Ärmste 20%": 0, "Unteres Mittel": 1, "Mittleres Mittel": 2,
               "Oberes Mittel": 3, "Reichste 20%": 4}

    # ── Status-Header: bei 1 Kreis = Trend-Card, bei >1 = Vergleichstabelle ──
    if not is_multi:
        sel_label   = next(iter(stories.keys()))
        df_story    = stories[sel_label]
        sel_kreis   = sel_kreise_rows[0]["kreis"]
        sel_ags     = sel_kreise_rows[0]["ags"]
        erstes      = df_story.iloc[0]
        letztes     = df_story.iloc[-1]
        q_start     = pos_map.get(erstes["quantil_gruppe"], -1)
        q_ende      = pos_map.get(letztes["quantil_gruppe"], -1)
        if q_start == -1 or q_ende == -1:
            trend_label, trend_color = "—", "#8E8E93"
        elif q_ende > q_start:
            trend_label, trend_color = f"↗ {q_ende - q_start} Stufe(n) aufgestiegen", "#1E8449"
        elif q_ende < q_start:
            trend_label, trend_color = f"↘ {q_start - q_ende} Stufe(n) abgerutscht", "#C0392B"
        else:
            trend_label, trend_color = "→ Stabil im selben Quintil", "#1B4F72"

        lohn_diff = letztes["median_entgelt"] - erstes["median_entgelt"]
        lohn_pct  = 100.0 * lohn_diff / erstes["median_entgelt"]
        rang_diff = int(erstes["rang"] - letztes["rang"])

        st.markdown(
            f'<div class="info-card" style="border-left-color:{trend_color}">'
            f'<span class="info-card-label" style="color:{trend_color}">{sel_kreis} · {letztes["bundesland"]}</span>'
            f'<p style="font-size:1.05rem;font-weight:600;color:#1D1D1F">{trend_label} ({int(erstes["jahr"])} → {int(letztes["jahr"])})</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

        m1, m2, m3, m4 = st.columns(4)
        m1.metric(
            f"Lohn {int(letztes['jahr'])}",
            f"{letztes['median_entgelt']:,.0f} €".replace(",", "."),
            delta=f"+{lohn_pct:.1f} % seit {int(erstes['jahr'])}",
        )
        m2.metric(
            "Aktuelles Quintil",
            letztes["quantil_gruppe"] if pd.notna(letztes["quantil_gruppe"]) else "—",
        )
        m3.metric(
            f"Platz {int(letztes['jahr'])}",
            f"{int(letztes['rang'])} / {int(letztes['n_kreise'])}",
            delta=f"{rang_diff:+d} Ränge seit {int(erstes['jahr'])}",
            delta_color="normal",
            help=(
                "Die Gesamtzahl der Kreise variiert leicht über die Jahre wegen "
                "Verwaltungsreformen: 2016 wurde Osterode am Harz in den Landkreis "
                "Göttingen eingegliedert (neuer AGS 03159), 2021 ging Eisenach im "
                "Wartburgkreis auf. Daher 402 → 401 → 400 Kreise."
            ),
        )
        m4.metric(
            "Lohnzuwachs absolut",
            f"+{lohn_diff:,.0f} €".replace(",", "."),
        )
    else:
        # Multi-Modus: Vergleichstabelle statt Trend-Card
        st.subheader(f"Vergleichstabelle — {len(stories)} Kreise")
        rows = []
        for lbl, df in stories.items():
            e, l = df.iloc[0], df.iloc[-1]
            q_s = pos_map.get(e["quantil_gruppe"], -1)
            q_e = pos_map.get(l["quantil_gruppe"], -1)
            stufen = q_e - q_s if (q_s >= 0 and q_e >= 0) else None
            if stufen is None:
                trend = "—"
            elif stufen > 0:
                trend = f"↗ +{stufen}"
            elif stufen < 0:
                trend = f"↘ {stufen}"
            else:
                trend = "→ stabil"
            rows.append({
                "Kreis": lbl,
                f"Lohn {int(e['jahr'])} €": int(e["median_entgelt"]),
                f"Lohn {int(l['jahr'])} €": int(l["median_entgelt"]),
                "Wachstum %": round(100 * (l["median_entgelt"] - e["median_entgelt"]) / e["median_entgelt"], 1),
                "Quintil heute": l["quantil_gruppe"] if pd.notna(l["quantil_gruppe"]) else "—",
                "Quintil-Trend": trend,
                f"Rang {int(l['jahr'])}": f"{int(l['rang'])} / {int(l['n_kreise'])}",
                "Δ Ränge": int(e["rang"] - l["rang"]),
            })
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True, hide_index=True,
        )
        st.caption(
            "Wachstum positiv = höheres Lohnniveau am Ende. "
            "Δ Ränge positiv = Kreis hat Plätze gewonnen (niedrigerer Rang = besserer Platz)."
        )

    st.divider()

    # ── Quintil-Bahn ─────────────────────────────────────────────────────────
    st.subheader("Quintil-Bahn")
    if is_multi:
        st.caption(
            "Jeder Kreis hat eine eigene Trajektorie. Sprünge zwischen den "
            "horizontalen Bahnen zeigen Aufstieg oder Abrutschen. Linien werden "
            "leicht vertikal versetzt, damit überlappende Verläufe sichtbar bleiben."
        )
        st.plotly_chart(chart_quintil_bahn_multi(stories), use_container_width=True)
    else:
        st.caption(
            "Jeder Punkt markiert das Quintil, in dem der Kreis im jeweiligen Jahr "
            "lag. Sprünge zwischen den Bahnen zeigen Aufstieg oder Abrutschen."
        )
        st.plotly_chart(chart_quintil_bahn(df_story, sel_kreis), use_container_width=True)

    st.divider()

    # ── Lohnverlauf im Kontext ───────────────────────────────────────────────
    st.subheader("Lohnverlauf im Quintil-Kontext")
    if is_multi:
        st.caption(
            "Jeder Kreis als eigene farbige Linie. Die fünf gepunkteten "
            "Hintergrundlinien zeigen den Durchschnittslohn jedes Quintils."
        )
        st.plotly_chart(
            chart_kreis_im_kontext_multi(stories, df_qv_ks),
            use_container_width=True,
        )
    else:
        st.caption(
            "Orange = dieser Kreis. Die fünf gepunkteten Hintergrundlinien zeigen "
            "den Durchschnittslohn jedes Quintils zum Vergleich."
        )
        st.plotly_chart(
            chart_kreis_im_kontext(df_story, df_qv_ks, sel_kreis),
            use_container_width=True,
        )

    st.divider()

    # ── Rang-Sparkline ───────────────────────────────────────────────────────
    st.subheader("Platzierung über die Jahre")
    if is_multi:
        st.caption(
            "Position der Kreise unter allen deutschen Kreisen. "
            "Platz 1 = höchster Lohn deutschlandweit. Niedrigere Linie = besserer Platz."
        )
        st.plotly_chart(chart_rang_sparkline_multi(stories), use_container_width=True)
    else:
        st.caption(
            f"Position des Kreises unter allen ~{int(letztes['n_kreise'])} Kreisen "
            "bei diesem Merkmal. Platz 1 = höchster Lohn deutschlandweit."
        )
        st.plotly_chart(chart_rang_sparkline(df_story, sel_kreis), use_container_width=True)

    st.divider()
    # Download: alle ausgewählten Kreise konkateniert
    if is_multi:
        df_export = pd.concat(
            [df.assign(kreis_label=lbl) for lbl, df in stories.items()],
            ignore_index=True,
        )
        dl_buttons(
            df_export,
            f"kreisstory_vergleich_{len(stories)}kreise_{sel_merkmal_ks}",
            f"Vergleich ({len(stories)} Kreise) exportieren",
        )
    else:
        dl_buttons(df_story, f"kreisstory_{sel_ags}_{sel_merkmal_ks}", "Kreis-Story exportieren")

    st.markdown(
        '<p class="source-note">Bundesagentur für Arbeit — Entgeltstatistik '
        '(Vollzeitbeschäftigte Kerngruppe, Stichtag 31.12.) · '
        'Quintile auf Basis Merkmal "Insgesamt" · '
        'Datenlizenz Deutschland 2.0</p>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════════════
elif seite == "Download":
    hero(
        eyebrow="Export",
        title="Daten herunterladen.",
        body="CSV und Excel — direkt importierbar in R, Python, Stata, SPSS oder Excel.",
    )

    st.subheader("Arbeitslosigkeit (monatlich, alle Bundesländer)")
    dl_buttons(query_arbeitslose(start=start_s, end=end_s),
               f"arbeitslose_{start_j}_{end_j}")

    st.divider()
    st.subheader("Beschäftigung (quartalsweise)")
    dl_buttons(query_beschaeftigung(start=start_s, end=end_s),
               f"beschaeftigung_{start_j}_{end_j}")

    st.divider()
    st.subheader("Erwerbstätige — Jahreswerte (VGR)")
    dl_buttons(query_erwerbstaetige(start_jahr=start_j, end_jahr=end_j),
               f"erwerbstaetige_{start_j}_{end_j}")

    st.divider()
    st.subheader("Mindestlohn-Anpassungshistorie")
    dl_buttons(_mindestlohn(), "mindestlohn_komplett")

    st.divider()
    st.subheader("Tariflohnindex — Jahreswerte (Destatis)")
    dl_buttons(query_tariflohnindex(), "tariflohnindex_destatis")

    st.divider()
    st.subheader("Regionaler Snapshot (aktuellster Stand je Bundesland)")
    dl_buttons(_snapshot(), "regional_snapshot")

    st.divider()
    st.markdown(
        "**Lizenz:** [Datenlizenz Deutschland 2.0](https://www.govdata.de/dl-de/by-2-0)\n\n"
        "**Empfohlene Quellenangabe:**\n"
        "> Bundesagentur für Arbeit / Statistisches Bundesamt (Destatis), "
        f"abgerufen via Arbeitsmarkt-Dashboard — THWS Business Analytics, {datetime.now().year}."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LITERATUR
# ═══════════════════════════════════════════════════════════════════════════════
elif seite == "Literatur":
    hero(
        eyebrow="Forschung & Quellen",
        title="Wissenschaft und Monitoring.",
        body="Ausgewählte Studien und Berichte zum deutschen Arbeitsmarkt und zum "
             "gesetzlichen Mindestlohn — von akademischen Grundlagenarbeiten bis hin "
             "zu öffentlich zugänglichen Policy-Reports.",
    )

    with st.expander("Mindestlohn — Wissenschaftliche Studien", expanded=True):
        st.markdown("""
<div class="lit-entry">
<strong>Dustmann, C., Lindner, A., Schönberg, U., Umkehrer, M. &amp; vom Berge, P. (2022)</strong><br>
Reallocation Effects of the Minimum Wage.<br>
<em>The Quarterly Journal of Economics, 137(1), 267–328.</em><br>
Untersucht Lohnstruktureffekte des deutschen Mindestlohns auf <strong>Kreisebene</strong>
mit regionalen Kartendarstellungen — besonders relevant für den regionalen Vergleich
dieses Dashboards.
</div>
<div class="lit-entry">
<strong>Bossler, M. &amp; Gerner, H.-D. (2020)</strong><br>
Employment Effects of the New German Minimum Wage.<br>
<em>Scandinavian Journal of Economics, 122(4), 1497–1524.</em><br>
Kausalanalyse der Beschäftigungseffekte mithilfe von Differenz-in-Differenzen-Schätzungen
auf Kreisebene.
</div>
<div class="lit-entry">
<strong>Caliendo, M., Fedorets, A., Preuss, M., Schröder, C. &amp; Wittbrodt, L. (2018)</strong><br>
The short-run employment effects of the German minimum wage reform.<br>
<em>Labour Economics, 53, 46–62.</em><br>
Kurzfristige Effekte auf Beschäftigung und Arbeitszeit; Basis für viele Folgestudien.
</div>
<div class="lit-entry">
<strong>Bonin, H. et al. (2018)</strong><br>
Auswirkungen des gesetzlichen Mindestlohns auf Beschäftigung, Arbeitszeit und Arbeitslosigkeit.<br>
<em>IZA Forschungsbericht Nr. 87. IZA, Bonn.</em><br>
Umfassende Evaluation der ersten Wirkungsjahre; enthält regionale Differenzierungen.
</div>
""", unsafe_allow_html=True)

    with st.expander("Mindestlohn — Policy-Berichte & Monitoring"):
        st.markdown("""
<div class="lit-entry">
<strong>Mindestlohnkommission (2024)</strong><br>
Dritter Bericht zu den Auswirkungen des gesetzlichen Mindestlohns.<br>
<em>Berlin.</em><br>
Offizieller Bericht der MiLoKo mit aktuellen Wirkungsanalysen und Empfehlungen.
<a href="https://www.mindestlohn-kommission.de" target="_blank">mindestlohn-kommission.de</a>
</div>
<div class="lit-entry">
<strong>Bundesagentur für Arbeit (2015–2023)</strong><br>
Mindestlohn-Monitor (Publikationsreihe, eingestellt 2023). Nürnberg.<br>
Quartalsweise Monitoring-Berichte zu Lohn- und Beschäftigungsentwicklung;
methodisch hilfreich als Vergleichsreferenz.
<a href="https://statistik.arbeitsagentur.de/SiteGlobals/Forms/Suche/Einzelheftsuche_Formular.html?nn=1523076&topic_f=mindestlohn-monitor"
   target="_blank">BA-Statistik Archiv</a>
</div>
<div class="lit-entry">
<strong>IAB (2023)</strong><br>
Auswirkungen des erhöhten Mindestlohns auf Beschäftigung und Löhne.<br>
<em>IAB-Kurzbericht 17/2023. Institut für Arbeitsmarkt- und Berufsforschung, Nürnberg.</em><br>
Kompakte Zusammenfassung der Effekte der Anhebung auf 12 € (Oktober 2022).
<a href="https://www.iab.de/de/publikationen.aspx" target="_blank">iab.de</a>
</div>
""", unsafe_allow_html=True)

    with st.expander("Lohnentwicklung & regionale Ungleichheit"):
        st.markdown("""
<div class="lit-entry">
<strong>Möller, J. (2016)</strong><br>
Lohnungleichheit in Deutschland: Entwicklungen, Ursachen und Reformoptionen.<br>
<em>Aus Politik und Zeitgeschichte, 66(14–15), 3–8.</em><br>
Verständliche Übersicht der Lohnungleichheit — gut als Hintergrundlektüre geeignet.
</div>
<div class="lit-entry">
<strong>vom Berge, P., Kaimer, S., Copestake, S., Eberle, J. &amp; Klosterhuber, W. (2016)</strong><br>
Arbeitsmarktspiegel: Entwicklungen nach Einführung des Mindestlohns (Ausgabe 1).<br>
<em>IAB-Forschungsbericht 01/2016. IAB, Nürnberg.</em><br>
Erste detaillierte regionale Analyse nach Mindestlohneinführung, mit Kreiskarten.
</div>
<div class="lit-entry">
<strong>Grabka, M. M. &amp; Goebel, J. (2017)</strong><br>
Realeinkommen sind von 1991 bis 2014 im Bundesdurchschnitt gestiegen.<br>
<em>DIW Wochenbericht, 84(4), 71–82.</em><br>
Langfristige Einkommensentwicklung mit Ost-West-Differenzierung.
</div>
<div class="lit-entry">
<strong>Bundesministerium für Arbeit und Soziales (2023)</strong><br>
Lebenslagen in Deutschland — Armuts- und Reichtumsbericht der Bundesregierung. Berlin.<br>
Offizieller Regierungsbericht mit umfassenden Daten zu Einkommensverteilung und Armut.
<a href="https://www.bmas.de" target="_blank">bmas.de</a>
</div>
""", unsafe_allow_html=True)

    with st.expander("Datenquellen & Methodik"):
        st.markdown("""
<div class="lit-entry">
<strong>Bundesagentur für Arbeit — Statistik-Portal</strong><br>
Arbeitslose, Beschäftigte, Entgelt nach Bundesland und Kreis (monatlich/jährlich).<br>
<a href="https://statistik.arbeitsagentur.de" target="_blank">statistik.arbeitsagentur.de</a>
— Datenlizenz Deutschland, Namensnennung, Version 2.0
</div>
<div class="lit-entry">
<strong>Destatis GENESIS-Datenbank</strong><br>
Erwerbstätige nach Bundesland (VGR-Konzept, Inlandskonzept), Tabelle 13311-0002.<br>
<a href="https://www-genesis.destatis.de" target="_blank">www-genesis.destatis.de</a>
— Datenlizenz Deutschland, Namensnennung, Version 2.0
</div>
<div class="lit-entry">
<strong>isellsoap / deutschlandGeoJSON (GitHub)</strong><br>
GeoJSON-Geometrien für Bundesländer und Kreise (Grundlage der Choropleth-Karten).<br>
<a href="https://github.com/isellsoap/deutschlandGeoJSON" target="_blank">github.com/isellsoap/deutschlandGeoJSON</a>
— MIT License
</div>
""", unsafe_allow_html=True)

    st.divider()
    st.markdown(
        f"**Empfohlene Zitation:** Bundesagentur für Arbeit / Statistisches Bundesamt (Destatis) "
        f"({datetime.now().year}): Arbeitsmarktdaten Deutschland, abgerufen via "
        f"Arbeitsmarkt-Dashboard, THWS Business School — Bachelor Business Analytics, SS 2026."
    )
