"""Tableau de bord dynamique — Enquête diarrhée chez les enfants de moins de 5 ans, ZS de Limete.

Lecture en direct des soumissions KoboCollect via l'API REST de KoboToolbox.
Lancement local :  streamlit run app.py
"""
from __future__ import annotations
import datetime as dt
import io
import os

import pandas as pd
import streamlit as st

import kobo
import theme
import viz

st.set_page_config(page_title="Diarrhée < 5 ans — ZS Limete", page_icon="💧",
                   layout="wide", initial_sidebar_state="expanded")

TITRE = "Profil épidémiologique et facteurs associés à la diarrhée chez les enfants de moins de 5 ans"
SOUS_TITRE = "Zone de Santé de Limete, Kinshasa — collecte KoboCollect 2026"

# --------------------------------------------------------------------- chargement
@st.cache_data(ttl=300, show_spinner="Lecture des soumissions KoboToolbox…")
def charger(serveur: str, token: str, uid: str, _jeton_cache: int) -> pd.DataFrame:
    return kobo.recuperer_soumissions(serveur, token, uid)


@st.cache_data(ttl=3600)
def dictionnaire() -> dict:
    return kobo.charger_dictionnaire()


def parametre(cle: str, defaut: str = "") -> str:
    """Cherche un paramètre dans l'ordre : secrets Streamlit → config_kobo.py → variable
    d'environnement → valeur par défaut. Permet de ne rien saisir à chaque ouverture."""
    try:
        valeur = st.secrets["kobo"][cle]
        if valeur:
            return str(valeur)
    except Exception:  # noqa: BLE001 — aucun fichier secrets.toml
        pass
    try:
        import config_kobo
        valeur = getattr(config_kobo, {"server": "SERVEUR", "token": "TOKEN",
                                       "asset_uid": "ASSET_UID"}[cle], "")
        if valeur:
            return str(valeur)
    except Exception:  # noqa: BLE001 — fichier absent ou incomplet
        pass
    return os.environ.get(f"KOBO_{cle.upper()}", defaut)


# ------------------------------------------------------------------ barre latérale
with st.sidebar:
    st.markdown('<div class="marque"><span class="ico">💧</span>'
                '<span class="txt">Enquête diarrhée &lt; 5 ans<em>ZS de Limete · Kinshasa · 2026</em></span></div>',
                unsafe_allow_html=True)

    st.markdown("### Affichage")
    demo = st.toggle("Mode démonstration", value=not parametre("token"),
                     help="Données fictives, pour présenter le tableau de bord avant la collecte.")

    st.markdown("### Connexion KoboToolbox")
    serveur = parametre("server", "https://eu.kobotoolbox.org")
    token = parametre("token")
    uid = parametre("asset_uid")
    configure = bool(token and uid)

    if configure:
        st.success(f"Connecté · projet `{uid[:10]}…`\n\n{serveur.replace('https://', '')}", icon="✅")
        with st.expander("Modifier la connexion (cette session)"):
            serveur_nom = st.selectbox("Serveur", list(kobo.SERVEURS),
                                       index=list(kobo.SERVEURS.values()).index(serveur)
                                       if serveur in kobo.SERVEURS.values() else 0)
            serveur = kobo.SERVEURS[serveur_nom]
            token = st.text_input("Jeton d'API", value=token, type="password") or token
            uid = st.text_input("Identifiant du formulaire", value=uid) or uid
    else:
        st.info("Renseigner `config_kobo.py` (en local) ou les Secrets de Streamlit Cloud "
                "pour ne plus rien saisir à l'ouverture.", icon="🔑")
        serveur_nom = st.selectbox("Serveur", list(kobo.SERVEURS), index=0)
        serveur = kobo.SERVEURS[serveur_nom]
        token = st.text_input("Jeton d'API", value="", type="password",
                              help="KoboToolbox → Paramètres du compte → Sécurité → Jeton d'API.")
        uid = st.text_input("Identifiant du formulaire", value="",
                            help="Visible dans l'URL du projet : /forms/<asset_uid>/")

    if st.button("Actualiser les données", width="stretch", type="primary"):
        st.cache_data.clear()
        st.session_state["maj"] = dt.datetime.now()
    st.caption(f"Dernière lecture : {st.session_state.get('maj', dt.datetime.now()):%d/%m/%Y %H:%M}")
    st.caption("Mode sombre : `base = \"dark\"` dans .streamlit/config.toml.")

