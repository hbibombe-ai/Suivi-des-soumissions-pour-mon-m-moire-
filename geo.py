"""Géolocalisation des ménages : lecture du champ GPS (A7), contrôle qualité, floutage et cartes.

Le champ `a7_gps` (geopoint) arrive de KoboToolbox sous la forme « latitude longitude altitude précision ».
KoboToolbox fournit aussi `_geolocation` = [latitude, longitude], utilisé en secours.

Carte sanitaire : si le fichier `carte_sanitaire/aires_limete.geojson` (limites des 11 aires de santé de la
ZS de Limete, produit par `carte_sanitaire/preparer_carte_sanitaire.R`) est présent, il sert :
  - de fond à toutes les cartes (limites et noms des aires) ;
  - à la carte de prévalence par aire (aires coloriées) ;
  - au contrôle qualité : point hors de la ZS, aire du GPS différente de l'aire déclarée (A4).
Sans ce fichier, le tableau de bord fonctionne comme avant (emprise rectangulaire, bulles par aire).
"""
from __future__ import annotations

VERSION_TDB = "9"  # doit correspondre à app.py
import functools
import hashlib
import json
import math
import os
import unicodedata

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# Emprise de contrôle utilisée SANS carte sanitaire : commune de Limete et ses abords (large marge).
EMPRISE = dict(lat_min=-4.45, lat_max=-4.28, lon_min=15.24, lon_max=15.42)
CENTRE = dict(lat=-4.372, lon=15.335)
PRECISION_MAX_M = 50  # au-delà, le point est jugé imprécis

# Carte sanitaire
FICHIER_AIRES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "carte_sanitaire", "aires_limete.geojson")
TOLERANCE_M = 100  # un point à moins de 100 m de la limite de la ZS n'est pas compté « hors zone » (imprécision GPS)
AIRE_HORS = "Hors ZS"

# Positions FICTIVES servant uniquement au mode démonstration sans carte (≈ centre de chaque aire).
CENTRES_DEMO = {
    "agricole": (-4.392, 15.318), "industriel_1": (-4.352, 15.335), "industriel_2": (-4.345, 15.350),
    "industriel_3": (-4.338, 15.322), "masiala": (-4.380, 15.345), "mateba": (-4.368, 15.312),
    "mayulu": (-4.385, 15.330), "mfumu": (-4.375, 15.358), "mombele": (-4.360, 15.365),
    "mososo": (-4.358, 15.300), "residentiel": (-4.370, 15.328),
}

# Noms officiels (DSNIS/GRID3) -> noms du formulaire, comparés sans accents ni espaces
ALIAS = {"industrielle1": "industriel1", "industrielle2": "industriel2", "industrielle3": "industriel3",
         "mfumumvula": "mfumu", "residentielle": "residentiel"}


def cle_aire(texte) -> str:
    """'Industrielle 1', 'industriel_1', 'Industriel 1' -> 'industriel1' (clé de jointure)."""
    if texte is None or (isinstance(texte, float) and math.isnan(texte)):
        return ""
    t = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode().lower()
    t = "".join(ch for ch in t if ch.isalnum())
    return ALIAS.get(t, t)


# --------------------------------------------------------------------- carte sanitaire
def _anneaux(geom: dict) -> list[list[np.ndarray]]:
    """GeoJSON Polygon / MultiPolygon -> liste de polygones, chacun = [contour extérieur, trous…]."""
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return []
    return [[np.asarray(r, dtype=float)[:, :2] for r in poly] for poly in polys]


