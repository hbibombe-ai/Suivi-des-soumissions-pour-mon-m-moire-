"""
Suivi des soumissions par enquêteur pour l'application « Diarrhée Limete »
(diarrhee-limete.streamlit.app).

Deux fonctions à brancher dans app.py :

1) filtre_enqueteur(df, conteneur)
   Ajoute un menu « Enquêteur » dans la rangée FILTRES (à côté de Période,
   Aires de santé, Sexe, Tranche d'âge) et renvoie les fiches filtrées.

2) section_suivi_enqueteurs(df_filtre)
   À placer dans l'onglet « Suivi de la collecte » : indicateurs, cumul par
   rapport au rythme attendu, fiches par jour et tableau de suivi.

Exemple (adapter les noms à votre code) :

    from suivi_enqueteurs import filtre_enqueteur, section_suivi_enqueteurs

    c1, c2, c3, c4, c5 = st.columns([1.3, 1.6, 0.9, 1.2, 1.2])   # au lieu de 4 colonnes
    ...                                       # vos filtres actuels dans c1 à c4
    df_f = filtre_enqueteur(df_f, c5)         # nouveau filtre, après les autres

    with onglet_suivi:                        # onglet « Suivi de la collecte »
        section_suivi_enqueteurs(df_f)
        ...                                   # vos graphiques actuels

Aucune nouvelle dépendance : altair est installé avec Streamlit.
"""
from __future__ import annotations

import datetime as dt

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

# ----------------------------------------------------------------------------
# PARAMÈTRES À AJUSTER
# ----------------------------------------------------------------------------
# Colonne « enquêteur » de l'export Kobo. None = détection automatique
# (A3, ou nom contenant « enqueteur »). Mettre le nom exact si besoin.
COL_ENQUETEUR: str | None = None
# Colonnes de date essayées dans l'ordre (heure d'envoi au serveur d'abord).
COL_DATE_CANDIDATES = ["_submission_time", "end", "today", "start"]

FUSEAU = "Africa/Kinshasa"
DATE_DEBUT = dt.date(2026, 9, 30)   # J1 de la collecte
RYTHME_JOUR = 10                    # ménages par jour et par enquêteur
JOURS_DE_TRAVAIL = "1111110"        # lundi → dimanche (dimanche non travaillé)
SEUIL_ETAPE = 40                    # point d'étape (réunion d'évaluation)
OBJECTIF_TOTAL = 427

# Quota de chaque enquêteur (lots E1 à E5) — noms tels qu'ils sont saisis dans Kobo.
QUOTAS: dict[str, int] = {
    # "FLODEN": 83,      # E1
    # "ELVIS": 87,       # E2
    # "HERMELINE": 87,   # E3
    # "BEATRICE": 82,    # E4
    # "CHRISTEVIE": 88,  # E5
}
QUOTA_PAR_DEFAUT = 85               # 427 / 5
CLE_SELECTION = "filtre_enqueteur"


# ----------------------------------------------------------------------------
# Outils
# ----------------------------------------------------------------------------
def _trouver_colonne_enqueteur(df: pd.DataFrame) -> str | None:
    if COL_ENQUETEUR and COL_ENQUETEUR in df.columns:
        return COL_ENQUETEUR
    for c in df.columns:
        court = str(c).split("/")[-1].lower()          # « groupe/A3 » -> « a3 »
        if court in ("a3", "enqueteur", "enquêteur", "nom_enqueteur") or "enqueteur" in court:
            return c
    return None


