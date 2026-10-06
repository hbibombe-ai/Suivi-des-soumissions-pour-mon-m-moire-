"""Suivi de la collecte par enquêteur : quotas, rythme attendu, évolution des fiches.

Paramètres à ajuster en haut du fichier (quotas des lots, rythme, jours travaillés).
"""
from __future__ import annotations

VERSION_TDB = "9"  # doit correspondre à app.py
import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import viz

# ----------------------------------------------------------------- paramètres
OBJECTIF_TOTAL = 427                 # ménages à enquêter dans la ZS
RYTHME_JOUR = 10                     # fiches visées par jour et par enquêteur
SEUIL_ETAPE = 40                     # point d'étape (réunion d'évaluation)
JOURS_TRAVAILLES = "1111110"         # lundi → dimanche : dimanche non travaillé
DATE_DEBUT: dt.date | None = None    # J1 ; None = premier jour présent dans les données

# Quota de chaque enquêteur (lots E1 à E5), noms tels qu'ils sont saisis dans Kobo (A3).
# Un enquêteur absent de cette liste reçoit OBJECTIF_TOTAL / nombre d'enquêteurs.
QUOTAS: dict[str, int] = {
    # "FLODEN": 83,      # E1
    # "ELVIS": 87,       # E2
    # "HERMELINE": 87,   # E3
    # "BEATRICE": 82,    # E4
    # "CHRISTEVIE": 88,  # E5
}


# ----------------------------------------------------------------- calculs
def debut(jours_tous) -> dt.date:
    return DATE_DEBUT or min(jours_tous)


def rang_jour(jour: dt.date, j1: dt.date) -> int:
    """Numéro du jour de collecte (J1 = premier jour), jours non travaillés exclus."""
    return int(np.busday_count(j1, jour + dt.timedelta(days=1), weekmask=JOURS_TRAVAILLES))


def quota(nom: str, n_enqueteurs: int) -> int:
    return QUOTAS.get(nom, round(OBJECTIF_TOTAL / max(1, n_enqueteurs)))


def serie(df: pd.DataFrame, j1: dt.date, fin: dt.date) -> pd.DataFrame:
    """Une ligne par enquêteur et par jour (0 les jours sans fiche), avec le cumul."""
    jours = pd.date_range(min(df["jour"].min(), j1), fin, freq="D").date
    noms = sorted(df["enqueteur"].dropna().unique())
    grille = pd.MultiIndex.from_product([noms, jours], names=["enqueteur", "jour"])
    s = df.groupby(["enqueteur", "jour"]).size().reindex(grille, fill_value=0).rename("n").reset_index()
    s["cumul"] = s.groupby("enqueteur")["n"].cumsum()
    return s


def tableau(s: pd.DataFrame, df: pd.DataFrame, j1: dt.date, fin: dt.date, n_equipe: int) -> pd.DataFrame:
    """Tableau de suivi : total, quota, avancement, écart à l'attendu, fiches par jour."""
    j = rang_jour(fin, j1)
    tab = s.pivot_table(index="enqueteur", columns="jour", values="n", aggfunc="sum", fill_value=0)
    tab.columns = [f"{c:%d/%m}" for c in tab.columns]
    r = pd.DataFrame(index=tab.index)
    r["Fiches"] = tab.sum(axis=1)
    r["Quota"] = [quota(x, n_equipe) for x in tab.index]
    r["Avancement"] = (100 * r["Fiches"] / r["Quota"]).round(0)
    r["Reste"] = (r["Quota"] - r["Fiches"]).clip(lower=0)
    r[f"Attendu à J{j}"] = [min(q, RYTHME_JOUR * j) for q in r["Quota"]]
    r["Écart"] = r["Fiches"] - r[f"Attendu à J{j}"]
    r["Dernière fiche"] = df.groupby("enqueteur")["jour"].max().reindex(tab.index).map(lambda x: f"{x:%d/%m}")
    out = pd.concat([r, tab], axis=1).sort_values("Fiches", ascending=False)
    out.index.name = "Enquêteur"
    return out.reset_index()


