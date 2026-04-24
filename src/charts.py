"""
Alle Plotly-Charts – einheitliches Design, einmal definiert.
"""

import json
import urllib.request
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ─── Design-System ───────────────────────────────────────────────────────────
_FONT   = "Inter, system-ui, sans-serif"
_GRID   = "#f0f0f0"
_COLORS = px.colors.qualitative.Plotly

_BASE_LAYOUT = dict(
    font=dict(family=_FONT, size=13),
    plot_bgcolor="white",
    paper_bgcolor="white",
    margin=dict(l=55, r=25, t=50, b=50),
    hovermode="x unified",
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
        bgcolor="rgba(255,255,255,0.9)", bordercolor="#e0e0e0", borderwidth=1,
    ),
)

# Karten-Layout ohne margin (wird separat gesetzt)
_BASE_LAYOUT_NO_MARGIN = {k: v for k, v in _BASE_LAYOUT.items() if k != "margin"}

_MINDESTLOHN_LINE = dict(color="rgba(220, 90, 20, 0.6)", width=1.2, dash="dot")


def _layout(fig: go.Figure, title: str = "", ylabel: str = "") -> go.Figure:
    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(text=title, font=dict(size=14, color="#2d2d2d"), x=0),
        xaxis=dict(showgrid=True, gridcolor=_GRID, linecolor="#ccc", zeroline=False),
        yaxis=dict(
            title=ylabel, showgrid=True, gridcolor=_GRID,
            linecolor="#ccc", zeroline=False, tickformat=",d",
        ),
    )
    return fig


def _add_ml_markers(fig: go.Figure, ml_df: pd.DataFrame) -> go.Figure:
    for _, row in ml_df.iterrows():
        fig.add_vline(
            x=row["datum"].timestamp() * 1000,
            line=_MINDESTLOHN_LINE,
            annotation_text=f"€{row['betrag']:.2f}",
            annotation_position="top",
            annotation_font=dict(size=8, color="rgba(180,70,0,0.85)"),
            annotation_bgcolor="rgba(255,255,255,0.7)",
        )
    return fig


# ─── 1. Zeitreihe ────────────────────────────────────────────────────────────

def chart_zeitreihe(
    df: pd.DataFrame,
    metrik: str = "arbeitslose_gesamt",
    ml_df: pd.DataFrame | None = None,
    titel: str = "",
) -> go.Figure:
    _labels = {
        "arbeitslose_gesamt": "Arbeitslose",
        "arbeitslosenquote":  "Quote (%)",
        "arbeitslose_u25":    "Arbeitslose u25",
        "arbeitslose_ausl":   "Ausl. Arbeitslose",
    }
    ylab = _labels.get(metrik, metrik)

    # Quote: keine Tausender-Formatierung
    tickfmt = ".1f" if metrik == "arbeitslosenquote" else ",d"

    fig = px.line(
        df, x="datum", y="wert", color="bundesland",
        labels={"datum": "", "wert": ylab, "bundesland": "Bundesland"},
        color_discrete_sequence=_COLORS,
    )
    fig.update_traces(line=dict(width=1.8), hovertemplate="%{y:,.1f}" if "quote" in metrik else "%{y:,.0f}")
    if ml_df is not None and not ml_df.empty:
        _add_ml_markers(fig, ml_df)
    _layout(fig, titel or ylab, ylab)
    fig.update_yaxes(tickformat=tickfmt)
    return fig


# ─── 2. YoY-Veränderung ──────────────────────────────────────────────────────