def _preparer(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute _enqueteur et _jour (date locale de soumission) sans modifier les autres colonnes."""
    if "_enqueteur" in df.columns and "_jour" in df.columns:
        return df
    col_enq = _trouver_colonne_enqueteur(df)
    col_date = next((c for c in COL_DATE_CANDIDATES if c in df.columns), None)
    if col_enq is None or col_date is None:
        st.error("Suivi par enquêteur : colonne enquêteur ou date introuvable. Renseignez COL_ENQUETEUR "
                 "dans suivi_enqueteurs.py.")
        st.stop()
    out = df.copy()
    out["_enqueteur"] = (out[col_enq].astype(str).str.strip().str.upper()
                         .replace({"": "NON RENSEIGNÉ", "NAN": "NON RENSEIGNÉ", "NONE": "NON RENSEIGNÉ"}))
    d = pd.to_datetime(out[col_date], errors="coerce", utc=True)
    out["_jour"] = d.dt.tz_convert(FUSEAU).dt.date
    return out


def _pleine_largeur(fonction, *args, **kwargs):
    """width='stretch' (Streamlit récent) ou use_container_width (versions plus anciennes)."""
    try:
        return fonction(*args, width="stretch", **kwargs)
    except TypeError:
        return fonction(*args, use_container_width=True, **kwargs)


def quota(nom: str) -> int:
    return QUOTAS.get(nom, QUOTA_PAR_DEFAUT)


def rang_jour(jour: dt.date) -> int:
    """Numéro du jour de collecte (J1 = DATE_DEBUT), dimanches exclus."""
    return int(np.busday_count(DATE_DEBUT, jour + dt.timedelta(days=1), weekmask=JOURS_DE_TRAVAIL))


# ----------------------------------------------------------------------------
# 1) Filtre
# ----------------------------------------------------------------------------
def filtre_enqueteur(df: pd.DataFrame, conteneur=st) -> pd.DataFrame:
    """Menu « Enquêteur » (sélection multiple, vide = tous) ; renvoie les fiches filtrées."""
    dfp = _preparer(df)
    noms = sorted(dfp["_enqueteur"].dropna().unique())
    choix = conteneur.multiselect("Enquêteur", noms, key=CLE_SELECTION,
                                  placeholder=f"Tous les enquêteurs ({len(noms)})")
    # dernier jour de collecte de toute l'équipe : sert de référence pour « l'attendu »,
    # même si l'enquêteur choisi n'a rien envoyé ce jour-là
    st.session_state["_suivi_dernier_jour"] = dfp["_jour"].dropna().max()
    return dfp[dfp["_enqueteur"].isin(choix)] if choix else dfp


# ----------------------------------------------------------------------------
# 2) Section « évolution par enquêteur »
# ----------------------------------------------------------------------------
def _serie(d: pd.DataFrame, fin: dt.date) -> pd.DataFrame:
    """Une ligne par enquêteur et par jour (0 les jours sans fiche) + cumul."""
    jours = pd.date_range(min(d["_jour"].min(), DATE_DEBUT), fin, freq="D").date
    grille = pd.MultiIndex.from_product([sorted(d["_enqueteur"].unique()), jours], names=["_enqueteur", "_jour"])
    s = d.groupby(["_enqueteur", "_jour"]).size().reindex(grille, fill_value=0).rename("n").reset_index()
    s["cumul"] = s.groupby("_enqueteur")["n"].cumsum()
    s["Jour"] = [f"{j:%d/%m}" for j in s["_jour"]]
    s["Enquêteur"] = s["_enqueteur"]
    return s


def section_suivi_enqueteurs(df_f: pd.DataFrame) -> None:
    df_f = _preparer(df_f).dropna(subset=["_jour"])
    choix = st.session_state.get(CLE_SELECTION) or []
    seul = choix[0] if len(choix) == 1 else None

    st.markdown("#### Évolution par enquêteur" + (f" — {seul}" if seul else ""))
    if df_f.empty:
        st.info("Aucune fiche pour les filtres sélectionnés.")
        return

    fin = max(df_f["_jour"].max(), st.session_state.get("_suivi_dernier_jour") or df_f["_jour"].max())
    serie = _serie(df_f, fin)
    noms = sorted(df_f["_enqueteur"].unique())
    j = rang_jour(fin)

    # --- indicateurs ---------------------------------------------------------
    n = len(df_f)
    objectif = sum(quota(x) for x in noms) if choix else OBJECTIF_TOTAL
    attendu = min(objectif, RYTHME_JOUR * j * len(noms))
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Fiches envoyées", n, f"{n - attendu:+d} par rapport à l'attendu (J{j})")
    k2.metric("Objectif atteint", f"{n / objectif:.0%}")
    k2.caption(f"{n} sur {objectif} ménages")
    k3.metric(f"Fiches du {fin:%d/%m}", int((df_f['_jour'] == fin).sum()))
    k3.caption(f"rythme visé : {RYTHME_JOUR} par jour" + ("" if seul else " et par enquêteur"))
    jours_actifs = df_f.groupby("_enqueteur")["_jour"].nunique()
    k4.metric("Moyenne par jour travaillé", f"{(df_f.groupby('_enqueteur').size() / jours_actifs).mean():.1f}")
    k4.caption("par enquêteur, jours avec au moins une fiche")

    ordre = list(dict.fromkeys(serie.sort_values("_jour")["Jour"]))
    axe_x = alt.X("Jour:O", title=None, sort=ordre, axis=alt.Axis(labelAngle=0))
    couleur = alt.Color("Enquêteur:N", legend=None if seul else alt.Legend(orient="bottom", title=None))

    g1, g2 = st.columns(2)
    # --- cumul par rapport à la trajectoire attendue -------------------------
    with g1:
        st.markdown("**Cumul par enquêteur**")
        jours = sorted(serie["_jour"].unique())
        q = quota(seul) if seul else QUOTA_PAR_DEFAUT
        cible = pd.DataFrame({"Jour": [f"{x:%d/%m}" for x in jours],
                              "Attendu": [min(q, RYTHME_JOUR * rang_jour(x)) for x in jours]})
        courbes = alt.Chart(serie).mark_line(point=True, strokeWidth=2).encode(
            x=axe_x, y=alt.Y("cumul:Q", title="Fiches (cumul)"), color=couleur,
            tooltip=["Enquêteur:N", "Jour:O", alt.Tooltip("n:Q", title="Ce jour"),
                     alt.Tooltip("cumul:Q", title="Cumul")])
        attendu_l = alt.Chart(cible).mark_line(strokeDash=[6, 4], color="#8a8983").encode(
            x=axe_x, y="Attendu:Q", tooltip=["Jour:O", alt.Tooltip("Attendu:Q", title="Attendu")])
        etape = alt.Chart(pd.DataFrame({"y": [SEUIL_ETAPE]})).mark_rule(
            color="#c0392b", strokeDash=[2, 2]).encode(y="y:Q")
        _pleine_largeur(st.altair_chart, (courbes + attendu_l + etape).properties(height=300))
        st.caption(f"Tirets gris : rythme attendu d'un enquêteur ({RYTHME_JOUR} fiches par jour travaillé, "
                   f"dimanche exclu). Ligne rouge : point d'étape ({SEUIL_ETAPE}).")

    # --- fiches par jour ---------------------------------------------------------
    with g2:
        st.markdown("**Fiches par jour**")
        barres = alt.Chart(serie).mark_bar().encode(
            x=axe_x, y=alt.Y("sum(n):Q", title="Fiches"), color=couleur,
            tooltip=["Enquêteur:N", "Jour:O", alt.Tooltip("n:Q", title="Fiches")])
        rythme = alt.Chart(pd.DataFrame({"y": [RYTHME_JOUR * (1 if seul else len(noms))]})).mark_rule(
            color="#8a8983", strokeDash=[6, 4]).encode(y="y:Q")
        _pleine_largeur(st.altair_chart, (barres + rythme).properties(height=300))
        st.caption("Tirets gris : nombre de fiches attendu par jour"
                   + ("." if seul else f" pour l'équipe ({len(noms)} × {RYTHME_JOUR})."))

    # --- tableau de suivi ----------------------------------------------------------
    st.markdown("**Tableau de suivi**")
    tab = serie.pivot_table(index="Enquêteur", columns="_jour", values="n", aggfunc="sum", fill_value=0)
    tab.columns = [f"{c:%d/%m}" for c in tab.columns]
    resume = pd.DataFrame({"Total": tab.sum(axis=1), "Quota": [quota(x) for x in tab.index]}, index=tab.index)
    resume["% du quota"] = (resume["Total"] / resume["Quota"] * 100).round(0).astype(int)
    resume["Reste"] = (resume["Quota"] - resume["Total"]).clip(lower=0)
    col_att = f"Attendu à J{j}"
    resume[col_att] = [min(quota(x), RYTHME_JOUR * j) for x in tab.index]
    resume["Écart"] = resume["Total"] - resume[col_att]
    resume["Dernière fiche"] = (df_f.groupby("_enqueteur")["_jour"].max().reindex(tab.index)
                                .map(lambda x: f"{x:%d/%m}"))
    tableau = pd.concat([resume, tab], axis=1).sort_values("Total", ascending=False)
    _pleine_largeur(st.dataframe, tableau, column_config={
        "% du quota": st.column_config.ProgressColumn("% du quota", min_value=0, max_value=100, format="%d %%"),
        "Écart": st.column_config.NumberColumn("Écart", format="%+d"),
    })
    st.download_button("Télécharger le tableau de suivi (CSV)", tableau.to_csv(sep=";").encode("utf-8-sig"),
                       file_name=f"suivi_enqueteurs_{fin:%Y%m%d}.csv", mime="text/csv")