# Le mode clair/sombre vient de .streamlit/config.toml (theme.base) : interface,
# widgets et graphiques restent ainsi parfaitement cohérents.
sombre = (st.get_option("theme.base") or "light").lower() == "dark"
p = viz.palette(sombre)
dico = dictionnaire()

# ------------------------------------------------------------------------ données
erreur = None
if demo:
    brut = kobo.donnees_demo()
elif token and uid:
    try:
        brut = charger(serveur, token, uid, st.session_state.get("maj", 0) and 1 or 0)
    except Exception as e:  # noqa: BLE001
        erreur, brut = str(e), pd.DataFrame()
else:
    brut = pd.DataFrame()

df = kobo.preparer(brut, dico) if not brut.empty else pd.DataFrame()

theme.appliquer(sombre)

if erreur:
    st.error(f"Connexion impossible : {erreur}")
if df.empty:
    theme.entete(TITRE, SOUS_TITRE, [("Source", "En attente de connexion", "alerte")])
    st.info("Renseigner le jeton d'API et l'identifiant du formulaire dans la barre latérale, "
            "ou activer le mode démonstration pour explorer le tableau de bord.")
    st.stop()

chips = [("Fiches", f"{len(df)}", ""),
         ("Dernière donnée",
          f"{max([j for j in df['jour'].dropna()]):%d/%m/%Y}" if df["jour"].notna().any() else "—", ""),
         ("Aires couvertes", f"{df['a3'].nunique() if 'a3' in df else 0} / 11", ""),
         ("Source", "Démonstration — données fictives" if demo else "KoboToolbox — lecture directe",
          "alerte" if demo else "direct")]
theme.entete(TITRE, SOUS_TITRE, chips)

# ------------------------------------------------------------------------ filtres
st.markdown('<div class="filtre-titre">Filtres</div>', unsafe_allow_html=True)
f1, f2, f3, f4 = st.columns([1.6, 2.2, 1.1, 1.6])
jours = sorted([j for j in df["jour"].dropna().unique()])
if jours:
    periode = f1.date_input("Période de collecte", value=(jours[0], jours[-1]),
                            min_value=jours[0], max_value=jours[-1], format="DD/MM/YYYY")
    if isinstance(periode, (list, tuple)) and len(periode) == 2:
        df = df[(df["jour"] >= periode[0]) & (df["jour"] <= periode[1])]

aires = sorted(df["aire_sante"].dropna().unique()) if "aire_sante" in df else []
sel_aires = f2.multiselect("Aires de santé", aires, placeholder=f"Toutes les aires ({len(aires)})")
if sel_aires:
    df = df[df["aire_sante"].isin(sel_aires)]

sexes = sorted(df["sexe"].dropna().unique()) if "sexe" in df else []
sel_sexe = f3.multiselect("Sexe de l'enfant", sexes, placeholder="Les deux")
if sel_sexe:
    df = df[df["sexe"].isin(sel_sexe)]

tranches = [t[2] for t in kobo.TRANCHES if t[2] in set(df.get("tranche_age", []))]
sel_tr = f4.multiselect("Tranche d'âge", tranches, placeholder="Toutes les tranches")
if sel_tr:
    df = df[df["tranche_age"].isin(sel_tr)]

st.markdown(f'<div class="pdp">{len(df)} fiche(s) sélectionnée(s) · actualisation automatique '
            "toutes les 5 minutes · bouton « Actualiser » pour forcer la lecture.</div>", unsafe_allow_html=True)

if df.empty:
    st.warning("Aucune fiche ne correspond aux filtres sélectionnés.")
    st.stop()

# ---------------------------------------------------------------------- indicateurs
def prop(masque_num, masque_den=None):
    den = df if masque_den is None else df[masque_den]
    if len(den) == 0:
        return 0.0, 0.0, 0.0, 0
    k = int(masque_num.reindex(den.index).fillna(False).sum())
    v, b, h = viz.wilson(k, len(den))
    return v, b, h, len(den)

avec_diarrhee = df["j1"] == 1
prev, prev_b, prev_h, n_tot = prop(avec_diarrhee)
d = df[avec_diarrhee]

def part(col, valeur=1, base=d):
    if col not in base or len(base) == 0:
        return 0.0, 0
    k = int((base[col] == valeur).sum())
    return (k / len(base)) if len(base) else 0.0, len(base)