# ----------------------------------------------------------------- graphiques
def _axe_jours(fig, jours, n_series: int) -> None:
    """Une graduation par jour sur une courte période, sinon automatique. Légende sous le graphique,
    sur autant de lignes que nécessaire, avec la place réservée pour ne jamais chevaucher les dates."""
    court = len(jours) <= 14
    fig.update_xaxes(tickformat="%d/%m", tickangle=0, **({"dtick": 86400000} if court else {"nticks": 10}))
    lignes = -(-n_series // 4)                     # 4 noms par ligne de légende
    bas = 34 + 22 * lignes                         # place réservée sous l'axe des dates
    fig.update_layout(height=320 + bas,
                      legend=dict(orientation="h", yanchor="top", y=-30 / 272, x=0, entrywidth=0.25,
                                  entrywidthmode="fraction"),
                      margin=dict(l=8, r=16, t=48, b=bas))


def _couleurs(noms, p, equipe=None):
    """Couleur fixe par enquêteur (rang dans l'équipe complète) : elle ne change pas avec le filtre."""
    ref = sorted(equipe) if equipe is not None else noms
    return {n: p["series"][(ref.index(n) if n in ref else i) % len(p["series"])] for i, n in enumerate(noms)}


def courbes_cumul(s: pd.DataFrame, j1: dt.date, quota_un: int, p: dict, titre: str, equipe=None):
    """Cumul des fiches par enquêteur + trajectoire attendue d'un enquêteur + point d'étape."""
    noms = sorted(s["enqueteur"].unique())
    coul = _couleurs(noms, p, equipe)
    fig = go.Figure()
    jours = sorted(s["jour"].unique())
    fig.add_scatter(x=jours, y=[min(quota_un, RYTHME_JOUR * rang_jour(x, j1)) for x in jours], mode="lines",
                    name="Attendu", line=dict(color=p["muted"], width=1.5, dash="dash"),
                    hovertemplate="%{x|%d/%m}<br>Attendu : %{y}<extra></extra>")
    for n in noms:
        g = s[s["enqueteur"] == n]
        fig.add_scatter(x=g["jour"], y=g["cumul"], mode="lines+markers", name=n,
                        line=dict(color=coul[n], width=2),
                        marker=dict(size=7, color=coul[n], line=dict(width=1.5, color=p["surface"])),
                        customdata=g["n"],
                        hovertemplate=f"<b>{n}</b><br>%{{x|%d/%m}}<br>Ce jour : %{{customdata}}<br>Cumul : %{{y}}<extra></extra>")
    fig.add_hline(y=SEUIL_ETAPE, line=dict(color=p["bad"], width=1, dash="dot"),
                  annotation_text=f"point d'étape ({SEUIL_ETAPE})", annotation_position="top left",
                  annotation_font=dict(color=p["bad"], size=11))
    fig.update_layout(**viz.layout(p, height=380, showlegend=True,
                                   title=dict(text=titre, font=dict(size=15, color=p["text"]), x=0, xanchor="left")))
    _axe_jours(fig, jours, len(noms) + 1)
    fig.update_yaxes(title="Fiches (cumul)", rangemode="tozero")
    return fig


def barres_jour(s: pd.DataFrame, rythme: int, p: dict, titre: str, equipe=None):
    """Fiches par jour, empilées par enquêteur, avec la ligne du nombre attendu."""
    noms = sorted(s["enqueteur"].unique())
    coul = _couleurs(noms, p, equipe)
    fig = go.Figure()
    for n in noms:
        g = s[s["enqueteur"] == n]
        fig.add_bar(x=g["jour"], y=g["n"], name=n, marker=dict(color=coul[n], line=dict(width=1, color=p["surface"])),
                    hovertemplate=f"<b>{n}</b><br>%{{x|%d/%m}} : %{{y}} fiche(s)<extra></extra>")
    fig.add_hline(y=rythme, line=dict(color=p["muted"], width=1.5, dash="dash"),
                  annotation_text=f"attendu : {rythme}/jour", annotation_position="top left",
                  annotation_font=dict(color=p["text2"], size=11))
    fig.update_layout(**viz.layout(p, height=380, showlegend=len(noms) > 1, barmode="stack",
                                   title=dict(text=titre, font=dict(size=15, color=p["text"]), x=0, xanchor="left")))
    _axe_jours(fig, sorted(s["jour"].unique()), len(noms))
    fig.update_yaxes(title="Fiches")
    return fig