def chart_yoy(df: pd.DataFrame, titel: str = "Vorjahresveränderung (%)") -> go.Figure:
    df = df.copy()
    colors = ["#d62728" if v > 0 else "#2ca02c" for v in df["yoy_pct"]]
    fig = go.Figure(go.Bar(
        x=df["datum"], y=df["yoy_pct"],
        marker_color=colors,
        hovertemplate="<b>%{x|%b %Y}</b><br>%{y:+.1f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_color="#999", line_width=0.8)
    return _layout(fig, titel, "Veränd. ggü. Vorjahr (%)")


# ─── 3. Beschäftigung gestapelt ──────────────────────────────────────────────

def chart_beschaeftigung_stack(df: pd.DataFrame, bundesland: str = "") -> go.Figure:
    if bundesland:
        df = df[df["bundesland"] == bundesland]
    agg = df.groupby("datum")[["beschaeftigte_vz", "beschaeftigte_tz"]].sum().reset_index()
    fig = go.Figure()
    fig.add_trace(go.Bar(x=agg["datum"], y=agg["beschaeftigte_vz"],
                         name="Vollzeit", marker_color="#1f77b4"))
    fig.add_trace(go.Bar(x=agg["datum"], y=agg["beschaeftigte_tz"],
                         name="Teilzeit", marker_color="#aec7e8"))
    fig.update_layout(
        **_BASE_LAYOUT,
        barmode="stack",
        title=dict(
            text=f"Beschäftigung{' – ' + bundesland if bundesland else ' – Gesamt'}",
            font=dict(size=14), x=0,
        ),
    )
    fig.update_yaxes(title="Beschäftigte", tickformat=",d", gridcolor=_GRID)
    fig.update_xaxes(showgrid=False)
    return fig


# ─── 4. Choropleth-Karte ─────────────────────────────────────────────────────

_GEOJSON_URL = (
    "https://raw.githubusercontent.com/isellsoap/deutschlandGeoJSON/"
    "main/2_bundeslaender/4_niedrig.geo.json"
)
_GEOJSON_CACHE: dict | None = None


def _geojson():
    global _GEOJSON_CACHE
    if _GEOJSON_CACHE is not None:
        return _GEOJSON_CACHE

    # Erst lokal versuchen (schneller, offline-fähig)
    import pathlib
    local = pathlib.Path(__file__).parent.parent / "data" / "bundeslaender.geojson"
    if local.exists():
        import json as _json
        with open(local, encoding="utf-8") as f:
            _GEOJSON_CACHE = _json.load(f)
        return _GEOJSON_CACHE

    # Fallback: von GitHub laden und lokal speichern
    try:
        with urllib.request.urlopen(_GEOJSON_URL, timeout=8) as r:
            data = r.read()
        _GEOJSON_CACHE = json.loads(data)
        # Für nächstes Mal lokal speichern
        local.parent.mkdir(parents=True, exist_ok=True)
        with open(local, "wb") as f:
            f.write(data)
    except Exception:
        _GEOJSON_CACHE = {}
    return _GEOJSON_CACHE


def chart_karte(
    df: pd.DataFrame,
    metrik: str = "arbeitslosenquote",
    titel: str = "",
) -> go.Figure:
    _mlabels = {
        "arbeitslosenquote":    "AL-Quote (%)",
        "arbeitslose_gesamt":   "Arbeitslose",
        "beschaeftigte_gesamt": "Beschäftigte",
    }
    label = _mlabels.get(metrik, metrik)
    geo   = _geojson()

    # Sicherstellen dass Quote-Werte vorhanden sind
    df = df.copy()
    if "arbeitslosenquote" in df.columns and df["arbeitslosenquote"].isna().all():
        df["arbeitslosenquote"] = (
            df["arbeitslose_gesamt"] /
            (df["beschaeftigte_gesamt"] + df["arbeitslose_gesamt"]) * 100
        ).round(1)

    # Fallback: Balken-Chart wenn GeoJSON nicht ladbar
    if not geo:
        fig = px.bar(
            df.sort_values(metrik),
            x=metrik, y="bundesland", orientation="h",
            color=metrik, color_continuous_scale="Blues",
            labels={"bundesland": "", metrik: label},
        )
        return _layout(fig, titel or label)

    # Hover-Template manuell definieren (vermeidet Plotly-Syntax-Fehler)
    fig = px.choropleth(
        df, geojson=geo,
        locations="bundesland", featureidkey="properties.name",
        color=metrik, color_continuous_scale="Blues_r",
        labels={metrik: label},
        custom_data=["bundesland", "arbeitslose_gesamt", "arbeitslosenquote"],
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Arbeitslose: %{customdata[1]:,.0f}<br>"
            "AL-Quote: %{customdata[2]:.1f} %<extra></extra>"
        )
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(
        **_BASE_LAYOUT_NO_MARGIN,
        margin=dict(l=0, r=0, t=50, b=0),
        title=dict(text=titel or label, font=dict(size=14), x=0),
        geo=dict(bgcolor="rgba(0,0,0,0)"),
        coloraxis_colorbar=dict(title=label, len=0.55),
    )
    return fig


# ─── 5. Mindestlohn-Treppe ───────────────────────────────────────────────────

def chart_mindestlohn(ml_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Scatter(
        x=ml_df["datum"], y=ml_df["betrag"],
        mode="lines+markers+text",
        line=dict(color="#e67e22", width=2.5, shape="hv"),
        marker=dict(size=8, color="#e67e22"),
        text=ml_df["betrag"].apply(lambda x: f"€{x:.2f}"),
        textposition="top center",
        textfont=dict(size=10),
        hovertemplate="<b>%{x|%d.%m.%Y}</b><br>€%{y:.2f}/Std.<extra></extra>",
    ))
    _layout(fig, "Entwicklung des gesetzlichen Mindestlohns", "€ / Stunde")
    fig.update_yaxes(tickformat=".2f")
    return fig


# ─── 6. Ranking-Tabelle ──────────────────────────────────────────────────────

def format_ranking(df: pd.DataFrame) -> pd.DataFrame:
    # Arbeitslosenquote berechnen falls nan
    if df["arbeitslosenquote"].isna().all():
        df = df.copy()
        df["arbeitslosenquote"] = (
            df["arbeitslose_gesamt"] / (df["beschaeftigte_gesamt"] * 1.15) * 100
        ).round(1)

    out = df[["bundesland", "datum", "arbeitslosenquote",
              "arbeitslose_gesamt", "beschaeftigte_gesamt"]].copy()
    out.columns = ["Bundesland", "Stand", "AL-Quote (%)", "Arbeitslose", "Beschäftigte (svpfl.)"]
    out["Stand"]    = out["Stand"].dt.strftime("%m/%Y")
    out["Arbeitslose"] = out["Arbeitslose"].apply(
        lambda x: f"{x:,.0f}".replace(",", ".")
    )
    out["Beschäftigte (svpfl.)"] = out["Beschäftigte (svpfl.)"].apply(
        lambda x: f"{x:,.0f}".replace(",", ".") if pd.notna(x) else "–"
    )
    return out.reset_index(drop=True)