def _dans_anneau(x: np.ndarray, y: np.ndarray, r: np.ndarray) -> np.ndarray:
    """Test du rayon (ray casting), vectorisé : points (x, y) dans l'anneau r ?"""
    if not np.allclose(r[0], r[-1]):
        r = np.vstack([r, r[:1]])
    x1, y1, x2, y2 = r[:-1, 0], r[:-1, 1], r[1:, 0], r[1:, 1]
    X, Y = x[:, None], y[:, None]
    traverse = (y1 > Y) != (y2 > Y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xi = x1 + (Y - y1) * (x2 - x1) / (y2 - y1)
    return (traverse & (X < xi)).sum(axis=1) % 2 == 1


def _dans_polygones(x, y, polys) -> np.ndarray:
    dedans = np.zeros(len(x), dtype=bool)
    for poly in polys:
        d = _dans_anneau(x, y, poly[0])
        for trou in poly[1:]:
            d &= ~_dans_anneau(x, y, trou)
        dedans |= d
    return dedans


def _distance_m(x, y, polys) -> np.ndarray:
    """Distance (m) de chaque point au contour le plus proche (projection locale, suffisante à cette échelle)."""
    kx, ky = 111_320 * math.cos(math.radians(CENTRE["lat"])), 110_574
    segs = np.vstack([np.hstack([r[:-1], r[1:]]) for poly in polys for r in poly])
    ax, ay, bx, by = segs[:, 0] * kx, segs[:, 1] * ky, segs[:, 2] * kx, segs[:, 3] * ky
    px, py = (x * kx)[:, None], (y * ky)[:, None]
    dx, dy = bx - ax, by - ay
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy), 0, 1)
    t = np.nan_to_num(t)
    return np.sqrt((ax + t * dx - px) ** 2 + (ay + t * dy - py) ** 2).min(axis=1)


def _point_etiquette(polys) -> tuple[float, float]:
    """Point intérieur pour placer le nom de l'aire (centroïde, sinon point de grille le plus central)."""
    ext = max((p[0] for p in polys), key=lambda r: abs(_aire_signee(r)))
    a = _aire_signee(ext)
    x, y = ext[:, 0], ext[:, 1]
    c = x[:-1] * y[1:] - x[1:] * y[:-1]
    cx, cy = ((x[:-1] + x[1:]) * c).sum() / (6 * a), ((y[:-1] + y[1:]) * c).sum() / (6 * a)
    if _dans_polygones(np.array([cx]), np.array([cy]), polys)[0]:
        return float(cx), float(cy)
    gx, gy = np.meshgrid(np.linspace(x.min(), x.max(), 25), np.linspace(y.min(), y.max(), 25))
    gx, gy = gx.ravel(), gy.ravel()
    ok = _dans_polygones(gx, gy, polys)
    if not ok.any():
        return float(x.mean()), float(y.mean())
    gx, gy = gx[ok], gy[ok]
    i = int(np.argmax(_distance_m(gx, gy, polys)))
    return float(gx[i]), float(gy[i])


def _aire_signee(r: np.ndarray) -> float:
    x, y = r[:, 0], r[:, 1]
    return 0.5 * float((x[:-1] * y[1:] - x[1:] * y[:-1]).sum())


@functools.lru_cache(maxsize=1)
def carte_sanitaire() -> dict | None:
    """Charge les limites des aires de santé (None si le fichier est absent ou illisible)."""
    if not os.path.exists(FICHIER_AIRES):
        return None
    try:
        with open(FICHIER_AIRES, encoding="utf-8") as f:
            gj = json.load(f)
        aires = []
        for feat in gj["features"]:
            polys = _anneaux(feat["geometry"])
            if not polys:
                continue
            nom = feat["properties"].get("aire") or feat["properties"].get("nom_officiel") or "?"
            feat["properties"]["cle"] = cle_aire(nom)
            feat["properties"]["aire"] = nom
            lon_e, lat_e = _point_etiquette(polys)
            tous = np.vstack([r for p_ in polys for r in p_])
            aires.append(dict(cle=cle_aire(nom), aire=nom, polys=polys, lon_etiq=lon_e, lat_etiq=lat_e,
                              bbox=(tous[:, 0].min(), tous[:, 1].min(), tous[:, 0].max(), tous[:, 1].max())))
        if not aires:
            return None
        b = np.array([a["bbox"] for a in aires])
        bbox = (b[:, 0].min(), b[:, 1].min(), b[:, 2].max(), b[:, 3].max())
        return dict(geojson=gj, aires=aires, bbox=bbox,
                    centre=dict(lon=(bbox[0] + bbox[2]) / 2, lat=(bbox[1] + bbox[3]) / 2))
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None


