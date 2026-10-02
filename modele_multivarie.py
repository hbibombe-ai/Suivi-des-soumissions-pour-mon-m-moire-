"""Garde-fou EPV et régression logistique pénalisée de Firth pour le Tableau 22.

- EPV (événements par variable) : le modèle multivarié n'est affiché que lorsque le
  nombre de cas (issue la plus rare) atteint 10 par variable (règle stricte) ou
  5 par variable (règle assouplie). Sous le seuil : cas disponibles / nécessaires,
  projection en fin de collecte et date estimée selon le rythme de collecte.
- Firth : utilisée automatiquement quand le modèle classique ne converge pas ou qu'une
  exposition sépare parfaitement les cas. IC 95 % et p par vraisemblance pénalisée
  profilée (même méthode que logistf en R). Implémentation numpy, sans dépendance
  supplémentaire (firthlogist ne s'installe pas sur Python >= 3.11).
"""
from __future__ import annotations

VERSION_TDB = "8"  # doit correspondre à app.py
import datetime as dt
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

import viz

CIBLE_MENAGES = 427           # taille d'échantillon prévue
CHI2_95_DF1 = 3.841458820694124


# ================================================================== garde-fou EPV
@dataclass
class EtatEPV:
    n: int
    cas: int
    evenements: int              # issue la plus rare : min(cas, non-cas)
    issue_rare: str
    k: int                       # nombre de variables dans le modèle
    seuil: int                   # 10 (stricte) ou 5 (assouplie)
    necessaires: int
    epv: float
    atteint: bool
    cible: int = CIBLE_MENAGES
    proj: float = float("nan")   # événements attendus à la cible
    proj_bas: float = float("nan")
    proj_haut: float = float("nan")
    k_max_fin: int = 0
    fiches_necessaires: float = float("nan")
    rythme_jour: float = float("nan")
    date_estimee: Optional[dt.date] = None


def calculer_epv(y: pd.Series, k: int, seuil: int = 10, cible: int = CIBLE_MENAGES,
                 dates: Optional[pd.Series] = None) -> EtatEPV:
    y = pd.Series(y).dropna().astype(int)
    n, cas = len(y), int(y.sum())
    ev = min(cas, n - cas)
    nec = seuil * max(k, 1)
    e = EtatEPV(n=n, cas=cas, evenements=ev, issue_rare="cas" if cas <= n - cas else "non-cas",
                k=k, seuil=seuil, necessaires=nec, epv=ev / k if k else float("inf"),
                atteint=k > 0 and ev >= nec, cible=cible)
    if n:
        p = ev / n
        _, bas, haut = viz.wilson(ev, n)
        e.proj, e.proj_bas, e.proj_haut = p * cible, bas * cible, haut * cible
        e.k_max_fin = int(e.proj // seuil)
        if p > 0:
            e.fiches_necessaires = math.ceil(nec / p)
    if dates is not None:
        d = pd.to_datetime(pd.Series(dates), errors="coerce").dropna()
        if len(d):
            jours = (d.max().normalize() - d.min().normalize()).days + 1
            e.rythme_jour = len(d) / max(jours, 1)
            if np.isfinite(e.fiches_necessaires) and e.rythme_jour > 0:
                e.date_estimee = dt.date.today() + dt.timedelta(
                    days=math.ceil(max(0, e.fiches_necessaires - n) / e.rythme_jour))
    return e


def message_seuil(e: EtatEPV) -> str:
    msg = (f"**Modèle non affiché** : {e.evenements} cas pour {e.k} variable(s), il en faut "
           f"{e.necessaires} ({e.seuil} par variable). Il manque {e.necessaires - e.evenements} cas.")
    if np.isfinite(e.fiches_necessaires):
        msg += f"\n\nÀ la prévalence actuelle, ce seuil sera atteint vers **{int(e.fiches_necessaires)} fiches**"
        if e.fiches_necessaires > e.cible:
            msg += f", au-delà des {e.cible} ménages prévus : réduire le nombre de variables."
        else:
            msg += "."
            if e.date_estimee:
                msg += (f" Au rythme actuel ({viz.fr(e.rythme_jour, 1)} fiches/jour), date estimée : "
                        f"**{e.date_estimee:%d/%m/%Y}**.")
    if np.isfinite(e.proj):
        msg += (f"\n\nEn fin de collecte ({e.cible} ménages), on peut attendre environ {viz.fr(e.proj, 0)} cas "
                f"(fourchette {viz.fr(e.proj_bas, 0)} à {viz.fr(e.proj_haut, 0)}), soit au plus "
                f"**{e.k_max_fin} variable(s)** dans le modèle avec cette règle.")
    if e.n < 200:
        msg += "\n\n_Projection encore instable (moins de 200 fiches) : à revoir au fil de la collecte._"
    return msg


def afficher_garde_fou(e: EtatEPV) -> None:
    import streamlit as st
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cas disponibles", e.evenements, help=f"Issue la plus rare ({e.issue_rare}).")
    c2.metric("Cas nécessaires", e.necessaires, help=f"{e.seuil} cas × {e.k} variable(s).")
    c3.metric("EPV actuel", viz.fr(e.epv, 1) if np.isfinite(e.epv) else "—",
              help="Événements par variable : cas disponibles / nombre de variables du modèle.")
    c4.metric(f"Cas attendus à {e.cible} ménages", viz.fr(e.proj, 0) if np.isfinite(e.proj) else "—",
              help=(f"Fourchette d'après l'IC 95 % de la prévalence actuelle : {viz.fr(e.proj_bas, 0)} à "
                    f"{viz.fr(e.proj_haut, 0)} cas." if np.isfinite(e.proj) else None))
    st.progress(min(1.0, e.evenements / max(e.necessaires, 1)),
                text=f"{e.evenements} / {e.necessaires} cas nécessaires")
    if not e.atteint:
        st.warning(message_seuil(e))


# ============================================================ régression de Firth
def _expit(eta):
    return 1.0 / (1.0 + np.exp(-np.clip(eta, -35, 35)))


def _loglik_pen(X, y, beta):
    p = np.clip(_expit(X @ beta), 1e-15, 1 - 1e-15)
    w = p * (1 - p)
    signe, logdet = np.linalg.slogdet(X.T @ (X * w[:, None]))
    return float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p))) + (0.5 * logdet if signe > 0 else -np.inf)


