"""Calibre le mode démonstration sur un export KoboToolbox réel.

Usage (en local) :
    python calibrer_demo.py "export_kobo.xlsx"

Lit un export Excel de KoboToolbox (libellés ou valeurs XML, toutes versions) et écrit
calibrage_demo.json : la distribution observée de chaque question (nombre de réponses par
modalité), la prévalence de la diarrhée, la participation, le rythme de collecte et la
répartition des fiches par enquêteur et par aire de santé.

Le fichier ne contient QUE des agrégats : aucune fiche individuelle, aucun code ménage,
aucune coordonnée GPS, aucun texte libre. Il peut donc être publié sur GitHub.
Le mode démonstration (kobo.donnees_demo) tire alors 427 ménages fictifs selon ces
distributions : une projection de l'enquête complète si la collecte continue comme observé.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
import unicodedata

import pandas as pd

import kobo

SORTIE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibrage_demo.json")
# Questions jamais agrégées : identification, localisation fine, texte libre, métadonnées
EXCLUES = {"a1", "a1a", "a2", "a3", "a5", "a6", "a7", "a7_gps", "a9_gps", "n1", "n3", "code_unique",
           "deviceid", "start", "end", "date_systeme", "b2"}
MIN_REPONSES = 5  # en dessous, la question garde la distribution par défaut de la démonstration


def _norm(x) -> str:
    t = unicodedata.normalize("NFKD", str(x)).encode("ascii", "ignore").decode().lower()
    return " ".join(t.replace("’", "'").split())


def _colonnes(df: pd.DataFrame, dico: dict) -> dict:
    """En-tête de l'export -> nom de variable du formulaire (par libellé ou par nom)."""
    par_label = {_norm(v["label"]): k for k, v in dico.items() if v.get("label")}
    out = {}
    for c in df.columns:
        if c in dico:
            out[c] = c
        elif _norm(c) in par_label:
            out[c] = par_label[_norm(c)]
        elif _norm(c).startswith("a3."):
            out[c] = "a3"
    return out


def _vers_code(valeur, choix: dict):
    """Libellé ou code -> code du formulaire (None si non reconnu)."""
    if valeur is None or (isinstance(valeur, float) and math.isnan(valeur)):
        return None
    if isinstance(valeur, float) and valeur.is_integer():
        valeur = int(valeur)
    s = str(valeur).strip()
    if s in choix:
        return s
    inv = {_norm(lab): code for code, lab in choix.items()}
    inv.update({_norm(code): code for code in choix})
    return inv.get(_norm(s))


def calibrer(chemin: str) -> dict:
    dico = kobo.charger_dictionnaire()
    brut = pd.read_excel(chemin)
    cols = _colonnes(brut, dico)
    garder = {}
    for c, v in cols.items():  # si deux colonnes donnent la même variable (versions), garder la première
        garder.setdefault(v, brut[c])
    df = pd.DataFrame(garder)
    elig = pd.to_numeric(df.get("eligible"), errors="coerce") == 1
    e = df[elig]

    categoriel, numerique = {}, {}
    for var, info in dico.items():
        if var in EXCLUES or var not in e.columns:
            continue
        s = e[var]
        if info.get("type") == "select_one" and info.get("choix"):
            codes = s.map(lambda v: _vers_code(v, info["choix"])).dropna()
            if len(codes) >= MIN_REPONSES:
                cpt = {c: 0 for c in info["choix"]}
                for c in codes:
                    cpt[c] += 1
                categoriel[var] = cpt
        elif info.get("type") in ("integer", "decimal", "calculate") or var in ("b3", "score_biens"):
            x = pd.to_numeric(s, errors="coerce").dropna()
            if len(x) >= MIN_REPONSES:
                x = x.round(0 if info.get("type") != "decimal" else 1)
                numerique[var] = {(str(int(k)) if float(k).is_integer() else str(k)): int(v)
                                  for k, v in x.value_counts().sort_index().items()}

    j1 = categoriel.get("j1", {})
    a4_choix = dico.get("a4", {}).get("choix", {})
    aires = e.get("a4", pd.Series(dtype=object)).map(lambda v: _vers_code(v, a4_choix))
    enq = e.get("a3", pd.Series(dtype=object)).astype(str).str.strip().str.upper()
    repart = {}
    for a, q in zip(aires, enq):
        if a and q and q != "NAN":
            repart.setdefault(q, {}).setdefault(a, 0)
            repart[q][a] += 1

    t = pd.to_datetime(e.get("_submission_time", e.get("end")), errors="coerce").dropna()
    jours = t.dt.date.nunique() if len(t) else 0
    nonel = df[~elig]
    motifs = {
        "hors_zone": int((pd.to_numeric(nonel.get("el1"), errors="coerce") == 0).sum()),
        "residence_courte": int((pd.to_numeric(nonel.get("el2"), errors="coerce") < 6).sum()),
        "sans_enfant": int((nonel.get("el3").map(lambda v: _vers_code(v, {"1": "Oui", "0": "Non"})) == "0").sum()),
        "refus": int((nonel.get("el4").map(lambda v: _vers_code(v, {"1": "Oui", "0": "Non"})) == "0").sum()),
    }
    return {
        "source": {"export": os.path.basename(chemin), "calibre_le": dt.date.today().isoformat(),
                   "fiches": int(len(df)), "eligibles": int(elig.sum())},
        "prevalence": {"cas": int(j1.get("1", 0)), "n": int(sum(j1.values()))},
        "participation": {"eligibles": int(elig.sum()), "non_eligibles": motifs},
        "collecte": {"debut": t.min().date().isoformat() if len(t) else None,
                     "jours": int(jours), "fiches_par_jour": round(elig.sum() / max(jours, 1), 1)},
        "enqueteurs_aires": repart,
        "categoriel": categoriel,
        "numerique": numerique,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage : python calibrer_demo.py export_kobo.xlsx")
    cal = calibrer(sys.argv[1])
    with open(SORTIE, "w", encoding="utf-8") as f:
        json.dump(cal, f, ensure_ascii=False, indent=1)
    p = cal["prevalence"]
    print(f"{SORTIE} écrit : {cal['source']['eligibles']} fiches éligibles, {len(cal['categoriel'])} questions "
          f"à choix, {len(cal['numerique'])} numériques ; prévalence {p['cas']}/{p['n']}.")