sro, n_d = part("k2")
zinc, _ = part("k3")
sro_zinc = float(((d.get("k2") == 1) & (d.get("k3") == 1)).mean()) if len(d) else 0.0
recours, _ = part("k7")

def carte(col, titre, valeur, note, accent=None):
    theme.carte(col, titre, valeur, note, accent or p["series"][0])

theme.section("Indicateurs clés", "Proportions calculées sur les fiches sélectionnées, avec intervalle de confiance à 95 %.")
c = st.columns(6, gap="small")
carte(c[0], "Fiches éligibles", f"{n_tot}", f"{df['a3'].nunique() if 'a3' in df else 0} aire(s) de santé")
carte(c[1], "Prévalence diarrhée (14 j)", f"{viz.fr(prev*100)} %",
      f"IC 95 % : {viz.fr(prev_b*100)} – {viz.fr(prev_h*100)} %", p["series"][1])
carte(c[2], "Cas de diarrhée", f"{len(d)}", "enfants concernés")
carte(c[3], "SRO", f"{viz.fr(sro*100, 0)} %", f"des {n_d} cas", p["good"])
carte(c[4], "SRO + zinc", f"{viz.fr(sro_zinc*100, 0)} %", "prise en charge complète", p["good"])
carte(c[5], "Recours aux soins", f"{viz.fr(recours*100, 0)} %", "hors domicile", p["series"][0])
st.write("")

onglets = st.tabs(["Suivi de la collecte", "Profil épidémiologique", "Facteurs associés",
                   "Prise en charge", "Connaissances", "Données"])

# 1 — collecte -----------------------------------------------------------------
with onglets[0]:
    g1, g2 = st.columns(2)
    parjour = df.groupby("jour").size().reset_index(name="n").sort_values("jour")
    g1.plotly_chart(viz.barres_temps(parjour["jour"], parjour["n"], "Fiches collectées par jour", p,
                                     ytitre="Fiches"), width="stretch")
    parjour["cumul"] = parjour["n"].cumsum()
    g2.plotly_chart(viz.courbe_cumul(parjour["jour"], parjour["cumul"], "Cumul des fiches collectées", p),
                    width="stretch")
    g3, g4 = st.columns(2)
    if "a6" in df:
        pe = df.groupby("a6").agg(fiches=("a6", "size"),
                                  duree=("duree_min", "median") if "duree_min" in df else ("a6", "size")).reset_index()
        pe = pe.sort_values("fiches", ascending=False)
        g3.plotly_chart(viz.barres_proportions(
            pe["a6"].tolist(), (pe["fiches"] / pe["fiches"].sum()).tolist(),
            (pe["fiches"] / pe["fiches"].sum()).tolist(), (pe["fiches"] / pe["fiches"].sum()).tolist(),
            pe["fiches"].tolist(), "Répartition des fiches par enquêteur", p), width="stretch")
        if "duree_min" in df:
            g4.markdown("**Durée médiane d'entretien par enquêteur**")
            g4.dataframe(pe.rename(columns={"a6": "Enquêteur", "fiches": "Fiches", "duree": "Durée médiane (min)"})
                         .round(1), hide_index=True, width="stretch")

# 2 — profil épidémiologique ---------------------------------------------------
with onglets[1]:
    def prevalence_par(colonne, ordre=None):
        lignes = []
        groupes = ordre or sorted(df[colonne].dropna().unique())
        for g in groupes:
            sous = df[df[colonne] == g]
            v, b, h = viz.wilson(int((sous["j1"] == 1).sum()), len(sous))
            lignes.append((str(g), v, b, h, len(sous)))
        return lignes

    if "aire_sante" in df:
        lignes = sorted(prevalence_par("aire_sante"), key=lambda r: -r[1])
        st.plotly_chart(viz.barres_proportions(
            [l[0] for l in lignes], [l[1] for l in lignes], [l[2] for l in lignes],
            [l[3] for l in lignes], [l[4] for l in lignes],
            "Prévalence de la diarrhée (14 derniers jours) par aire de santé — IC 95 %", p),
            width="stretch")
    a, b = st.columns(2)
    ordre_tr = [t[2] for t in kobo.TRANCHES]
    lignes = [l for l in prevalence_par("tranche_age", ordre_tr) if l[4] > 0]
    a.plotly_chart(viz.barres_proportions(
        [l[0] for l in lignes], [l[1] for l in lignes], [l[2] for l in lignes],
        [l[3] for l in lignes], [l[4] for l in lignes], "Prévalence par tranche d'âge", p),
        width="stretch")
    if "sexe" in df:
        lignes = prevalence_par("sexe")
        b.plotly_chart(viz.barres_proportions(
            [l[0] for l in lignes], [l[1] for l in lignes], [l[2] for l in lignes],
            [l[3] for l in lignes], [l[4] for l in lignes], "Prévalence selon le sexe", p),
            width="stretch")

