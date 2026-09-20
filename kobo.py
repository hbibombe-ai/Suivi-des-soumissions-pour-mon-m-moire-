"""Connexion à KoboToolbox, dictionnaire de variables et préparation des données.

Le tableau de bord lit les soumissions en direct via l'API REST de KoboToolbox
(https://<serveur>/api/v2/assets/<asset_uid>/data.json) et traduit les codes en
libellés à partir du XLSForm déposé dans le dépôt (version V7 du formulaire).
"""
from __future__ import annotations
import datetime as dt
import random
from typing import Dict, List

import numpy as np
import pandas as pd
import requests

import nutrition

SERVEURS = {
    "Europe (eu.kobotoolbox.org)": "https://eu.kobotoolbox.org",
    "Global (kf.kobotoolbox.org)": "https://kf.kobotoolbox.org",
    "OCHA (kobo.humanitarianresponse.info)": "https://kobo.humanitarianresponse.info",
}
XLSFORM = "KoboCollect_XLSForm_Diarrhee_Limete_2026_V7.xlsx"
TIMEOUT = 60

AIRES = ["agricole", "industriel_1", "industriel_2", "industriel_3", "masiala", "mateba",
         "mayulu", "mfumu", "mombele", "mososo", "residentiel"]


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
    return {"nom": a.get("name", "—"), "soumissions": a.get("deployment__submission_count", 0),
            "deploye": a.get("date_deployed") or a.get("date_modified")}


# ------------------------------------------------------------------- dictionnaire
def charger_dictionnaire(chemin_xlsform: str = XLSFORM) -> Dict[str, dict]:
    """Construit {variable: {'label':…, 'type':…, 'choix': {code: libellé}}} à partir du XLSForm."""
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
        if not q["name"] or not t or t[0] in ("begin_group", "end_group"):
            continue
        dico[q["name"]] = {"label": q.get("label", "") or q["name"], "type": t[0],
                           "choix": listes.get(t[1], {}) if len(t) > 1 else {}}
    return dico


