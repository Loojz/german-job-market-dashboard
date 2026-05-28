"""
Alle Plotly-Charts – einheitliches Design, einmal definiert.
"""

import json
import urllib.request
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ─── Design-System (THWS-inspiriert) ─────────────────────────────────────────
_FONT      = "-apple-system, BlinkMacSystemFont, 'Helvetica Neue', system-ui, sans-serif"
_GRID      = "#F0F0F0"
_THWS_ORANGE = "#F07000"

_COLORS = [
    "#1B4F72",    # Deep Blue (Hauptreihe)
    _THWS_ORANGE, # THWS Orange (Hervorhebung)
    "#1E8449",  # Waldgrün
    "#B7770D",  # Amber
    "#6C3483",  # Violett
    "#0E6655",  # Petrol
    "#784212",  # Braun
    "#2C3E50",  # Dunkelblau-Grau
]

_BASE_LAYOUT = dict(
    font=dict(family=_FONT, size=13, color="#1D1D1F"),
    plot_bgcolor="white",
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=55, r=25, t=50, b=50),
    hovermode="x unified",
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
        bgcolor="rgba(255,255,255,0.95)", bordercolor="#E5E5EA", borderwidth=1,
        font=dict(color="#1D1D1F"),
    ),
)

_BASE_LAYOUT_NO_MARGIN = {k: v for k, v in _BASE_LAYOUT.items() if k != "margin"}

_MINDESTLOHN_LINE = dict(color="rgba(240, 112, 0, 0.75)", width=1.5, dash="dot")

_QUINTIL_COLORS = {
    "Ärmste 20%":       "#1B4F72",
    "Unteres Mittel":   "#2980B9",
    "Mittleres Mittel": "#85C1E9",
    "Oberes Mittel":    "#D4690A",
    "Reichste 20%":     "#F07000",
}


def _layout(fig: go.Figure, title: str = "", ylabel: str = "") -> go.Figure:
    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(text=title, font=dict(size=14, color="#111111"), x=0),
        xaxis=dict(
            showgrid=True, gridcolor=_GRID, gridwidth=1,
            linecolor="#D2D2D7", linewidth=1, zeroline=False,
            tickfont=dict(size=12, color="#6E6E73"),
            title_font=dict(size=12, color="#6E6E73"),
        ),
        yaxis=dict(
            title=ylabel,
            showgrid=True, gridcolor=_GRID, gridwidth=1,
            linecolor="#D2D2D7", linewidth=1, zeroline=False,
            tickformat=",d",
            tickfont=dict(size=12, color="#6E6E73"),
            title_font=dict(size=12, color="#6E6E73"),
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
            annotation_font=dict(size=8, color="rgba(240,112,0,0.9)"),
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
        "arbeitslose_gesamt":  "Arbeitslose",
        "arbeitslosenquote":   "Quote (%)",
        "arbeitslose_u25":     "Arbeitslose u25",
        "arbeitslose_ausl":    "Ausl. Arbeitslose",
        "unterbeschaeftigung": "Unterbeschäftigung",
    }
    ylab    = _labels.get(metrik, metrik)
    tickfmt = ".1f" if metrik == "arbeitslosenquote" else ",d"

    fig = px.line(
        df, x="datum", y="wert", color="bundesland",
        labels={"datum": "", "wert": ylab, "bundesland": "Bundesland"},
        color_discrete_sequence=_COLORS,
    )
    fig.update_traces(
        line=dict(width=1.8),
        hovertemplate="%{y:,.1f}" if "quote" in metrik else "%{y:,.0f}",
    )
    if ml_df is not None and not ml_df.empty:
        _add_ml_markers(fig, ml_df)
    _layout(fig, titel or ylab, ylab)
    fig.update_yaxes(tickformat=tickfmt)
    return fig


# ─── 2. YoY-Veränderung ──────────────────────────────────────────────────────

