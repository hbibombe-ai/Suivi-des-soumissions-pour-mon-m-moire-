"""Connexion à KoboToolbox, dictionnaire de variables et préparation des données.

Le tableau de bord lit les soumissions en direct via l'API REST de KoboToolbox
(https://<serveur>/api/v2/assets/<asset_uid>/data.json) et traduit les codes en
libellés à partir du XLSForm déposé dans le dépôt.
"""
from __future__ import annotations
import datetime as dt
import random
from typing import Dict, List

import pandas as pd
import requests

SERVEURS = {
    "Europe (eu.kobotoolbox.org)": "https://eu.kobotoolbox.org",
    "Global (kf.kobotoolbox.org)": "https://kf.kobotoolbox.org",
    "OCHA (kobo.humanitarianresponse.info)": "https://kobo.humanitarianresponse.info",
}
XLSFORM = "KoboCollect_XLSForm_Diarrhee_Limete_2026_V3.xlsx"
TIMEOUT = 60


# --------------------------------------------------------------------------- API
def recuperer_soumissions(serveur: str, token: str, asset_uid: str, taille_page: int = 2000) -> pd.DataFrame:
    """Télécharge toutes les soumissions (pagination incluse) et renvoie un DataFrame brut."""
    url = f"{serveur.rstrip('/')}/api/v2/assets/{asset_uid}/data.json"
    entetes = {"Authorization": f"Token {token}", "Accept": "application/json"}
    lignes: List[dict] = []
    depart = 0
    while True:
        r = requests.get(url, headers=entetes, params={"limit": taille_page, "start": depart}, timeout=TIMEOUT)
        if r.status_code == 401:
            raise PermissionError("Jeton d'API refusé (401). Vérifier le token et le serveur.")
        if r.status_code == 404:
            raise FileNotFoundError("Projet introuvable (404). Vérifier l'identifiant du formulaire (asset UID).")
        r.raise_for_status()
        paquet = r.json().get("results", [])
        lignes.extend(paquet)
        if len(paquet) < taille_page:
            break
        depart += taille_page
    return pd.DataFrame(lignes)


def tester_connexion(serveur: str, token: str, asset_uid: str) -> dict:
    """Renvoie les métadonnées du projet (nom, nombre de soumissions, date de déploiement)."""
    url = f"{serveur.rstrip('/')}/api/v2/assets/{asset_uid}.json"
    r = requests.get(url, headers={"Authorization": f"Token {token}"}, timeout=TIMEOUT)
    r.raise_for_status()
    a = r.json()
    return {
        "nom": a.get("name", "—"),
        "soumissions": a.get("deployment__submission_count", 0),
        "deploye": a.get("date_deployed") or a.get("date_modified"),
    }


# ------------------------------------------------------------------- dictionnaire
def charger_dictionnaire(chemin_xlsform: str = XLSFORM) -> Dict[str, dict]:
    """Construit {variable: {'label':…, 'choix': {code: libellé}}} à partir du XLSForm."""
    try:
        survey = pd.read_excel(chemin_xlsform, sheet_name="survey", dtype=str).fillna("")
        choices = pd.read_excel(chemin_xlsform, sheet_name="choices", dtype=str).fillna("")
    except Exception:
        return {}
    listes: Dict[str, Dict[str, str]] = {}
    for _, c in choices.iterrows():
        listes.setdefault(c["list_name"], {})[str(c["name"])] = c["label"]
    dico: Dict[str, dict] = {}
    for _, q in survey.iterrows():
        t = q["type"].split()
        if not q["name"] or t[0] in ("begin_group", "end_group"):
            continue
        dico[q["name"]] = {
            "label": q.get("label", "") or q["name"],
            "type": t[0],
            "choix": listes.get(t[1], {}) if len(t) > 1 else {},
        }
    return dico