def _code(v):
    """Normalise un code : 2.0 → '2', 'mfumu' → 'mfumu'."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return v
    if isinstance(v, float) and float(v).is_integer():
        return str(int(v))
    return str(v)


def libelle(dico: Dict[str, dict], var: str, valeur) -> str:
    """Traduit un code en libellé lisible (ex. a4 = 'agricole' → 'Agricole')."""
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return "Non renseigné"
    return dico.get(var, {}).get("choix", {}).get(str(valeur), str(valeur))


# ------------------------------------------------------------------- préparation
# Compatibilité : données collectées avec la version V3 du formulaire → noms V7
V3_VERS_V7 = {"el0": "el4", "a3": "a4", "a4": "a5", "a5": "a6", "a6": "a3", "a7": "a8", "a8": "a9",
              "a9_gps": "a7_gps", "k2": "k4", "k3": "k5", "k4": "k6", "k5": "k2", "k6": "k3"}

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


def _numeriser(df: pd.DataFrame) -> pd.DataFrame:
    """Convertit en nombres les colonnes dont (presque) toutes les valeurs sont numériques."""
    for c in df.columns:
        if not c.startswith("_") and not pd.api.types.is_numeric_dtype(df[c]) \
                and not pd.api.types.is_datetime64_any_dtype(df[c]):
            s = df[c].dropna()
            if len(s) and s.map(lambda v: isinstance(v, (int, float)) or str(v).replace(".", "", 1).lstrip("-").isdigit()).mean() >= 0.9:
                df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def aplatir(brut: pd.DataFrame) -> pd.DataFrame:
    """Retire les préfixes de groupes (groupe/variable) et applique la compatibilité V3."""
    df = brut.copy()
    df.columns = [c.split("/")[-1] for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()]
    if "el0" in df.columns and "el4" not in df.columns:  # formulaire V3
        df = df.rename(columns=V3_VERS_V7)
    return _numeriser(df)


def participation(brut: pd.DataFrame) -> dict:
    """Bilan des fiches envoyées : éligibles, non éligibles, refus (Tableau 5 du mémoire)."""
    if brut.empty:
        return {}
    df = aplatir(brut)
    g = lambda c: df[c] if c in df else pd.Series(np.nan, index=df.index)
    non_elig = (g("el1") == 0) | (g("el2") < 6) | (g("el3") == 0)
    refus = (~non_elig) & (g("el4") == 0)
    enquetes = eligibilite(df) == 1
    return {"soumises": len(df), "non_eligibles": int(non_elig.sum()), "refus": int(refus.sum()),
            "enquetes": int(enquetes.sum()),
            "detail_non_elig": {"Hors ZS de Limete": int((g("el1") == 0).sum()),
                                "Résidence < 6 mois": int(((g("el1") == 1) & (g("el2") < 6)).sum()),
                                "Pas d'enfant de 0 à 59 mois": int(((g("el1") == 1) & (g("el2") >= 6) & (g("el3") == 0)).sum())}}


def preparer(brut: pd.DataFrame, dico: Dict[str, dict]) -> pd.DataFrame:
    """Aplatit, convertit les types et ajoute les variables dérivées (y compris les z-scores)."""
    if brut.empty:
        return brut
    df = aplatir(brut)
    # colonnes absentes (questions non posées ou non encore renseignées) : ajoutées vides
    manquantes = [v for v in dico if v not in df.columns]
    if manquantes:
        df = pd.concat([df, pd.DataFrame(np.nan, index=df.index, columns=manquantes)], axis=1)

    for c in ("_submission_time", "start", "end"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce", utc=True).dt.tz_localize(None)
    for c in ("a2", "b2"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    df["date_collecte"] = df.get("a2", pd.Series(pd.NaT, index=df.index))
    if "_submission_time" in df.columns:
        df["date_collecte"] = df["date_collecte"].fillna(df["_submission_time"])
    df["jour"] = pd.to_datetime(df["date_collecte"], errors="coerce").dt.date
    if {"start", "end"}.issubset(df.columns):
        df["duree_min"] = (df["end"] - df["start"]).dt.total_seconds() / 60

    # Libellés lisibles
    for var, cible in [("a4", "aire_sante"), ("b1", "sexe"), ("c3", "niveau_etudes"),
                       ("f1", "source_eau"), ("g1", "type_latrine"), ("h1", "elimination_dechets"),
                       ("k8", "lieu_soins")]:
        if var in df.columns:
            df[cible] = df[var].apply(lambda v, x=var: libelle(dico, x, _code(v)))
    if "a3" in df.columns:
        df["enqueteur"] = df["a3"].astype(str)

    if "b3" in df.columns:
        df["tranche_age"] = df["b3"].apply(_tranche)
    if "j1" in df.columns:
        df["diarrhee"] = (df["j1"] == 1).astype("Int64")

    # Filets de sécurité : recalcul si les variables calculées du formulaire sont absentes
    if {"k4", "k5"}.issubset(df.columns) and "sro_zinc" not in df.columns:
        df["sro_zinc"] = np.where(df["j1"] == 1, ((df["k4"] == 1) & (df["k5"] == 1)).astype(int), np.nan)
    if "eau_amelioree" not in df.columns and "f1" in df.columns:
        df["eau_amelioree"] = df["f1"].isin([1, 2, 3, 5, 7, 8]).astype(int)
    if "jmp_hygiene" not in df.columns and "i1" in df.columns:
        df["jmp_hygiene"] = np.where(df["i1"] == 1, np.where((df.get("i2") == 1) & (df.get("i3") == 1), "Basique", "Limité"), "Aucun service")

    # --- Anthropométrie : âge exact, z-scores OMS, classes -------------------
    age_exact = df.get("b3", pd.Series(np.nan, index=df.index)).astype(float)
    if {"a2", "b2"}.issubset(df.columns):
        jours = (df["a2"] - df["b2"]).dt.days
        age_exact = (jours / 30.4375).where(jours.notna(), age_exact)
    df["age_exact_mois"] = age_exact
    if "poids_final" in df.columns or "taille_final" in df.columns:
        g = lambda c: df[c] if c in df else pd.Series(np.nan, index=df.index)
        z = [nutrition.zscores(s, a, w, h, pos) for s, a, w, h, pos in
             zip(g("b1"), df["age_exact_mois"], g("poids_final"), g("taille_final"), g("m4"))]
        z = pd.DataFrame(z, index=df.index)
        for k in ("waz", "haz", "whz"):
            df[k] = z[k]
        df["cl_whz"] = df["whz"].apply(nutrition.classe_z)
        df["cl_haz"] = df["haz"].apply(nutrition.classe_z)
        df["cl_waz"] = df["waz"].apply(nutrition.classe_z)
        df["emaciation"] = np.where(df["whz"].notna(), (df["whz"] < -2).astype(float), np.nan)
        df["retard_croissance"] = np.where(df["haz"].notna(), (df["haz"] < -2).astype(float), np.nan)
        df["insuffisance_ponderale"] = np.where(df["waz"].notna(), (df["waz"] < -2).astype(float), np.nan)
        pb, oed = g("pb_final"), g("m11")
        df["cl_pb"] = [nutrition.classe_pb(p_, o) for p_, o in zip(pb, oed)]
        mesure = (oed == 1) | pb.notna()
        df["malnutrition_aigue_pb"] = np.where(mesure, ((oed == 1) | (pb < 125)).astype(float), np.nan)

    df["eligible"] = eligibilite(df)
    df = df[df["eligible"] == 1]
    return df.reset_index(drop=True)


def eligibilite(df: pd.DataFrame) -> pd.Series:
    """Variable `eligible` du formulaire ; recalculée à partir de EL1–EL4 si elle manque ou est vide."""
    g = lambda c: pd.to_numeric(df[c], errors="coerce") if c in df else pd.Series(np.nan, index=df.index)
    calc = ((g("el1") == 1) & ((g("el2") >= 6) | g("el2").isna() & ("el2" not in df)) & (g("el3") == 1)
            & (g("el4") == 1)).astype(int)
    if "eligible" in df.columns:
        return g("eligible").fillna(calc)
    return calc


def diagnostic(brut: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par fiche reçue : critères d'éligibilité et motif d'exclusion éventuel."""
    df = aplatir(brut)
    g = lambda c: pd.to_numeric(df[c], errors="coerce") if c in df else pd.Series(np.nan, index=df.index)
    elig = eligibilite(df)
    def motif(i):
        if elig.iloc[i] == 1:
            return "Retenue"
        if g("el1").iloc[i] == 0: return "Ménage hors ZS de Limete (EL1 = Non)"
        if g("el2").iloc[i] < 6: return "Résidence < 6 mois (EL2)"
        if g("el3").iloc[i] == 0: return "Pas d'enfant de 0 à 59 mois (EL3 = Non)"
        if g("el4").iloc[i] == 0: return "Consentement refusé (EL4 = Non)"
        return "Critères d'éligibilité non renseignés"
    out = pd.DataFrame({
        "Fiche": df.get("_id", pd.Series(range(len(df)))).values,
        "Envoyée le": pd.to_datetime(df.get("_submission_time"), errors="coerce").values if "_submission_time" in df else None,
        "Version du formulaire": df.get("__version__", pd.Series("", index=df.index)).values,
        "EL1": g("el1").values, "EL2 (mois)": g("el2").values, "EL3": g("el3").values, "EL4": g("el4").values,
        "eligible": g("eligible").values, "Statut": [motif(i) for i in range(len(df))],
    })
    return out


