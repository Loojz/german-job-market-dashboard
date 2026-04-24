"""
Arbeitsmarkt-Dashboard Deutschland
────────────────────────────────────
Interaktive Visualisierung zentraler Arbeitsmarktkennzahlen.
Lokal starten: streamlit run app.py
"""

import io
from datetime import datetime

import pandas as pd
import streamlit as st

from src.pipeline import ensure_data_exists
from src.queries import (
    query_arbeitslose,
    query_arbeitslose_bundesweit,
    query_beschaeftigung,
    query_erwerbstaetige,
    query_mindestlohn,
    query_regional_snapshot,
    query_yoy_change,
)
from src.charts import (
    chart_zeitreihe,
    chart_yoy,
    chart_beschaeftigung_stack,
    chart_karte,
    chart_mindestlohn,
    format_ranking,
)

# ─── Seiten-Setup ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Arbeitsmarkt-Dashboard Deutschland",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="metric-container"] {
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 8px;
    padding: 14px 18px;
}
section[data-testid="stSidebar"] { background: #f0f2f6; }
.stDownloadButton > button {
    background-color: #1f77b4 !important;
    color: white !important;
    width: 100%;
}
.source-note { font-size: 0.75rem; color: #888; border-top: 1px solid #eee;
               padding-top: 0.6rem; margin-top: 1.2rem; }
</style>
""", unsafe_allow_html=True)

# ─── Daten sicherstellen ─────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner="Lade Daten …")
def _snapshot():    return query_regional_snapshot()

@st.cache_data(ttl=3600, show_spinner=False)
def _mindestlohn(): return query_mindestlohn()


# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 Arbeitsmarkt-Dashboard")
    st.caption("Bundesrepublik Deutschland")
    st.divider()

    seite = st.radio(
        "Navigation",
        ["🗺️ Überblick", "📈 Zeitreihen", "📊 Beschäftigung", "💶 Mindestlohn", "⬇️ Download"],
        label_visibility="collapsed",
    )
    st.divider()
    st.subheader("Filter")

    ALLE_BL = [
        "Schleswig-Holstein", "Hamburg", "Niedersachsen", "Bremen",
        "Nordrhein-Westfalen", "Hessen", "Rheinland-Pfalz", "Baden-Württemberg",
        "Bayern", "Saarland", "Berlin", "Brandenburg",
        "Mecklenburg-Vorpommern", "Sachsen", "Sachsen-Anhalt", "Thüringen",
    ]
    sel_bl = st.multiselect(
        "Bundesländer",
        ALLE_BL,
        default=["Bayern", "Nordrhein-Westfalen", "Berlin", "Sachsen"],
        help="Leer lassen = alle Bundesländer",
    )
    if not sel_bl:
        sel_bl = ALLE_BL

    c1, c2 = st.columns(2)
    start_j = c1.selectbox("Von", list(range(2015, 2025)), index=0)
    end_j   = c2.selectbox("Bis", list(range(2015, 2025)), index=9)
    if start_j > end_j:
        st.error("'Von' muss ≤ 'Bis' sein.")

    start_s = f"{start_j}-01"
    end_s   = f"{end_j}-12"

    st.divider()
    st.caption(
        f"Stand: {datetime.now().strftime('%d.%m.%Y')}\n\n"
        "Quellen: [BA-Statistik](https://statistik.arbeitsagentur.de) · "
        "[GENESIS](https://www-genesis.destatis.de)"
    )


# ─── Hilfs-Funktion Download-Buttons ─────────────────────────────────────────
def dl_buttons(df: pd.DataFrame, name: str, label: str = ""):
    if label:
        st.caption(f"**{label}** — {len(df):,} Zeilen")
    ca, cb = st.columns(2)
    with ca:
        st.download_button(
            "⬇️ CSV",
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
            "⬇️ Excel",
            buf.getvalue(),
            file_name=f"{name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SEITE: ÜBERBLICK
# ═══════════════════════════════════════════════════════════════════════════════
if "Überblick" in seite:
    st.header("Überblick: Aktueller Arbeitsmarkt")

    snap = _snapshot()
    ml   = _mindestlohn()

    # KPI-Zeile
    k1, k2, k3, k4 = st.columns(4)
    bund_al    = int(snap["arbeitslose_gesamt"].sum())
    quote_mean = snap["arbeitslosenquote"].dropna().mean()
    if pd.isna(quote_mean):
        quote_mean = snap["arbeitslose_gesamt"].sum() / (
                    snap["beschaeftigte_gesamt"].sum() + snap["arbeitslose_gesamt"].sum()) * 100
    bund_quote = round(float(quote_mean), 1)
    bund_be    = snap["beschaeftigte_gesamt"].sum()
    ml_aktuell = float(ml.iloc[-1]["betrag"])

    k1.metric("Arbeitslose gesamt",      f"{bund_al:,}".replace(",", "."))
    k2.metric("Ø Arbeitslosenquote",     f"{bund_quote:.1f} %")
    k3.metric("Beschäftigte (svpfl.)",
              f"{bund_be/1e6:.1f} Mio." if pd.notna(bund_be) else "–")
    k4.metric("Aktueller Mindestlohn",   f"€ {ml_aktuell:.2f} / Std.")

    st.divider()

    col_karte, col_rank = st.columns([3, 2])

    with col_karte:
        metrik_k = st.selectbox(
            "Karte zeigt",
            ["arbeitslosenquote", "arbeitslose_gesamt", "beschaeftigte_gesamt"],
            format_func=lambda x: {
                "arbeitslosenquote":  "Arbeitslosenquote (%)",
                "arbeitslose_gesamt": "Arbeitslose (absolut)",
                "beschaeftigte_gesamt": "Beschäftigte (svpfl.)",
            }[x],
        )
        st.plotly_chart(chart_karte(snap, metrik_k), use_container_width=True)

    with col_rank:
        st.subheader("Ranking nach AL-Quote")
        st.dataframe(
            format_ranking(snap),
            use_container_width=True, hide_index=True, height=420,
            column_config={
                "AL-Quote (%)": st.column_config.ProgressColumn(
                    "AL-Quote (%)", min_value=0, max_value=15, format="%.1f"
                )
            },
        )
        dl_buttons(snap, "regional_snapshot", "Snapshot exportieren")

    st.markdown(
        '<p class="source-note">Datenquellen: Bundesagentur für Arbeit '
        '(statistik.arbeitsagentur.de) · Destatis GENESIS · '
        'Datenlizenz Deutschland 2.0</p>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SEITE: ZEITREIHEN
# ═══════════════════════════════════════════════════════════════════════════════
elif "Zeitreihen" in seite:
    st.header("Zeitreihenanalyse")

    col_m, col_ml = st.columns([2, 1])
    with col_m:
        metrik = st.selectbox(
            "Indikator",
            ["arbeitslose_gesamt", "arbeitslosenquote", "arbeitslose_u25", "arbeitslose_ausl"],
            format_func=lambda x: {
                "arbeitslose_gesamt": "Arbeitslose (absolut)",
                "arbeitslosenquote":  "Arbeitslosenquote (%)",
                "arbeitslose_u25":    "Arbeitslose unter 25 Jahre",
                "arbeitslose_ausl":   "Ausländische Arbeitslose",
            }[x],
        )
    with col_ml:
        zeige_ml = st.toggle("Mindestlohn-Markierungen", value=True)

    ml_df = _mindestlohn() if zeige_ml else None

    # Bundesland-Vergleich
    df_ts = query_arbeitslose(sel_bl, start_s, end_s, metrik)
    if df_ts.empty:
        st.warning("Keine Daten für diese Auswahl.")
    else:
        st.plotly_chart(chart_zeitreihe(df_ts, metrik, ml_df), use_container_width=True)
        dl_buttons(df_ts, f"arbeitslose_{metrik}_{start_j}_{end_j}", "Zeitreihendaten")

    st.divider()

    # Bundesweit + YoY nebeneinander
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
# SEITE: BESCHÄFTIGUNG
# ═══════════════════════════════════════════════════════════════════════════════
elif "Beschäftigung" in seite:
    st.header("Sozialversicherungspflichtig Beschäftigte")

    df_be = query_beschaeftigung(sel_bl, start_s, end_s)

    if df_be.empty:
        st.warning("Keine Beschäftigungsdaten verfügbar.")
    else:
        ansicht = st.radio(
            "Darstellung",
            ["Alle gewählten Länder (aggregiert)"] + sel_bl,
            horizontal=True,
        )
        bl_sel = "" if "aggregiert" in ansicht else ansicht
        st.plotly_chart(chart_beschaeftigung_stack(df_be, bl_sel), use_container_width=True)
        dl_buttons(df_be, f"beschaeftigung_{start_j}_{end_j}", "Beschäftigungsdaten")

    st.divider()
    st.subheader("Erwerbstätige nach VGR-Konzept (inkl. Selbständige)")
    df_et = query_erwerbstaetige(sel_bl, start_j, end_j)
    if not df_et.empty:
        import plotly.express as px
        fig_et = px.line(
            df_et, x="jahr", y="erwerbstaetige", color="bundesland",
            labels={"jahr": "Jahr", "erwerbstaetige": "Erwerbstätige",
                    "bundesland": "Bundesland"},
            color_discrete_sequence=px.colors.qualitative.Plotly,
        )
        fig_et.update_layout(
            plot_bgcolor="white", hovermode="x unified",
            margin=dict(l=55, r=25, t=30, b=50),
            yaxis=dict(tickformat=",d", gridcolor="#f0f0f0"),
            xaxis=dict(gridcolor="#f0f0f0"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_et, use_container_width=True)
        dl_buttons(df_et, f"erwerbstaetige_{start_j}_{end_j}", "Erwerbstätige (GENESIS)")


# ═══════════════════════════════════════════════════════════════════════════════
# SEITE: MINDESTLOHN
# ═══════════════════════════════════════════════════════════════════════════════
elif "Mindestlohn" in seite:
    st.header("Mindestlohn-Monitoring")
    st.caption(
        "Entwicklung des gesetzlichen Mindestlohns seit 2015 – mit Zeitreihenvergleich "
        "zur Arbeitslosigkeit. So lassen sich Einführung und Anpassungen visuell in den "
        "Arbeitsmarktkontext einbetten."
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
        ["arbeitslose_gesamt", "arbeitslosenquote"],
        format_func=lambda x: {
            "arbeitslose_gesamt": "Arbeitslose (absolut)",
            "arbeitslosenquote":  "Arbeitslosenquote (%)",
        }[x],
        key="ml_sel",
    )
    df_ts_ml = query_arbeitslose(sel_bl, "2015-01", "2024-12", metrik_ml)
    if not df_ts_ml.empty:
        st.plotly_chart(
            chart_zeitreihe(df_ts_ml, metrik_ml, ml_df,
                            titel="Arbeitslosigkeit + Mindestlohn-Anpassungen"),
            use_container_width=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SEITE: DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════════════
elif "Download" in seite:
    st.header("Daten herunterladen")
    st.info(
        "CSV (Semikolon-getrennt, UTF-8 mit BOM — direkt in Excel importierbar) "
        "und Excel (.xlsx mit Metadaten-Blatt). "
        "Geeignet für R, Python, Excel, SPSS und jede weitere Analyse-Software."
    )

    st.subheader("Arbeitslosigkeit (monatlich, alle Bundesländer)")
    dl_buttons(query_arbeitslose(start=start_s, end=end_s),
               f"arbeitslose_{start_j}_{end_j}")

    st.divider()
    st.subheader("Beschäftigung (quartalsweise)")
    dl_buttons(query_beschaeftigung(start=start_s, end=end_s),
               f"beschaeftigung_{start_j}_{end_j}")

    st.divider()
    st.subheader("Erwerbstätige – Jahreswerte (VGR)")
    dl_buttons(query_erwerbstaetige(start_jahr=start_j, end_jahr=end_j),
               f"erwerbstaetige_{start_j}_{end_j}")

    st.divider()
    st.subheader("Mindestlohn-Anpassungshistorie")
    dl_buttons(_mindestlohn(), "mindestlohn_komplett")

    st.divider()
    st.subheader("Regionaler Snapshot (aktuellster Stand je Bundesland)")
    dl_buttons(_snapshot(), "regional_snapshot")

    st.markdown("""
---
**Lizenz:** [Datenlizenz Deutschland 2.0](https://www.govdata.de/dl-de/by-2-0)

**Empfohlene Quellenangabe:**
> Bundesagentur für Arbeit / Statistisches Bundesamt (Destatis), abgerufen via
> Arbeitsmarkt-Dashboard – THWS Business Analytics, {year}.
""".format(year=datetime.now().year))