# 3 — facteurs associés --------------------------------------------------------
with onglets[2]:
    st.markdown("**Services WASH selon l'échelle JMP (OMS/UNICEF)**")
    def niveaux_wash():
        cats, series = ["Eau de boisson", "Assainissement", "Hygiène des mains"], {}
        eau = df["eau_amelioree"] == 1 if "eau_amelioree" in df else df["f1"].isin([1, 2, 3, 5, 7, 8])
        eau_bas = eau & df["f8"].isin([1, 2]) if "f8" in df else eau
        ass = df["g1"].isin([1, 2, 3]) if "g1" in df else pd.Series(False, index=df.index)
        ass_bas = ass & (df["g2"] == 0) if "g2" in df else ass
        hyg = df["i1"] == 1 if "i1" in df else pd.Series(False, index=df.index)
        hyg_bas = hyg & (df["i2"] == 1) & (df["i3"] == 1) if {"i2", "i3"}.issubset(df.columns) else hyg
        n = len(df)
        series["Basique"] = [eau_bas.mean(), ass_bas.mean(), hyg_bas.mean()]
        series["Limité"] = [(eau & ~eau_bas).mean(), (ass & ~ass_bas).mean(), (hyg & ~hyg_bas).mean()]
        series["Non amélioré / aucun"] = [(~eau).mean(), (~ass).mean(), (~hyg).mean()]
        return cats, [(k, v) for k, v in series.items()], n
    cats, series, n = niveaux_wash()
    st.plotly_chart(viz.barres_empilees(cats, series, f"Niveaux de service WASH des ménages (n = {n})", p),
                    width="stretch")

    st.markdown("**Ratios de prévalence bruts** — comparaison exposés / non exposés (analyse exploratoire, non ajustée)")
    expositions = [
        ("Logement inondé (12 derniers mois)", df.get("d18") == 1),
        ("Eaux stagnantes à proximité", df.get("d21") == 1),
        ("Source d'eau non améliorée", ~(df.get("eau_amelioree", pd.Series(1, index=df.index)) == 1)),
        ("Eau de boisson non traitée", df.get("f3") == 0),
        ("Latrine partagée", df.get("g2") == 1),
        ("Latrine non améliorée", ~df.get("g1", pd.Series(1, index=df.index)).isin([1, 2, 3])),
        ("Pas de savon au point de lavage", df.get("i3") != 1),
        ("Surpeuplement (> 3 pers./pièce)", (df.get("d17") / df.get("d16")) > 3),
    ]
    lib, rp, bas, haut, tab = [], [], [], [], []
    for nom, masque in expositions:
        if masque is None or masque.isna().all():
            continue
        m = masque.fillna(False).astype(bool)
        a1, n1 = int((df.loc[m, "j1"] == 1).sum()), int(m.sum())
        a0, n0 = int((df.loc[~m, "j1"] == 1).sum()), int((~m).sum())
        r, lo, hi = viz.ratio_prevalence(a1, n1, a0, n0)
        if r == r:
            lib.append(nom); rp.append(r); bas.append(lo); haut.append(hi)
            tab.append({"Exposition": nom, "Exposés n": n1, "Prévalence exposés": f"{a1/n1:.1%}",
                        "Non exposés n": n0, "Prévalence non exposés": f"{a0/n0:.1%}",
                        "RP (IC 95 %)": f"{r:.2f} ({lo:.2f} – {hi:.2f})"})
    if lib:
        ordre = sorted(range(len(rp)), key=lambda i: -rp[i])
        st.plotly_chart(viz.points_ratios([lib[i] for i in ordre], [rp[i] for i in ordre],
                                          [bas[i] for i in ordre], [haut[i] for i in ordre],
                                          "Ratios de prévalence de la diarrhée selon l'exposition", p),
                        width="stretch")
        st.dataframe(pd.DataFrame(tab), hide_index=True, width="stretch")
        st.caption("Ratios bruts, sans ajustement : à interpréter comme une exploration, "
                   "avant la régression multivariée prévue dans le protocole.")