def _ajuster_firth(X, y, fixe=None, beta0=None, max_iter=200, tol=1e-8, pas_max=5.0):
    """Newton-Raphson sur la vraisemblance pénalisée (Firth). `fixe` = (indice, valeur)
    pour la vraisemblance profilée. Renvoie (beta, log-vraisemblance pénalisée, convergé)."""
    k = X.shape[1]
    beta = np.zeros(k) if beta0 is None else np.asarray(beta0, float).copy()
    libres = np.arange(k)
    if fixe is not None:
        beta[fixe[0]] = fixe[1]
        libres = np.array([i for i in range(k) if i != fixe[0]])
    ll = _loglik_pen(X, y, beta)
    for _ in range(max_iter):
        p = _expit(X @ beta)
        w = p * (1 - p)
        info = X.T @ (X * w[:, None])
        info_inv = np.linalg.pinv(info)
        h = w * np.einsum("ij,jk,ik->i", X, info_inv, X)
        score = X.T @ (y - p + h * (0.5 - p))
        sous = info[np.ix_(libres, libres)]
        d_l = np.linalg.lstsq(sous, score[libres], rcond=None)[0]
        m = np.max(np.abs(d_l)) if d_l.size else 0.0
        if m > pas_max:
            d_l *= pas_max / m
        delta = np.zeros(k)
        delta[libres] = d_l
        pas = 1.0
        for _ in range(30):  # demi-pas tant que la vraisemblance pénalisée diminue
            nb = beta + pas * delta
            nll = _loglik_pen(X, y, nb)
            if nll >= ll - 1e-10:
                break
            pas /= 2
        beta, ll = nb, nll
        if np.max(np.abs(pas * delta)) < tol and (not libres.size or np.max(np.abs(score[libres])) < 1e-6):
            return beta, ll, True
    return beta, ll, False


def _ic_profil(X, y, beta, ll_max, j, borne=30.0):
    def ecart(b):
        return 2 * (ll_max - _ajuster_firth(X, y, fixe=(j, b), beta0=beta)[1]) - CHI2_95_DF1

    bornes = []
    for sens in (-1, 1):
        a, b = beta[j], beta[j] + sens
        while ecart(b) < 0:
            a, b = b, b + sens
            if abs(b - beta[j]) > borne:
                b = None
                break
        if b is None:
            bornes.append(sens * np.inf)
            continue
        for _ in range(50):  # dichotomie
            m = (a + b) / 2
            a, b = (m, b) if ecart(m) < 0 else (a, m)
            if abs(b - a) < 1e-5:
                break
        bornes.append((a + b) / 2)
    return bornes


def firth(X: pd.DataFrame, y: pd.Series) -> dict:
    """Régression logistique de Firth. Renvoie coefficients, IC 95 % et p (vraisemblance
    pénalisée profilée) par variable, probabilités prédites et convergence."""
    M = np.column_stack([np.ones(len(X)), X.to_numpy(float)])
    yv = np.asarray(y, float)
    beta, ll, ok = _ajuster_firth(M, yv)
    res = {"converge": ok, "proba": _expit(M @ beta), "params": {}, "ic": {}, "p": {}}
    for i, nom in enumerate(X.columns, start=1):
        res["params"][nom] = beta[i]
        res["ic"][nom] = _ic_profil(M, yv, beta, ll, i)
        ll0 = _ajuster_firth(M, yv, fixe=(i, 0.0), beta0=beta)[1]
        res["p"][nom] = math.erfc(math.sqrt(max(2 * (ll - ll0), 0.0) / 2))
    return res
