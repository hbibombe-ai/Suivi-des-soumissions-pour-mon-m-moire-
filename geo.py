"""Géolocalisation des ménages : lecture du champ GPS (A7), contrôle qualité, floutage et cartes.

Le champ `a7_gps` (geopoint) arrive de KoboToolbox sous la forme « latitude longitude altitude précision ».
KoboToolbox fournit aussi `_geolocation` = [latitude, longitude], utilisé en secours.
"""
from __future__ import annotations

VERSION_TDB = "6"  # doit correspondre à app.py
import hashlib
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# Emprise de contrôle : commune de Limete et ses abords (large marge).
# Un point en dehors est signalé « hors zone » (erreur de saisie, GPS non fixé, position par défaut 0/0…).
EMPRISE = dict(lat_min=-4.45, lat_max=-4.28, lon_min=15.24, lon_max=15.42)
CENTRE = dict(lat=-4.372, lon=15.335)
PRECISION_MAX_M = 50  # au-delà, le point est jugé imprécis

# Positions FICTIVES servant uniquement au mode démonstration (≈ centre de chaque aire).
CENTRES_DEMO = {
    "agricole": (-4.392, 15.318), "industriel_1": (-4.352, 15.335), "industriel_2": (-4.345, 15.350),
    "industriel_3": (-4.338, 15.322), "masiala": (-4.380, 15.345), "mateba": (-4.368, 15.312),
    "mayulu": (-4.385, 15.330), "mfumu": (-4.375, 15.358), "mombele": (-4.360, 15.365),
    "mososo": (-4.358, 15.300), "residentiel": (-4.370, 15.328),
}


def _lire(valeur):
    """'−4.37 15.33 280 5' ou [−4.37, 15.33] → (lat, lon, alt, précision)."""
    if valeur is None or (isinstance(valeur, float) and math.isnan(valeur)):
        return (np.nan,) * 4
    if isinstance(valeur, (list, tuple, np.ndarray)):
        parts = list(valeur)
    else:
        parts = str(valeur).replace(",", " ").split()
    try:
        nums = [float(x) for x in parts[:4]]
    except ValueError:
        return (np.nan,) * 4
    nums += [np.nan] * (4 - len(nums))
    return tuple(nums[:4])