def chart_yoy(df: pd.DataFrame, titel: str = "Vorjahresveränderung (%)") -> go.Figure:
    df = df.copy()
    colors = [_THWS_ORANGE if v > 0 else "#1B4F72" for v in df["yoy_pct"]]
    fig = go.Figure(go.Bar(
        x=df["datum"], y=df["yoy_pct"],
        marker_color=colors,
        hovertemplate="<b>%{x|%b %Y}</b><br>%{y:+.1f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_color="#999999", line_width=0.8)
    return _layout(fig, titel, "Veränd. ggü. Vorjahr (%)")


# ─── 3. Beschäftigung gestapelt ──────────────────────────────────────────────

def chart_beschaeftigung_stack(df: pd.DataFrame, bundesland: str = "") -> go.Figure:
    if bundesland:
        df = df[df["bundesland"] == bundesland]

    if "beschaeftigte_svb" in df.columns:
        col1, label1 = "beschaeftigte_svb",          "Sozialversicherungspflichtig"
        col2, label2 = "beschaeftigte_geringfuegig", "Geringfügig beschäftigt"
    else:
        col1, label1 = "beschaeftigte_gesamt", "Beschäftigte gesamt"
        col2, label2 = None, None

    agg_cols = [c for c in [col1, col2] if c and c in df.columns]
    agg = df.groupby("datum")[agg_cols].sum().reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(x=agg["datum"], y=agg[col1],
                         name=label1, marker_color="#1B4F72"))
    if col2 and col2 in agg.columns:
        fig.add_trace(go.Bar(x=agg["datum"], y=agg[col2],
                             name=label2, marker_color="#5D8AA8"))

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


# ─── 4. Choropleth-Karte (Bundesländer) ──────────────────────────────────────

_GEOJSON_URL = (
    "https://raw.githubusercontent.com/isellsoap/deutschlandGeoJSON/"
    "main/2_bundeslaender/4_niedrig.geo.json"
)
_GEOJSON_CACHE: dict | None = None


def _geojson():
    global _GEOJSON_CACHE
    if _GEOJSON_CACHE is not None:
        return _GEOJSON_CACHE

    import pathlib
    local = pathlib.Path(__file__).parent.parent / "data" / "bundeslaender.geojson"
    if local.exists():
        import json as _json
        with open(local, encoding="utf-8") as f:
            _GEOJSON_CACHE = _json.load(f)
        return _GEOJSON_CACHE

    try:
        with urllib.request.urlopen(_GEOJSON_URL, timeout=8) as r:
            data = r.read()
        _GEOJSON_CACHE = json.loads(data)
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

    df = df.copy()
    if "arbeitslosenquote" in df.columns and df["arbeitslosenquote"].isna().all():
        df["arbeitslosenquote"] = (
            df["arbeitslose_gesamt"] /
            (df["beschaeftigte_gesamt"] + df["arbeitslose_gesamt"]) * 100
        ).round(1)

    if not geo:
        fig = px.bar(
            df.sort_values(metrik),
            x=metrik, y="bundesland", orientation="h",
            color=metrik, color_continuous_scale="Blues",
            labels={"bundesland": "", metrik: label},
        )
        return _layout(fig, titel or label)

    fig = px.choropleth(
        df, geojson=geo,
        locations="bundesland", featureidkey="properties.name",
        color=metrik,
        color_continuous_scale=[
            [0.0, "#f7fbff"], [0.2, "#c6dbef"], [0.4, "#6baed6"],
            [0.6, "#2171b5"], [0.8, "#084594"], [1.0, "#08306b"],
        ],
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
        line=dict(color=_THWS_ORANGE, width=2.5, shape="hv"),
        marker=dict(size=8, color=_THWS_ORANGE),
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
    out = df[["bundesland", "datum", "arbeitslosenquote",
              "arbeitslose_gesamt", "beschaeftigte_gesamt"]].copy()
    out.columns = ["Bundesland", "Stand", "AL-Quote (%)*",
                   "Arbeitslose", "Beschäftigte (svpfl.)"]
    out["Stand"]    = out["Stand"].dt.strftime("%m/%Y")
    out["Arbeitslose"] = out["Arbeitslose"].apply(
        lambda x: f"{x:,.0f}".replace(",", ".")
    )
    out["Beschäftigte (svpfl.)"] = out["Beschäftigte (svpfl.)"].apply(
        lambda x: f"{x:,.0f}".replace(",", ".") if pd.notna(x) else "–"
    )
    return out.reset_index(drop=True)


# ─── 7. Choropleth-Karte (Kreisebene) ────────────────────────────────────────
# GeoJSON-Quelle: isellsoap/deutschlandGeoJSON, featureidkey = properties.RS (5-stelliger AGS)

_GEOJSON_KREISE_URL = (
    "https://raw.githubusercontent.com/isellsoap/deutschlandGeoJSON/"
    "main/4_kreise/4_niedrig.geo.json"
)
_GEOJSON_KREISE_CACHE: dict | None = None


def _geojson_kreise():
    global _GEOJSON_KREISE_CACHE
    if _GEOJSON_KREISE_CACHE is not None:
        return _GEOJSON_KREISE_CACHE

    import pathlib
    local = pathlib.Path(__file__).parent.parent / "data" / "kreise.geojson"
    if local.exists():
        import json as _json
        with open(local, encoding="utf-8") as f:
            _GEOJSON_KREISE_CACHE = _json.load(f)
        return _GEOJSON_KREISE_CACHE

    try:
        with urllib.request.urlopen(_GEOJSON_KREISE_URL, timeout=20) as r:
            data = r.read()
        _GEOJSON_KREISE_CACHE = json.loads(data)
        local.parent.mkdir(parents=True, exist_ok=True)
        with open(local, "wb") as f:
            f.write(data)
    except Exception:
        _GEOJSON_KREISE_CACHE = {}
    return _GEOJSON_KREISE_CACHE


def chart_karte_kreise(
    df: pd.DataFrame,
    metrik: str = "median_entgelt",
    titel: str = "",
) -> go.Figure:
    """Choropleth-Karte auf Kreisebene. df muss Spalte 'ags' (5-stellig) enthalten."""
    label = {
        "median_entgelt":    "Median €/Monat",
        "arbeitslosenquote": "AL-Quote (%)",
    }.get(metrik, metrik)
    geo = _geojson_kreise()

    if not geo or df.empty:
        fig = px.bar(
            df.sort_values(metrik, ascending=False).head(25),
            x=metrik, y="kreis", orientation="h",
            color=metrik, color_continuous_scale="Oranges",
            labels={"kreis": "", metrik: label},
        )
        return _layout(fig, titel or label)

    fig = px.choropleth(
        df, geojson=geo,
        locations="ags", featureidkey="properties.RS",
        color=metrik,
        color_continuous_scale=[
            [0.0,  "#fff5eb"],
            [0.25, "#fdd0a2"],
            [0.5,  "#fd8d3c"],
            [0.75, "#d94801"],
            [1.0,  "#7f2704"],
        ],
        labels={metrik: label},
        custom_data=["kreis", "bundesland", metrik],
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "%{customdata[1]}<br>"
            f"{label}: " + "%{customdata[2]:,.0f}<extra></extra>"
        )
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(
        **_BASE_LAYOUT_NO_MARGIN,
        margin=dict(l=0, r=0, t=50, b=0),
        title=dict(text=titel or label, font=dict(size=14), x=0),
        geo=dict(bgcolor="rgba(0,0,0,0)"),
        coloraxis_colorbar=dict(title=label, len=0.6),
    )
    return fig


# ─── 8. Quintil-Verlauf ──────────────────────────────────────────────────────

def chart_quintil_verlauf(df: pd.DataFrame, titel: str = "") -> go.Figure:
    """Lohnentwicklung je Entgelt-Quintil über die Zeit (Trendvergleich)."""
    fig = go.Figure()
    for gruppe, farbe in _QUINTIL_COLORS.items():
        d = df[df["quantil_gruppe"] == gruppe].sort_values("jahr")
        if d.empty:
            continue
        fig.add_trace(go.Scatter(
            x=d["jahr"], y=d["avg_entgelt"],
            name=gruppe,
            mode="lines+markers",
            line=dict(color=farbe, width=2.5),
            marker=dict(size=7),
            hovertemplate=(
                f"<b>{gruppe}</b><br>"
                "Jahr: %{x}<br>"
                "Ø Entgelt: %{y:,.0f} €/Monat<extra></extra>"
            ),
        ))
    _layout(
        fig,
        titel or "Lohnentwicklung nach Entgelt-Quintil (Kreisebene)",
        "Ø Median-Entgelt €/Monat",
    )
    fig.update_yaxes(tickformat=",.0f")
    fig.update_xaxes(dtick=1)
    return fig


# ─── 9. Gruppen-Vergleich (zwei frei wählbare Quintile) ──────────────────────

def chart_gruppen_vergleich(
    df: pd.DataFrame,
    label_a: str = "Gruppe A",
    label_b: str = "Gruppe B",
    highlight_jahr: int | None = None,
) -> go.Figure:
    """
    Zwei Linien: Gruppe A (orange) vs. Gruppe B (blau) mit Gap-Schattierung.
    df muss Spalten 'jahr','entgelt_a','entgelt_b','gap_absolut','gap_pct' haben.
    Reihenfolge im Stack basiert auf Median (höhere Gruppe = oben).
    """
    fig = go.Figure()

    # Welche Gruppe liegt oben? -> für korrekte Gap-Schattierung
    a_oben = df["entgelt_a"].mean() >= df["entgelt_b"].mean()
    y_top    = df["entgelt_a"] if a_oben else df["entgelt_b"]
    y_bottom = df["entgelt_b"] if a_oben else df["entgelt_a"]

    fig.add_trace(go.Scatter(
        x=df["jahr"], y=y_top,
        mode="lines", line=dict(width=0),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=df["jahr"], y=y_bottom,
        mode="lines", line=dict(width=0),
        fill="tonexty", fillcolor="rgba(240, 112, 0, 0.10)",
        showlegend=False, hoverinfo="skip",
    ))

    fig.add_trace(go.Scatter(
        x=df["jahr"], y=df["entgelt_a"],
        name=label_a,
        mode="lines+markers",
        line=dict(color=_THWS_ORANGE, width=2.8),
        marker=dict(size=7),
        hovertemplate=f"<b>{label_a}</b><br>%{{x}}<br>%{{y:,.0f}} €/Monat<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df["jahr"], y=df["entgelt_b"],
        name=label_b,
        mode="lines+markers",
        line=dict(color="#1B4F72", width=2.8),
        marker=dict(size=7),
        hovertemplate=f"<b>{label_b}</b><br>%{{x}}<br>%{{y:,.0f}} €/Monat<extra></extra>",
    ))

    if highlight_jahr is not None and highlight_jahr in df["jahr"].values:
        row = df[df["jahr"] == highlight_jahr].iloc[0]
        fig.add_vline(
            x=highlight_jahr,
            line=dict(color="#8E8E93", width=1, dash="dash"),
        )
        y_anchor = max(row["entgelt_a"], row["entgelt_b"])
        fig.add_annotation(
            x=highlight_jahr, y=y_anchor,
            text=f"Δ {abs(row['gap_absolut']):,.0f} € ({abs(row['gap_pct']):.1f} %)",
            showarrow=True, arrowhead=2, arrowcolor="#8E8E93",
            ax=30, ay=-30,
            bgcolor="rgba(255,255,255,0.95)",
            bordercolor="#F07000", borderwidth=1, borderpad=4,
            font=dict(size=11, color="#1D1D1F"),
        )

    _layout(fig, f"{label_a} vs. {label_b}", "Median-Entgelt €/Monat")
    fig.update_yaxes(tickformat=",.0f")
    fig.update_xaxes(dtick=1)
    return fig


def chart_gap_verlauf(
    df: pd.DataFrame,
    label_a: str = "Gruppe A",
    label_b: str = "Gruppe B",
) -> go.Figure:
    """
    Lückenverlauf in Prozent: positiv = B liegt vor A, negativ = A liegt vor B.
    """
    fig = go.Figure(go.Scatter(
        x=df["jahr"], y=df["gap_pct"],
        mode="lines+markers",
        line=dict(color=_THWS_ORANGE, width=2.8),
        marker=dict(size=8, color=_THWS_ORANGE),
        fill="tozeroy", fillcolor="rgba(240, 112, 0, 0.08)",
        hovertemplate="<b>%{x}</b><br>Lücke: %{y:+.1f} %<extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color="#999999", width=0.8))
    _layout(
        fig,
        f"Lohnlücke ({label_b} – {label_a}) in %",
        "Vorsprung %",
    )
    fig.update_yaxes(tickformat=".1f", ticksuffix=" %")
    fig.update_xaxes(dtick=1)
    return fig


# ─── 10. Kreis-Story Charts ──────────────────────────────────────────────────

_QUINTIL_ORDER = ["Ärmste 20%", "Unteres Mittel", "Mittleres Mittel",
                  "Oberes Mittel", "Reichste 20%"]


def chart_quintil_bahn(df: pd.DataFrame, kreis_name: str = "") -> go.Figure:
    """
    Quintil-Bahn: 5 horizontale Bahnen, eine farbige Markierung pro Jahr
    zeigt in welcher Bahn der Kreis war. Sprünge zwischen den Bahnen
    werden direkt als Höhensprünge sichtbar.
    """
    if df.empty or df["quantil_gruppe"].isna().all():
        fig = go.Figure()
        _layout(fig, "Quintil-Bahn — keine Daten")
        return fig

    d = df.dropna(subset=["quantil_gruppe"]).copy()
    pos_map = {q: i for i, q in enumerate(_QUINTIL_ORDER)}
    d["y_pos"] = d["quantil_gruppe"].map(pos_map)

    fig = go.Figure()

    # Hintergrund-Bahnen
    for i, q in enumerate(_QUINTIL_ORDER):
        fig.add_hrect(
            y0=i - 0.45, y1=i + 0.45,
            fillcolor=_QUINTIL_COLORS[q], opacity=0.10,
            line_width=0, layer="below",
        )

    # Trajektorie als Step-Line
    fig.add_trace(go.Scatter(
        x=d["jahr"], y=d["y_pos"],
        mode="lines",
        line=dict(color="#8E8E93", width=2, shape="hv"),
        showlegend=False, hoverinfo="skip",
    ))

    # Marker pro Jahr in der Farbe seines Quintils
    marker_colors = [_QUINTIL_COLORS.get(q, "#999") for q in d["quantil_gruppe"]]
    fig.add_trace(go.Scatter(
        x=d["jahr"], y=d["y_pos"],
        mode="markers+text",
        marker=dict(
            size=22, color=marker_colors,
            line=dict(color="white", width=2.5),
        ),
        text=d["jahr"].astype(str),
        textposition="top center",
        textfont=dict(size=9, color="#6E6E73"),
        hovertemplate="<b>%{x}</b><br>%{customdata}<extra></extra>",
        customdata=d["quantil_gruppe"],
        showlegend=False,
    ))

    title = f"Quintil-Bahn{' — ' + kreis_name if kreis_name else ''}"
    _layout(fig, title)
    fig.update_yaxes(
        range=[-0.7, 4.7],
        tickvals=list(range(5)),
        ticktext=_QUINTIL_ORDER,
        showgrid=False, zeroline=False,
        tickfont=dict(size=11, color="#3A3A3C"),
    )
    fig.update_xaxes(
        dtick=1, gridcolor=_GRID,
        tickfont=dict(size=11, color="#6E6E73"),
    )
    fig.update_layout(margin=dict(l=120, r=25, t=50, b=40), height=380)
    return fig


def chart_kreis_im_kontext(
    df_kreis: pd.DataFrame,
    df_quintile: pd.DataFrame,
    kreis_name: str = "",
) -> go.Figure:
    """
    Lohnverlauf des Kreises (dicke orange Linie) im Kontext der 5
    Quintil-Durchschnitte (graue Punkt-Linien im Hintergrund).
    """
    fig = go.Figure()

    # Hintergrund: 5 Quintil-Durchschnittslinien
    for gruppe in _QUINTIL_ORDER:
        dq = df_quintile[df_quintile["quantil_gruppe"] == gruppe].sort_values("jahr")
        if dq.empty:
            continue
        fig.add_trace(go.Scatter(
            x=dq["jahr"], y=dq["avg_entgelt"],
            name=gruppe, mode="lines",
            line=dict(color=_QUINTIL_COLORS[gruppe], width=1.3, dash="dot"),
            opacity=0.55,
            hovertemplate=f"<b>{gruppe}</b><br>%{{x}}: %{{y:,.0f}} €<extra></extra>",
        ))

    # Kreis-Linie (Vordergrund)
    fig.add_trace(go.Scatter(
        x=df_kreis["jahr"], y=df_kreis["median_entgelt"],
        name=kreis_name or "Kreis", mode="lines+markers",
        line=dict(color=_THWS_ORANGE, width=3.5),
        marker=dict(size=10, color=_THWS_ORANGE,
                    line=dict(color="white", width=1.5)),
        hovertemplate=(
            f"<b>{kreis_name}</b><br>"
            "%{x}: %{y:,.2f} €/Monat<extra></extra>"
        ),
    ))

    _layout(
        fig,
        f"{kreis_name} im Quintil-Kontext" if kreis_name else "Kreis im Kontext",
        "Median-Entgelt €/Monat",
    )
    fig.update_yaxes(tickformat=",.0f")
    fig.update_xaxes(dtick=1)
    return fig


def chart_rang_sparkline(df: pd.DataFrame, kreis_name: str = "") -> go.Figure:
    """
    Rang-Verlauf des Kreises unter allen ~400 Kreisen.
    Y-Achse invertiert: Platz 1 oben, höchste Zahl unten.
    """
    if df.empty:
        fig = go.Figure()
        _layout(fig, "Rang — keine Daten")
        return fig

    n_kreise = int(df["n_kreise"].max())
    fig = go.Figure(go.Scatter(
        x=df["jahr"], y=df["rang"],
        mode="lines+markers",
        line=dict(color=_THWS_ORANGE, width=2.8),
        marker=dict(size=9, color=_THWS_ORANGE,
                    line=dict(color="white", width=1.5)),
        fill="tozeroy", fillcolor="rgba(240,112,0,0.06)",
        hovertemplate=(
            f"<b>{kreis_name}</b><br>"
            "Jahr: %{x}<br>"
            "Platz %{y} von " + str(n_kreise) + "<extra></extra>"
        ),
    ))
    _layout(
        fig,
        f"Rang über die Jahre (von {n_kreise} Kreisen)",
        "Platzierung (Platz 1 = höchster Lohn)",
    )
    fig.update_yaxes(autorange="reversed", tickformat="d")
    fig.update_xaxes(dtick=1)
    return fig


# ─── 11. Mindestlohn vs. Tariflohnindex (Indexvergleich) ─────────────────────

def chart_mindestlohn_vs_tariflohn(df: pd.DataFrame, basis_jahr: int = 2015) -> go.Figure:
    """
    Index-Vergleich: Mindestlohn und Tariflohnindex auf gemeinsamer Basis
    (Standard: basis_jahr = 100). Zeigt wie stark der Mindestlohn relativ
    zum allgemeinen Tariflohn-Trend gestiegen ist.
    """
    if df.empty:
        fig = go.Figure()
        _layout(fig, "Mindestlohn vs. Tariflohn — keine Daten")
        return fig

    fig = go.Figure()

    # Schattierte Fläche zwischen den beiden Linien = das "Mindestlohn-Plus"
    # (nur wenn Mindestlohn-Index > Tariflohn-Index)
    fig.add_trace(go.Scatter(
        x=df["jahr"], y=df["mindestlohn_idx"],
        mode="lines", line=dict(width=0),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=df["jahr"], y=df["tariflohn_idx"],
        mode="lines", line=dict(width=0),
        fill="tonexty", fillcolor="rgba(240, 112, 0, 0.10)",
        showlegend=False, hoverinfo="skip",
    ))

    # Tariflohnindex (Hintergrund-Linie)
    fig.add_trace(go.Scatter(
        x=df["jahr"], y=df["tariflohn_idx"],
        name="Tariflohnindex (Destatis)",
        mode="lines+markers",
        line=dict(color="#1B4F72", width=2.5),
        marker=dict(size=7),
        customdata=df["tariflohn_idx2020"],
        hovertemplate=(
            "<b>Tariflohnindex</b><br>"
            "Jahr: %{x}<br>"
            "Index (Basis " + str(basis_jahr) + "=100): %{y:.1f}<br>"
            "Original (2020=100): %{customdata:.1f}<extra></extra>"
        ),
    ))

    # Mindestlohn (Vordergrund-Linie)
    fig.add_trace(go.Scatter(
        x=df["jahr"], y=df["mindestlohn_idx"],
        name="Mindestlohn (BMAS)",
        mode="lines+markers",
        line=dict(color=_THWS_ORANGE, width=3.2),
        marker=dict(size=8, color=_THWS_ORANGE,
                    line=dict(color="white", width=1.5)),
        customdata=df["mindestlohn_eur"],
        hovertemplate=(
            "<b>Mindestlohn</b><br>"
            "Jahr: %{x}<br>"
            "Index (Basis " + str(basis_jahr) + "=100): %{y:.1f}<br>"
            "€/Stunde: %{customdata:.2f}<extra></extra>"
        ),
    ))

    # Basis-Linie 100
    fig.add_hline(
        y=100, line=dict(color="#999", width=0.8, dash="dot"),
        annotation_text=f"Basis {basis_jahr}",
        annotation_position="left",
        annotation_font=dict(size=10, color="#6E6E73"),
    )

    _layout(
        fig,
        f"Mindestlohn vs. Tariflohnindex (Basis {basis_jahr} = 100)",
        f"Index ({basis_jahr} = 100)",
    )
    fig.update_yaxes(tickformat=".0f")
    fig.update_xaxes(dtick=1)
    return fig


# Backward-compat Alias
def chart_armste_vs_rest(df, vergleichs_label="Reichste 20%", highlight_jahr=None):
    """Wrapper für alte Aufrufe — erwartet 'entgelt_armste'/'entgelt_vergleich'-Spalten."""
    d = df.rename(columns={"entgelt_armste": "entgelt_a", "entgelt_vergleich": "entgelt_b"})
    return chart_gruppen_vergleich(d, "Ärmste 20%", vergleichs_label, highlight_jahr)
