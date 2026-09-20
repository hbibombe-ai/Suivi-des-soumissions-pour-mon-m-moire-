"""État nutritionnel : z-scores selon les normes de croissance de l'OMS (2006).

Méthode LMS de l'OMS (avec la correction au-delà de ±3 z pour les indices fondés sur le poids),
tables mensuelles (âge) et par pas de 0,5 cm (longueur/taille) fournies dans who_lms.csv,
interpolation linéaire entre deux points. Les résultats sont très proches de ceux de WHO Anthro
(écart habituel ≤ 0,05 z) ; pour les chiffres définitifs du mémoire, WHO Anthro reste la référence.
"""
from __future__ import annotations

VERSION_TDB = "5"  # doit correspondre à app.py
import math
import os
from functools import lru_cache

import numpy as np
import pandas as pd

ICI = os.path.dirname(os.path.abspath(__file__))
FICHIER_LMS = os.path.join(ICI, "who_lms.csv")

# Valeurs biologiquement invraisemblables (critères OMS)
BORNES = {"whz": (-5, 5), "haz": (-6, 6), "waz": (-6, 5)}


@lru_cache(maxsize=1)
def _tables() -> dict:
    t = pd.read_csv(FICHIER_LMS)
    return {(ind, int(sx)): g.sort_values("x")[["x", "L", "M", "S"]].to_numpy()
            for (ind, sx), g in t.groupby(["indicateur", "sexe"])}


def _lms(ind: str, sexe: int, x: float):
    tab = _tables().get((ind, int(sexe)))
    if tab is None or not (tab[0, 0] <= x <= tab[-1, 0]):
        return None
    return tuple(np.interp(x, tab[:, 0], tab[:, c]) for c in (1, 2, 3))


def _z(y: float, L: float, M: float, S: float, poids: bool) -> float:
    z = ((y / M) ** L - 1) / (L * S) if L != 0 else math.log(y / M) / S
    if poids and abs(z) > 3:  # correction OMS pour les queues de distribution
        sd = lambda k: M * (1 + L * S * k) ** (1 / L)
        if z > 3:
            z = 3 + (y - sd(3)) / (sd(3) - sd(2))
        else:
            z = -3 + (y - sd(-3)) / (sd(-2) - sd(-3))
    return z


def zscores(sexe, age_mois, poids, taille, position) -> dict:
    """sexe 1=M 2=F ; age en mois (décimal) ; poids kg ; taille cm ; position 1=couché 2=debout."""
    res = {"waz": np.nan, "haz": np.nan, "whz": np.nan}
    try:
        sexe, age = int(sexe), float(age_mois)
    except (TypeError, ValueError):
        return res
    if not (0 <= age < 61) or sexe not in (1, 2):
        return res
    # taille corrigée selon la position recommandée pour l'âge
    t = None
    if taille == taille and taille is not None:
        t = float(taille)
        if position == position and position is not None:
            if age < 24 and int(position) == 2:
                t += 0.7
            elif age >= 24 and int(position) == 1:
                t -= 0.7
    if poids == poids and poids is not None:
        lms = _lms("wfa", sexe, age)
        if lms: res["waz"] = _z(float(poids), *lms, poids=True)
    if t is not None:
        lms = _lms("lhfa_l" if age < 24 else "lhfa_h", sexe, age)
        if lms: res["haz"] = _z(t, *lms, poids=False)
        if poids == poids and poids is not None:
            lms = _lms("wfl" if age < 24 else "wfh", sexe, t)
            if lms: res["whz"] = _z(float(poids), *lms, poids=True)
    for k, (lo, hi) in BORNES.items():
        if res[k] == res[k] and not (lo <= res[k] <= hi):
            res[k] = np.nan  # valeur exclue (invraisemblable)
    return res


def classe_z(z) -> str:
    if z != z:
        return "Non mesuré / exclu"
    return "Sévère (< −3)" if z < -3 else ("Modéré (−3 à < −2)" if z < -2 else "Normal (≥ −2)")


def classe_pb(pb, oedemes=None) -> str:
    if oedemes == 1:
        return "MAS (œdèmes)"
    if pb != pb or pb is None:
        return "Non mesuré"
    return "MAS (< 115 mm)" if pb < 115 else ("MAM (115–124 mm)" if pb < 125 else "Normal (≥ 125 mm)")