def mode_controle() -> str:
    return "carte" if carte_sanitaire() else "emprise"


def localiser(lon, lat) -> pd.Series:
    """Nom de l'aire de santé contenant chaque point (AIRE_HORS au-delà de la tolérance)."""
    carte = carte_sanitaire()
    lon, lat = np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)
    res = np.full(len(lon), None, dtype=object)
    if carte is None or len(lon) == 0:
        return pd.Series(res)
    ok = ~(np.isnan(lon) | np.isnan(lat))
    for a in carte["aires"]:
        d = ok & (res == None) & _dans_polygones(np.nan_to_num(lon), np.nan_to_num(lat), a["polys"])  # noqa: E711
        res[d] = a["aire"]
    reste = ok & (res == None)  # noqa: E711
    if reste.any():  # hors de toutes les aires : aire la plus proche si à moins de TOLERANCE_M
        idx = np.where(reste)[0]
        dist = np.vstack([_distance_m(lon[idx], lat[idx], a["polys"]) for a in carte["aires"]])
        j = dist.argmin(axis=0)
        proche = dist.min(axis=0) <= TOLERANCE_M
        res[idx] = np.where(proche, [carte["aires"][k]["aire"] for k in j], AIRE_HORS)
    return pd.Series(res)


# --------------------------------------------------------------------- GPS
def _nombre(x) -> float:
    """Valeur numérique, ou NaN si vide, None, texte ou valeur invalide."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return np.nan
    return v if math.isfinite(v) else np.nan


def _lire(valeur):
    """'−4.37 15.33 280 5', [−4.37, 15.33] ou [None, None] → (lat, lon, alt, précision) ; NaN si absent."""
    try:
        if valeur is None or (isinstance(valeur, float) and math.isnan(valeur)):
            return (np.nan,) * 4
        if isinstance(valeur, (list, tuple, np.ndarray)):
            parts = list(valeur)
        elif isinstance(valeur, dict):  # certains exports : {"latitude": …, "longitude": …}
            parts = [valeur.get("latitude"), valeur.get("longitude"), valeur.get("altitude"), valeur.get("accuracy")]
        else:
            parts = str(valeur).replace(",", " ").split()
        nums = [_nombre(x) for x in parts[:4]]
    except Exception:  # valeur inattendue : on la traite comme un GPS manquant plutôt que de bloquer l'application
        return (np.nan,) * 4
    nums += [np.nan] * (4 - len(nums))
    return tuple(nums[:4])


def ajouter_gps(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute lat, lon, gps_precision_m, gps_statut et, avec la carte sanitaire, aire_gps et aire_coherente."""
    brut = df["a7_gps"] if "a7_gps" in df.columns else pd.Series(np.nan, index=df.index)
    vals = pd.DataFrame([_lire(v) for v in brut], index=df.index, columns=["lat", "lon", "gps_altitude", "gps_precision_m"])
    if "_geolocation" in df.columns:  # secours : coordonnées extraites par KoboToolbox
        secours = pd.DataFrame([_lire(v) for v in df["_geolocation"]], index=df.index,
                               columns=["lat", "lon", "alt", "prec"])[["lat", "lon"]].rename(columns={"lat": 0, "lon": 1})
        vals["lat"] = vals["lat"].fillna(secours[0])
        vals["lon"] = vals["lon"].fillna(secours[1])
    for c in vals.columns:
        df[c] = vals[c]
    manquant = df["lat"].isna() | df["lon"].isna() | ((df["lat"] == 0) & (df["lon"] == 0))
    df.loc[manquant, ["lat", "lon"]] = np.nan

    if carte_sanitaire() is not None:
        df["aire_gps"] = localiser(df["lon"], df["lat"]).values
        hors = ~manquant & (df["aire_gps"] == AIRE_HORS)
        if "aire_sante" in df.columns:
            declaree = df["aire_sante"].map(cle_aire)
            gps = df["aire_gps"].map(cle_aire)
            comparable = ~manquant & ~hors & (declaree != "")
            df["aire_coherente"] = np.where(comparable, declaree == gps, np.nan)
    else:
        hors = ~manquant & ~(df["lat"].between(EMPRISE["lat_min"], EMPRISE["lat_max"])
                             & df["lon"].between(EMPRISE["lon_min"], EMPRISE["lon_max"]))
    imprecis = ~manquant & ~hors & (df["gps_precision_m"] > PRECISION_MAX_M)
    df["gps_statut"] = np.select([manquant, hors, imprecis], ["Manquant", "Hors zone", f"Imprécis (> {PRECISION_MAX_M} m)"], "Valide")
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