def ajouter_gps(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute lat, lon, gps_precision_m et gps_statut."""
    brut = df["a7_gps"] if "a7_gps" in df.columns else pd.Series(np.nan, index=df.index)
    vals = pd.DataFrame([_lire(v) for v in brut], index=df.index, columns=["lat", "lon", "gps_altitude", "gps_precision_m"])
    if "_geolocation" in df.columns:  # secours : coordonnées extraites par KoboToolbox
        secours = pd.DataFrame([_lire(v) for v in df["_geolocation"]], index=df.index).iloc[:, :2]
        vals["lat"] = vals["lat"].fillna(secours[0])
        vals["lon"] = vals["lon"].fillna(secours[1])
    for c in vals.columns:
        df[c] = vals[c]
    manquant = df["lat"].isna() | df["lon"].isna() | ((df["lat"] == 0) & (df["lon"] == 0))
    hors = ~manquant & ~(df["lat"].between(EMPRISE["lat_min"], EMPRISE["lat_max"])
                         & df["lon"].between(EMPRISE["lon_min"], EMPRISE["lon_max"]))
    imprecis = ~manquant & ~hors & (df["gps_precision_m"] > PRECISION_MAX_M)
    df["gps_statut"] = np.select([manquant, hors, imprecis], ["Manquant", "Hors zone", f"Imprécis (> {PRECISION_MAX_M} m)"], "Valide")
    df.loc[manquant, ["lat", "lon"]] = np.nan
    return df


def flouter(df: pd.DataFrame, rayon_m: float = 150) -> pd.DataFrame:
    """Déplace chaque point d'une distance aléatoire ≤ rayon_m (déplacement stable d'une actualisation à l'autre).

    Protège la confidentialité des ménages quand la carte est montrée ou partagée.
    """
    out = df.copy()
    cle = out["_id"].astype(str) if "_id" in out else pd.Series(out.index.astype(str), index=out.index)
    def decal(k):
        h = int(hashlib.sha256(f"limete-{k}".encode()).hexdigest()[:12], 16)
        angle = (h % 3600) / 3600 * 2 * math.pi
        dist = (0.3 + 0.7 * ((h // 3600) % 1000) / 1000) * rayon_m
        return dist * math.cos(angle), dist * math.sin(angle)
    d = np.array([decal(k) for k in cle]) if len(out) else np.zeros((0, 2))
    if len(out):
        out["lat"] = out["lat"] + d[:, 1] / 111_320
        out["lon"] = out["lon"] + d[:, 0] / (111_320 * np.cos(np.radians(out["lat"].fillna(CENTRE["lat"]))))
    return out


def _fond(sombre: bool) -> str:
    return "carto-darkmatter" if sombre else "open-street-map"


def _mise_en_page(fig: go.Figure, p: dict, titre: str, sombre: bool, zoom: float = 12.6, hauteur: int = 560):
    fig.update_layout(
        map=dict(style=_fond(sombre), center=CENTRE, zoom=zoom),
        height=hauteur, margin=dict(l=0, r=0, t=40, b=0), paper_bgcolor="rgba(0,0,0,0)",
        title=dict(text=titre, x=0, font=dict(size=15, color=p["text"])),
        legend=dict(orientation="h", y=-0.02, x=0, bgcolor="rgba(0,0,0,0)", font=dict(color=p["text2"])),
        font=dict(family="Inter, Segoe UI, Arial, sans-serif", color=p["text2"]),
    )
    return fig


def carte_points(pts: pd.DataFrame, couleur: str, libelle_couleur: str, p: dict, sombre: bool,
                 infobulle: list[tuple[str, str]], titre: str, ordre: list | None = None,
                 couleurs_fixes: dict | None = None) -> go.Figure:
    """Un point par ménage, coloré selon `couleur` (colonne catégorielle)."""
    fig = go.Figure()
    cats = ordre or sorted(pts[couleur].dropna().astype(str).unique())
    couleurs = p["series"]
    for i, cat in enumerate(cats):
        s = pts[pts[couleur].astype(str) == cat]
        if s.empty:
            continue
        texte = s.apply(lambda r: "<br>".join(f"{lib} : {r.get(c, '')}" for lib, c in infobulle), axis=1)
        fig.add_trace(go.Scattermap(lat=s["lat"], lon=s["lon"], mode="markers", name=f"{cat} ({len(s)})",
                                    marker=dict(size=9, opacity=0.85,
                                                color=(couleurs_fixes or {}).get(cat, couleurs[i % len(couleurs)])),
                                    text=texte, hovertemplate="%{text}<extra></extra>"))
    return _mise_en_page(fig, p, titre, sombre)


def carte_densite(pts: pd.DataFrame, p: dict, sombre: bool, titre: str, rayon: int = 18) -> go.Figure:
    """Carte de chaleur des cas (concentration spatiale)."""
    fig = go.Figure(go.Densitymap(lat=pts["lat"], lon=pts["lon"], radius=rayon, opacity=0.75,
                                  colorscale=[[0, "rgba(255,255,255,0)"], [0.25, p["warn"]], [1, p["bad"]]],
                                  showscale=False, hoverinfo="skip"))
    return _mise_en_page(fig, p, titre, sombre)


def carte_aires(agg: pd.DataFrame, p: dict, sombre: bool, titre: str) -> go.Figure:
    """Une bulle par aire de santé : taille = fiches, couleur = prévalence (aucune position de ménage)."""
    taille = 12 + 30 * np.sqrt(agg["n"] / max(agg["n"].max(), 1))
    fig = go.Figure(go.Scattermap(
        lat=agg["lat"], lon=agg["lon"], mode="markers+text", text=agg["aire"], textposition="top center",
        textfont=dict(size=12, color=p["text"]),
        marker=dict(size=taille, color=agg["prevalence"] * 100, colorscale=[[0, p["ordinal"][2]], [1, p["bad"]]],
                    cmin=0, cmax=max(float(agg["prevalence"].max() * 100), 1), opacity=0.85,
                    colorbar=dict(title=dict(text="Prévalence (%)", font=dict(color=p["text2"])), tickfont=dict(color=p["text2"]),
                                  thickness=12, len=0.6)),
        customdata=np.stack([agg["n"], agg["cas"], agg["prevalence"] * 100], axis=-1),
        hovertemplate="<b>%{text}</b><br>Fiches : %{customdata[0]:.0f}<br>Cas : %{customdata[1]:.0f}"
                      "<br>Prévalence : %{customdata[2]:.1f} %<extra></extra>"))
    return _mise_en_page(fig, p, titre, sombre)


def demo_gps(aire: str, rng) -> str:
    """Point FICTIF autour du centre de l'aire (mode démonstration)."""
    if rng.random() < 0.01:  # quelques points aberrants pour illustrer le contrôle qualité
        return f"{-4.31 + rng.gauss(0, 0.01):.6f} {15.28 + rng.gauss(0, 0.01):.6f} 300 5" if rng.random() < .5 else "-4.325 15.50 300 5"
    lat, lon = CENTRES_DEMO.get(aire, (CENTRE["lat"], CENTRE["lon"]))
    return f"{lat + rng.gauss(0, 0.004):.6f} {lon + rng.gauss(0, 0.004):.6f} {rng.randint(270, 330)} {rng.choice([3, 4, 4, 5, 5, 6, 6, 8, 10, 12, 15, 20, 30, 65])}"