# 4 — prise en charge ----------------------------------------------------------
with onglets[3]:
    if len(d) == 0:
        st.info("Aucun cas de diarrhée dans la sélection.")
    else:
        etapes = [
            ("Liquides augmentés", (d.get("k1") == 1)),
            ("SRO reçus", (d.get("k2") == 1)),
            ("Zinc reçu", (d.get("k3") == 1)),
            ("SRO + zinc", (d.get("k2") == 1) & (d.get("k3") == 1)),
            ("Alimentation maintenue ou augmentée", d.get("k6").isin([1, 2])),
            ("Recours aux soins hors domicile", (d.get("k7") == 1)),
            ("Recours dans les 24–48 h", (d.get("k7") == 1) & d.get("k9").isin([1, 2])),
        ]
        lib, val, bas, haut, eff = [], [], [], [], []
        for nom, m in etapes:
            m = m.fillna(False)
            v, b_, h_ = viz.wilson(int(m.sum()), len(d))
            lib.append(nom); val.append(v); bas.append(b_); haut.append(h_); eff.append(len(d))
        st.plotly_chart(viz.barres_proportions(lib, val, bas, haut, eff,
                        f"Cascade de prise en charge des cas de diarrhée (n = {len(d)})", p,
                        couleur=p["series"][2]), width="stretch")
        if "lieu_soins" in d and d["lieu_soins"].notna().any():
            s = d.loc[d.get("k7") == 1, "lieu_soins"].value_counts()
            if len(s):
                v = (s / s.sum()).tolist()
                st.plotly_chart(viz.barres_proportions(s.index.tolist(), v, v, v, s.tolist(),
                                "Premier recours aux soins", p, couleur=p["series"][0]),
                                width="stretch")

# 5 — connaissances ------------------------------------------------------------
with onglets[4]:
    if "score_connaissances" in df:
        dist = df["score_connaissances"].value_counts().sort_index()
        a, b = st.columns([2, 1])
        a.plotly_chart(viz.barres_distribution(dist.index.tolist(), dist.tolist(),
                       "Distribution du score de connaissances (0 à 8)", p,
                       xtitre="Score sur 8"), width="stretch")
        moy = df["score_connaissances"].mean()
        bon = (df["score_connaissances"] >= 6).mean()
        b.metric("Score moyen", f"{viz.fr(moy)} / 8")
        b.metric("Score ≥ 6/8", f"{viz.fr(bon*100, 0)} %")
        if "nb_signes_danger" in df:
            b.metric("Signes de danger cités (moyenne)", viz.fr(df['nb_signes_danger'].mean()))
        if "niveau_etudes" in df:
            par = df.groupby("niveau_etudes")["score_connaissances"].mean().sort_values(ascending=False)
            v = (par / 8).tolist()
            st.plotly_chart(viz.barres_proportions(par.index.tolist(), v, v, v,
                            df.groupby("niveau_etudes").size().reindex(par.index).tolist(),
                            "Score moyen de connaissances (en % du maximum) selon le niveau d'études du répondant", p,
                            couleur=p["series"][6]), width="stretch")

# 6 — données ------------------------------------------------------------------
with onglets[5]:
    colonnes = [c for c in ["_id", "jour", "aire_sante", "a5", "a6", "sexe", "b3", "tranche_age", "j1",
                            "k2", "k3", "k7", "score_biens", "score_connaissances", "duree_min"] if c in df]
    st.dataframe(df[colonnes], hide_index=True, width="stretch", height=460)
    tampon = io.BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="donnees")
    st.download_button("Télécharger les données filtrées (Excel)", tampon.getvalue(),
                       file_name=f"donnees_diarrhee_limete_{dt.date.today():%Y%m%d}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.download_button("Télécharger les données filtrées (CSV)", df.to_csv(index=False).encode("utf-8"),
                       file_name=f"donnees_diarrhee_limete_{dt.date.today():%Y%m%d}.csv", mime="text/csv")

st.caption(f"Dernière actualisation : {dt.datetime.now():%d/%m/%Y %H:%M} — "
           "source : KoboToolbox, formulaire kobo_diarrhee_limete_2026 (V3).")