# --------------------------------------------------------------------- cartes
def _fond(sombre: bool) -> str:
    return "carto-darkmatter" if sombre else "open-street-map"


def _contours(fig: go.Figure, p: dict, etiquettes: bool = True) -> list:
    """Limites des aires (couche de la carte) et noms des aires (texte). Renvoie les couches à ajouter."""
    carte = carte_sanitaire()
    if carte is None:
        return []
    if etiquettes:
        fig.add_trace(go.Scattermap(
            lon=[a["lon_etiq"] for a in carte["aires"]], lat=[a["lat_etiq"] for a in carte["aires"]],
            mode="text", text=[a["aire"] for a in carte["aires"]], textfont=dict(size=12, color=p["text"]),
            hoverinfo="skip", showlegend=False, name="Aires de santé"))
    return [dict(sourcetype="geojson", source=carte["geojson"], type="line", color=p["text2"],
                 line=dict(width=1.8), below="traces")]


def _mise_en_page(fig: go.Figure, p: dict, titre: str, sombre: bool, zoom: float = 12.6, hauteur: int = 560,
                  couches: list | None = None):
    carte = carte_sanitaire()
    centre = carte["centre"] if carte else CENTRE
    fig.update_layout(
        map=dict(style=_fond(sombre), center=centre, zoom=zoom, layers=couches or []),
        height=hauteur, margin=dict(l=0, r=0, t=40, b=0), paper_bgcolor="rgba(0,0,0,0)",
        title=dict(text=titre, x=0, font=dict(size=15, color=p["text"])),
        legend=dict(orientation="h", y=-0.02, x=0, bgcolor="rgba(0,0,0,0)", font=dict(color=p["text2"])),
        font=dict(family="Inter, Segoe UI, Arial, sans-serif", color=p["text2"]),
    )
    return fig


def carte_points(pts: pd.DataFrame, couleur: str, libelle_couleur: str, p: dict, sombre: bool,
                 infobulle: list[tuple[str, str]], titre: str, ordre: list | None = None,
                 couleurs_fixes: dict | None = None) -> go.Figure:
    """Un point par ménage, coloré selon `couleur` (colonne catégorielle), sur les limites des aires."""
    fig = go.Figure()
    couches = _contours(fig, p)
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
    return _mise_en_page(fig, p, titre, sombre, couches=couches)


def carte_densite(pts: pd.DataFrame, p: dict, sombre: bool, titre: str, rayon: int = 18) -> go.Figure:
    """Carte de chaleur des cas (concentration spatiale)."""
    fig = go.Figure(go.Densitymap(lat=pts["lat"], lon=pts["lon"], radius=rayon, opacity=0.75,
                                  colorscale=[[0, "rgba(255,255,255,0)"], [0.25, p["warn"]], [1, p["bad"]]],
                                  showscale=False, hoverinfo="skip"))
    couches = _contours(fig, p)
    return _mise_en_page(fig, p, titre, sombre, couches=couches)


def carte_aires(agg: pd.DataFrame, p: dict, sombre: bool, titre: str) -> go.Figure:
    """Sans carte sanitaire : une bulle par aire de santé (taille = fiches, couleur = prévalence)."""
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