def _code(v):
    """Normalise un code : 2.0 → '2', 'mfumu' → 'mfumu'."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return v
    if isinstance(v, float) and float(v).is_integer():
        return str(int(v))
    return str(v)


def libelle(dico: Dict[str, dict], var: str, valeur) -> str:
    """Traduit un code en libellé lisible (ex. a3 = 'agricole' → 'Agricole')."""
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return "Non renseigné"
    return dico.get(var, {}).get("choix", {}).get(str(valeur), str(valeur))


# ------------------------------------------------------------------- préparation
NUMERIQUES = [
    "el2", "a7", "a8", "b3", "b3_declare", "age_calcule", "b5", "c2", "d16", "d17",
    "e4", "e4_valeur", "g3", "j2", "j3", "k4", "m1", "m2", "m3", "m4",
    "score_biens", "promiscuite", "score_connaissances", "pct_connaissances",
    "nb_signes_danger", "exposition_inondation", "eau_amelioree", "assainissement_ameliore",
    "traitement_eau", "allaitement_exclusif_6m", "sro_zinc", "recours_precoce",
    "prise_charge_adequate", "eligible",
]
CATEGORIELLES_NUM = [
    "el0", "el1", "el3", "b1", "b2_connue", "b4", "b6", "b7", "b8", "c1", "c3", "c4", "c5",
    *[f"d{i}" for i in range(1, 24)], "e1", "e2", "e3", "e4_intro", "e4_unite", "e5", "e6", "e7",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "g1", "g2", "g4", "g5", "g6", "g7",
    "h1", "h2", "i1", "i2", "i3", "j1", "j4", "j5", "j6",
    "k1", "k2", "k3", "k5", "k6", "k7", "k8", "k9", "l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8", "n2",
]

TRANCHES = [(0, 5, "0–5 mois"), (6, 11, "6–11 mois"), (12, 23, "12–23 mois"),
            (24, 35, "24–35 mois"), (36, 47, "36–47 mois"), (48, 59, "48–59 mois")]


def _tranche(age) -> str:
    try:
        a = float(age)
    except (TypeError, ValueError):
        return "Non renseigné"
    for bas, haut, nom in TRANCHES:
        if bas <= a <= haut:
            return nom
    return "Hors cible"


def preparer(brut: pd.DataFrame, dico: Dict[str, dict]) -> pd.DataFrame:
    """Aplatit les noms de groupes, convertit les types et ajoute les variables dérivées."""
    if brut.empty:
        return brut
    df = brut.copy()
    df.columns = [c.split("/")[-1] for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()]

    for c in set(NUMERIQUES + CATEGORIELLES_NUM) & set(df.columns):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    for c in ("_submission_time", "start", "end"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce", utc=True).dt.tz_localize(None)
    if "a2" in df.columns:
        df["a2"] = pd.to_datetime(df["a2"], errors="coerce")

    df["date_collecte"] = df.get("a2", pd.Series(pd.NaT, index=df.index))
    if "_submission_time" in df.columns:
        df["date_collecte"] = df["date_collecte"].fillna(df["_submission_time"])
    df["jour"] = pd.to_datetime(df["date_collecte"], errors="coerce").dt.date

    if {"start", "end"}.issubset(df.columns):
        df["duree_min"] = (df["end"] - df["start"]).dt.total_seconds() / 60

    # Libellés lisibles
    for var, cible in [("a3", "aire_sante"), ("b1", "sexe"), ("c3", "niveau_etudes"),
                       ("f1", "source_eau"), ("g1", "type_latrine"), ("h1", "elimination_dechets"),
                       ("k8", "lieu_soins")]:
        if var in df.columns:
            df[cible] = df[var].apply(lambda v, x=var: libelle(dico, x, _code(v)))

    if "b3" in df.columns:
        df["tranche_age"] = df["b3"].apply(_tranche)

    # Filets de sécurité : recalcul si les variables calculées du formulaire sont absentes
    if "j1" in df.columns:
        df["diarrhee"] = (df["j1"] == 1).astype("Int64")
    if {"k2", "k3"}.issubset(df.columns) and "sro_zinc" not in df.columns:
        df["sro_zinc"] = ((df["k2"] == 1) & (df["k3"] == 1)).astype(int)
    if {"i1", "i2", "i3"}.issubset(df.columns) and "jmp_hygiene" not in df.columns:
        df["jmp_hygiene"] = df.apply(
            lambda r: "Basique" if r.get("i1") == 1 and r.get("i2") == 1 and r.get("i3") == 1
            else ("Limité" if r.get("i1") == 1 else "Aucun service"), axis=1)

    if "eligible" in df.columns:
        df = df[df["eligible"] == 1]
    return df.reset_index(drop=True)


# ---------------------------------------------------------------- données de test
def donnees_demo(n: int = 420, graine: int = 11) -> pd.DataFrame:
    """Jeu de données fictif respectant la structure du formulaire (mode démonstration)."""
    rng = random.Random(graine)
    aires = ["agricole", "industriel_1", "industriel_2", "industriel_3", "masiala", "mateba",
             "mayulu", "mfumu", "mombele", "mososo", "residentiel"]
    debut = dt.date.today() - dt.timedelta(days=21)
    lignes = []
    for i in range(n):
        aire = rng.choice(aires)
        inond = rng.random() < (0.55 if aire in ("industriel_1", "mombele", "mososo") else 0.22)
        eau_am = rng.random() < 0.78
        savon = rng.random() < 0.52
        latrine_partagee = rng.random() < 0.46
        risque = 0.11 + 0.10 * inond + 0.07 * (not eau_am) + 0.06 * (not savon) + 0.03 * latrine_partagee
        diarrhee = rng.random() < risque
        age = rng.choice([rng.randint(0, 5), rng.randint(6, 11), rng.randint(12, 23),
                          rng.randint(24, 35), rng.randint(36, 47), rng.randint(48, 59)])
        sro = diarrhee and rng.random() < 0.58
        zinc = diarrhee and rng.random() < 0.31
        recours = diarrhee and rng.random() < 0.63
        lignes.append({
            "_id": 1000 + i,
            "_submission_time": dt.datetime.combine(debut + dt.timedelta(days=rng.randint(0, 21)),
                                                    dt.time(rng.randint(8, 17), rng.randint(0, 59))),
            "a2": debut + dt.timedelta(days=rng.randint(0, 21)),
            "a3": aire, "a6": f"ENQ{rng.randint(1, 6):02d}", "a7": rng.randint(3, 12), "a8": rng.randint(1, 4),
            "b1": rng.choice([1, 2]), "b3": age,
            "c2": rng.randint(18, 45), "c3": rng.choice([0, 1, 2, 2, 3]),
            "d16": rng.randint(1, 4), "d17": rng.randint(2, 9),
            "d18": int(inond), "d21": int(rng.random() < 0.4),
            "score_biens": rng.randint(1, 12),
            "f1": rng.choice([1, 2, 2, 3, 4, 7, 9]) if not eau_am else rng.choice([1, 2, 3, 7]),
            "f3": rng.choice([0, 1, 2]), "f8": rng.choice([1, 1, 2, 3, 4]),
            "eau_amelioree": int(eau_am),
            "g1": rng.choice([1, 2, 3]) if rng.random() < 0.8 else rng.choice([4, 5]),
            "g2": int(latrine_partagee), "g7": rng.choice([0, 1, 2, 8]),
            "i1": int(rng.random() < 0.72), "i2": int(rng.random() < 0.6), "i3": int(savon),
            "j1": int(diarrhee), "j3": rng.randint(1, 7) if diarrhee else None,
            "j4": int(rng.random() < 0.08) if diarrhee else None,
            "k1": rng.choice([1, 2, 3]) if diarrhee else None,
            "k2": int(sro) if diarrhee else None, "k3": int(zinc) if diarrhee else None,
            "k6": rng.choice([1, 1, 2, 3]) if diarrhee else None,
            "k7": int(recours) if diarrhee else None,
            "k8": rng.choice([1, 2, 3, 4, 5, 6]) if recours else None,
            "k9": rng.choice([1, 1, 2, 3, 4]) if recours else None,
            "score_connaissances": max(0, min(8, int(rng.gauss(5.2, 1.7)))),
            "nb_signes_danger": rng.randint(0, 5),
            "eligible": 1, "n2": 1,
        })
    df = pd.DataFrame(lignes)
    df["start"] = pd.to_datetime(df["_submission_time"]) - pd.to_timedelta([rng.randint(14, 38) for _ in range(n)], unit="m")
    df["end"] = pd.to_datetime(df["_submission_time"])
    return df