# ---------------------------------------------------------------- données de test
def donnees_demo(n: int = 420, graine: int = 11) -> pd.DataFrame:
    """Jeu de données fictif respectant la structure du formulaire V7 (mode démonstration)."""
    rng = random.Random(graine)
    ch = rng.choice
    debut = dt.date.today() - dt.timedelta(days=21)
    lignes = []
    for i in range(n):
        aire_i = rng.randrange(11)
        aire = AIRES[aire_i]
        inond = rng.random() < (0.55 if aire in ("industriel_1", "mombele", "mososo") else 0.22)
        eau_am = rng.random() < 0.78
        savon = rng.random() < 0.52
        partage = rng.random() < 0.46
        age = ch([rng.randint(0, 5), rng.randint(6, 11), rng.randint(12, 23), rng.randint(24, 35),
                  rng.randint(36, 47), rng.randint(48, 59)])
        sexe = ch([1, 2])
        # anthropométrie : tirages autour de la médiane OMS
        z_h, z_w = rng.gauss(-0.9, 1.2), rng.gauss(-0.4, 1.1)
        lms_h = nutrition._lms("lhfa_l" if age < 24 else "lhfa_h", sexe, age + 0.5)
        taille = lms_h[1] * (1 + lms_h[2] * z_h) if lms_h else None
        lms_w = nutrition._lms("wfl" if age < 24 else "wfh", sexe, taille) if taille else None
        poids = lms_w[1] * (1 + lms_w[2] * z_w) if lms_w else None
        pb = int(rng.gauss(142, 12)) if age >= 6 else None
        maigre = (z_w < -2) or (pb is not None and pb < 125)
        risque = 0.10 + 0.10 * inond + 0.07 * (not eau_am) + 0.06 * (not savon) + 0.03 * partage + 0.08 * maigre \
            + (0.06 if 6 <= age <= 23 else 0)
        diarrhee = rng.random() < risque
        f1 = ch([1, 2, 3, 7]) if eau_am else ch([4, 6, 9])
        g1 = ch([1, 2, 3]) if rng.random() < 0.8 else ch([4, 5])
        f8 = ch([1, 1, 2, 3, 4])
        i1, i2 = int(rng.random() < 0.72), int(rng.random() < 0.6)
        sro, zinc, recours = (diarrhee and rng.random() < 0.58), (diarrhee and rng.random() < 0.31), (diarrhee and rng.random() < 0.63)
        e4_intro = int(age >= 4 or rng.random() < 0.4)
        l = {f"l{k}": int(rng.random() < p_) for k, p_ in zip(range(1, 9), [.85, .7, .6, .45, .5, .8, .7, .55])}
        l["l2"] = ch([1, 1, 1, 2, 3, 9])
        score = sum([l["l1"], l["l2"] == 1, l["l3"], l["l4"], l["l5"], l["l6"], l["l7"], l["l8"]])
        signes = rng.sample(["boire", "vomissements", "sang", "fievre", "lethargie", "persistante"], rng.randint(0, 4))
        d16, d17 = rng.randint(1, 4), rng.randint(2, 9)
        t_sub = dt.datetime.combine(debut + dt.timedelta(days=rng.randint(0, 21)), dt.time(rng.randint(8, 17), rng.randint(0, 59)))
        lignes.append({
            "_id": 1000 + i, "_submission_time": t_sub, "a2": t_sub.date(),
            "el1": 1, "el2": rng.randint(6, 240), "el3": 1, "el4": 1, "eligible": 1,
            "a3": f"ENQ{aire_i + 1:02d}", "a4": aire, "a6": f"M{i:04d}", "a8": rng.randint(3, 12), "a9": ch([1, 1, 2, 3]),
            "b1": sexe, "b2_connue": 1, "b3": age, "b4": ch([1, 2, 2, 3]), "b5": ch([1, 1, 2, 3, 4, 5]),
            "b6": ch([1, 1, 2, 3]), "b7": ch([1, 1, 1, 0, 9]),
            "c1": ch([1, 1, 1, 1, 2, 3, 4]), "c2": rng.randint(16, 48), "c3": ch([0, 1, 2, 2, 2, 3]),
            "c4": ch(range(1, 9)), "c5": ch([1, 2, 2, 2, 3, 4]),
            "d1": int(rng.random() < .8), "score_biens": rng.randint(1, 12), "d14": ch([1, 2, 2, 3]),
            "d15": ch([1, 2, 2, 2, 3]), "d16": d16, "d17": d17, "promiscuite": round(d17 / d16, 1),
            "d18": int(inond), "d19": ch([1, 2, 3]) if inond else None, "d20": ch([1, 2, 3]) if inond else None,
            "d21": int(rng.random() < 0.4), "d22": ch([0, 1, 2]), "d23": ch([1, 2, 3, 4]),
            "e1": 1, "e2": int(age < 20 and rng.random() < 0.8), "e3": ch([1, 0, 0, 9]), "e4_intro": e4_intro,
            "e4": (rng.choice([2, 3, 4, 5, 6, 6, 7]) if e4_intro else None), "e5": ch([0, 0, 1, 2]), "e6": int(rng.random() < .6),
            "e7": ch([1, 2, 2, 3]),
            "f1": f1, "f2": int(rng.random() < .5), "f3": ch([0, 1, 2]), "f4": ch([1, 2, 3, 4]), "f5": ch([1, 2, 3, 4, 5]),
            "f6": int(rng.random() < .7), "f7": ch([1, 2, 3, 4]), "f8": f8, "eau_amelioree": int(eau_am),
            "jmp_eau": ("Basique" if f8 in (1, 2) else "Limité") if eau_am else "Non amélioré",
            "g1": g1, "g2": int(partage) if g1 != 5 else None, "g4": ch([1, 1, 2, 3, 4, 5]), "g5": ch([0, 0, 1, 8]),
            "g6": ch([0, 1, 9]), "g7": ch([0, 1, 2, 8]),
            "jmp_assainissement": ("Basique" if not partage else "Limité") if g1 in (1, 2, 3) else ("Défécation en plein air" if g1 == 5 else "Non amélioré"),
            "h1": ch([1, 2, 3, 3, 4, 5, 6]), "h2": int(rng.random() < .5),
            "i1": i1, "i2": i2, "i3": int(savon),
            "jmp_hygiene": ("Basique" if i2 and savon else "Limité") if i1 else "Aucun service",
            "i4": " ".join(rng.sample(["apres_toilettes", "apres_selles", "avant_preparation", "avant_manger", "avant_nourrir"], rng.randint(1, 4))),
            "j1": int(diarrhee), "j2": rng.randint(1, 13) if diarrhee else None, "j3": ch([1, 2, 3, 4, 5, 7, 9, 15]) if diarrhee else None,
            "j4": ch([0, 0, 0, 1, 9]) if diarrhee else None, "j5": ch([0, 1, 9]) if diarrhee else None, "j6": ch([0, 1]) if diarrhee else None,
            "k1": ch([1, 2, 3, 4]) if diarrhee else None, "k2": ch([1, 2, 3, 4, 8]) if diarrhee else None,
            "k3": ch([1, 1, 2, 3, 4]) if diarrhee else None, "k4": int(sro) if diarrhee else None, "k5": int(zinc) if diarrhee else None,
            "k6": ch([5, 10, 10, 14]) if zinc else None, "k7": int(recours) if diarrhee else None,
            "k8": ch([1, 2, 3, 4, 5, 6]) if recours else None, "k9": ch([1, 1, 2, 3, 4]) if recours else None,
            "k10": ("maladie_legere" if rng.random() < .5 else "argent domicile") if diarrhee and not recours else None,
            **l, "l9": " ".join(signes) if signes else "nsp",
            "score_connaissances": score, "nb_signes_danger": len(signes),
            "m0": 1, "m4": 1 if age < 24 else 2, "poids_final": round(poids, 2) if poids else None,
            "taille_final": round(taille, 1) if taille else None, "pb_final": pb, "m11": int(rng.random() < 0.01),
            "n2": 1,
        })
    # quelques fiches non éligibles ou refusées (bilan de participation)
    for j in range(38):
        cas = j % 4
        lignes.append({"_id": 5000 + j, "_submission_time": dt.datetime.combine(debut + dt.timedelta(days=rng.randint(0, 21)), dt.time(10)),
                       "el1": 0 if cas == 0 else 1, "el2": 3 if cas == 1 else 24, "el3": 0 if cas == 2 else 1,
                       "el4": 0 if cas == 3 else None, "eligible": 0})
    df = pd.DataFrame(lignes)
    df["start"] = pd.to_datetime(df["_submission_time"]) - pd.to_timedelta([rng.randint(18, 45) for _ in range(len(df))], unit="m")
    df["end"] = pd.to_datetime(df["_submission_time"])
    df["b2"] = pd.to_datetime(df["a2"]) - pd.to_timedelta(df["b3"].fillna(0) * 30.4375 + 10, unit="D")
    return df