def carte_aires_polygones(agg: pd.DataFrame, p: dict, sombre: bool, titre: str) -> go.Figure:
    """Avec carte sanitaire : chaque aire coloriée selon la prévalence (carte choroplèthe).

    `agg` : colonnes aire, n, cas, prevalence, ic_bas, ic_haut (proportions 0-1).
    """
    carte = carte_sanitaire()
    agg = agg.copy()
    agg["cle"] = agg["aire"].map(cle_aire)
    vmax = max(float(agg["prevalence"].max() * 100), 1) if len(agg) else 1
    fig = go.Figure(go.Choroplethmap(
        geojson=carte["geojson"], featureidkey="properties.cle", locations=agg["cle"], z=agg["prevalence"] * 100,
        zmin=0, zmax=vmax, colorscale=[[0, "#fde0d2"], [0.5, "#f08a5d"], [1, p["bad"]]],
        marker=dict(opacity=0.78, line=dict(width=1.2, color=p["surface"])),
        colorbar=dict(title=dict(text="Prévalence (%)", font=dict(color=p["text2"])), tickfont=dict(color=p["text2"]),
                      thickness=12, len=0.6),
        text=agg["aire"],
        customdata=np.stack([agg["n"], agg["cas"], agg["prevalence"] * 100, agg["ic_bas"] * 100, agg["ic_haut"] * 100], axis=-1),
        hovertemplate="<b>%{text}</b><br>Enfants enquêtés : %{customdata[0]:.0f}<br>Cas : %{customdata[1]:.0f}"
                      "<br>Prévalence : %{customdata[2]:.1f} % (IC 95 % : %{customdata[3]:.1f} – %{customdata[4]:.1f})"
                      "<extra></extra>"))
    # Noms des aires et prévalence en étiquette
    prev = dict(zip(agg["cle"], agg["prevalence"]))
    etiq = [f"{a['aire']}<br>{prev[a['cle']] * 100:.1f} %".replace(".", ",") if a["cle"] in prev else f"{a['aire']}<br>n.d."
            for a in carte["aires"]]
    fig.add_trace(go.Scattermap(lon=[a["lon_etiq"] for a in carte["aires"]], lat=[a["lat_etiq"] for a in carte["aires"]],
                                mode="text", text=etiq, textfont=dict(size=12, color="#1a1a1a"),
                                hoverinfo="skip", showlegend=False))
    couches = _contours(go.Figure(), p, etiquettes=False)  # limites, y compris les aires sans données
    return _mise_en_page(fig, p, titre, sombre, couches=couches)


# --------------------------------------------------------------------- démonstration
def demo_gps(aire: str, rng) -> str:
    """Point FICTIF dans l'aire (dans son polygone si la carte sanitaire est présente)."""
    if rng.random() < 0.01:  # quelques points aberrants pour illustrer le contrôle qualité
        return f"{-4.31 + rng.gauss(0, 0.01):.6f} {15.28 + rng.gauss(0, 0.01):.6f} 300 5" if rng.random() < .5 else "-4.325 15.50 300 5"
    precision = rng.choice([3, 4, 4, 5, 5, 6, 6, 8, 10, 12, 15, 20, 30, 65])
    carte = carte_sanitaire()
    if carte and rng.random() < 0.03:  # quelques ménages dans une autre aire que celle déclarée
        aire = rng.choice([a["aire"] for a in carte["aires"]])
    cible = next((a for a in carte["aires"] if a["cle"] == cle_aire(aire)), None) if carte else None
    if cible is not None:
        x0, y0, x1, y1 = cible["bbox"]
        for _ in range(200):
            lon, lat = rng.uniform(x0, x1), rng.uniform(y0, y1)
            if _dans_polygones(np.array([lon]), np.array([lat]), cible["polys"])[0]:
                return f"{lat:.6f} {lon:.6f} {rng.randint(270, 330)} {precision}"
    lat, lon = CENTRES_DEMO.get(aire, (CENTRE["lat"], CENTRE["lon"]))
    return f"{lat + rng.gauss(0, 0.004):.6f} {lon + rng.gauss(0, 0.004):.6f} {rng.randint(270, 330)} {precision}"
