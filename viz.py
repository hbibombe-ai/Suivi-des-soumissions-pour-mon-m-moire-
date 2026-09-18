"""Thème graphique et composants de visualisation (palette validée, mode clair/sombre)."""
from __future__ import annotations
import math
import plotly.graph_objects as go

# --- Palette (validée pour les déficiences de vision des couleurs) -----------
LIGHT = dict(
    surface="#fcfcfb", panel="#ffffff", text="#0b0b0b", text2="#52514e", muted="#8a8a86",
    grid="#e6e5e1", series=["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
    ordinal=["#1c5cab", "#3987e5", "#86b6ef"],  # Basique > Limité > Aucun (une seule teinte)
    good="#008300", warn="#eda100", bad="#e34948",
)
DARK = dict(
    surface="#1a1a19", panel="#222220", text="#ffffff", text2="#c3c2b7", muted="#8f8e86",
    grid="#3a3a37", series=["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
    ordinal=["#184f95", "#3987e5", "#86b6ef"],
    good="#4caf50", warn="#c98500", bad="#e66767",
)

def palette(dark: bool) -> dict:
    return DARK if dark else LIGHT

def layout(p: dict, height: int = 360, showlegend: bool = False, **kw) -> dict:
    """Mise en page commune : grille discrète, encres de texte, fond transparent."""
    base = dict(
        height=height, showlegend=showlegend,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, Arial, sans-serif", size=13, color=p["text2"]),
        margin=dict(l=8, r=16, t=48, b=8),
        title=dict(font=dict(size=15, color=p["text"]), x=0, xanchor="left", y=0.97),
        hoverlabel=dict(bgcolor=p["panel"], font=dict(color=p["text"], size=12), bordercolor=p["grid"]),
        xaxis=dict(gridcolor=p["grid"], zerolinecolor=p["grid"], linecolor=p["grid"], tickfont=dict(color=p["text2"])),
        yaxis=dict(gridcolor=p["grid"], zerolinecolor=p["grid"], linecolor=p["grid"], tickfont=dict(color=p["text2"])),
        legend=dict(orientation="h", y=-0.16, x=0, font=dict(color=p["text2"], size=12)),
        bargap=0.28,
    )
    base.update(kw)
    return base

# --- Statistiques -----------------------------------------------------------
def wilson(k: int, n: int, z: float = 1.96):
    """Intervalle de confiance à 95 % d'une proportion (méthode de Wilson)."""
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / d
    demi = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / d
    return p, max(0.0, centre - demi), min(1.0, centre + demi)

def ratio_prevalence(a: int, na: int, b: int, nb: int, z: float = 1.96):
    """Ratio de prévalence exposés/non exposés et son IC 95 % (méthode de Katz)."""
    if min(a, b, na, nb) <= 0:
        return (float("nan"),) * 3
    p1, p0 = a / na, b / nb
    rp = p1 / p0
    se = math.sqrt(1 / a - 1 / na + 1 / b - 1 / nb)
    return rp, rp * math.exp(-z * se), rp * math.exp(z * se)

# --- Graphiques -------------------------------------------------------------
def fr(x: float, dec: int = 1) -> str:
    """Format français : 25.7 -> '25,7'."""
    return f"{x:.{dec}f}".replace(".", ",")


def barres_proportions(libelles, valeurs, bas, haut, effectifs, titre, p, height=None, couleur=None):
    """Barres horizontales de proportions + IC 95 %, valeurs alignées en colonne à droite."""
    couleur = couleur or p["series"][0]
    h = height or max(240, 70 + 38 * len(libelles))
    etiquettes = [f"{l}  (n={n})" for l, n in zip(libelles, effectifs)]
    fig = go.Figure(go.Bar(
        x=valeurs, y=etiquettes, orientation="h", marker=dict(color=couleur, line=dict(width=0)),
        width=0.6, cliponaxis=False,
        error_x=dict(type="data", symmetric=False,
                     array=[hh - v for hh, v in zip(haut, valeurs)],
                     arrayminus=[v - bb for bb, v in zip(bas, valeurs)],
                     color=p["muted"], thickness=1.5, width=5),
        hovertemplate="<b>%{y}</b><br>Proportion : %{x:.1%}<br>IC 95 % : "
                      + "%{customdata[0]:.1%} – %{customdata[1]:.1%}<extra></extra>",
        customdata=list(zip(bas, haut)),
    ))
    # colonne de valeurs à droite (lisible quel que soit le contraste de la barre)
    annotations = [dict(xref="paper", x=1.0, y=e, xanchor="left", yanchor="middle", showarrow=False,
                        text=f"<b>{fr(v*100)} %</b>", font=dict(color=p["text"], size=12))
                   for e, v in zip(etiquettes, valeurs)]
    m = max([hh for hh in haut if hh == hh] or [0.1])
    fig.update_layout(**layout(p, height=h, annotations=annotations,
                               margin=dict(l=8, r=72, t=48, b=8),
                               title=dict(text=titre, font=dict(size=15, color=p["text"]), x=0, xanchor="left")))
    fig.update_xaxes(tickformat=".0%", range=[0, min(1.0, m * 1.05 + 0.02)])
    fig.update_yaxes(autorange="reversed")
    return fig


def fr(x: float, dec: int = 1) -> str:
    """Format français : 25.7 -> '25,7'."""
    return f"{x:.{dec}f}".replace(".", ",")


def barres_temps(x, y, titre, p, couleur=None, ytitre=""):
    couleur = couleur or p["series"][0]
    fig = go.Figure(go.Bar(x=x, y=y, marker=dict(color=couleur, line=dict(width=2, color=p["surface"])),
                           hovertemplate="%{x|%d/%m/%Y}<br>%{y} fiche(s)<extra></extra>"))
    fig.update_layout(**layout(p, height=300, title=dict(text=titre, font=dict(size=15, color=p["text"]), x=0, xanchor="left")))
    fig.update_yaxes(title=ytitre)
    return fig

def courbe_cumul(x, y, titre, p):
    fig = go.Figure(go.Scatter(x=x, y=y, mode="lines+markers",
                               line=dict(color=p["series"][0], width=2),
                               marker=dict(size=8, color=p["series"][0], line=dict(width=2, color=p["surface"])),
                               hovertemplate="%{x|%d/%m/%Y}<br>Cumul : %{y}<extra></extra>"))
    fig.update_layout(**layout(p, height=300, hovermode="x unified",
                               title=dict(text=titre, font=dict(size=15, color=p["text"]), x=0, xanchor="left")))
    return fig

def barres_empilees(categories, series, titre, p):
    """series = [(libellé, [valeurs par catégorie])] — échelle ordinale à une teinte."""
    fig = go.Figure()
    for i, (nom, vals) in enumerate(series):
        fig.add_bar(name=nom, x=categories, y=vals,
                    marker=dict(color=p["ordinal"][i % len(p["ordinal"])], line=dict(width=2, color=p["surface"])),
                    text=[f"{v*100:.0f} %" if v >= 0.08 else "" for v in vals],
                    textposition="inside", insidetextfont=dict(color="#ffffff", size=12),
                    hovertemplate="<b>%{x}</b><br>" + nom + " : %{y:.1%}<extra></extra>")
    fig.update_layout(**layout(p, height=340, showlegend=True, barmode="stack", legend_traceorder="reversed",
                               title=dict(text=titre, font=dict(size=15, color=p["text"]), x=0, xanchor="left")))
    fig.update_yaxes(tickformat=".0%", range=[0, 1])
    return fig

def points_ratios(libelles, rp, bas, haut, titre, p):
    """Graphique en forêt : ratios de prévalence avec IC 95 % et ligne de référence à 1."""
    h = max(240, 70 + 34 * len(libelles))
    fig = go.Figure(go.Scatter(
        x=rp, y=libelles, mode="markers", marker=dict(size=11, color=p["series"][0], line=dict(width=2, color=p["surface"])),
        error_x=dict(type="data", symmetric=False,
                     array=[hh - v for hh, v in zip(haut, rp)], arrayminus=[v - bb for bb, v in zip(bas, rp)],
                     color=p["muted"], thickness=1.5, width=5),
        hovertemplate="<b>%{y}</b><br>RP = %{x:.2f}<br>IC 95 % : %{customdata[0]:.2f} – %{customdata[1]:.2f}<extra></extra>",
        customdata=list(zip(bas, haut)),
    ))
    fig.add_vline(x=1, line=dict(color=p["muted"], width=1, dash="dot"))
    fig.update_layout(**layout(p, height=h, title=dict(text=titre, font=dict(size=15, color=p["text"]), x=0, xanchor="left")))
    fig.update_xaxes(type="log", title="Ratio de prévalence (échelle log.)")
    fig.update_yaxes(autorange="reversed")
    return fig

def barres_distribution(x, y, titre, p, xtitre=""):
    fig = go.Figure(go.Bar(x=x, y=y, marker=dict(color=p["series"][0], line=dict(width=2, color=p["surface"])),
                           hovertemplate="Score %{x}/8 : %{y} enfant(s)<extra></extra>"))
    fig.update_layout(**layout(p, height=300, title=dict(text=titre, font=dict(size=15, color=p["text"]), x=0, xanchor="left")))
    fig.update_xaxes(title=xtitre, dtick=1)
    return fig
