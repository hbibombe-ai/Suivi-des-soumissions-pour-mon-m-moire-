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
import tableaux
import theme
import viz

st.set_page_config(page_title="Diarrhée < 5 ans — ZS Limete", page_icon="💧",
                   layout="wide", initial_sidebar_state="expanded")

# Contrôle de cohérence : tous les fichiers du dépôt doivent provenir de la même version
VERSION_TDB = "5"
try:
    import nutrition
    import tableaux as _t
    _perimes = [nom for nom, mod in (("kobo.py", kobo), ("tableaux.py", _t), ("nutrition.py", nutrition), ("viz.py", viz))
                if getattr(mod, "VERSION_TDB", None) != VERSION_TDB]
except ImportError as _e:
    _perimes = [f"{_e.name}.py (fichier absent)"]
if _perimes:
    st.error("**Mise à jour incomplète du dépôt GitHub.** Ces fichiers ne correspondent pas à la version de `app.py` : "
             + ", ".join(f"`{f}`" for f in _perimes)
             + ". Remplacer **tous** les fichiers du dépôt par ceux du dernier zip (y compris `who_lms.csv`, "
             "`requirements.txt` et le formulaire `KoboCollect_XLSForm_Diarrhee_Limete_2026_V7.xlsx`), puis redéployer.")
    st.stop()

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
    if not demo and token and uid and not erreur and brut.empty:
        theme.entete(TITRE, SOUS_TITRE, [("Source", "Connecté — aucune fiche reçue", "alerte")])
        st.warning(
            "La connexion à KoboToolbox fonctionne, mais le projet ne renvoie **aucune fiche**. Causes possibles :\n\n"
            "1. **Fiche non envoyée** : dans KoboCollect, une fiche « finalisée » reste sur le téléphone tant qu'on "
            "n'a pas utilisé **Envoyer formulaire finalisé**. Vérifier qu'elle apparaît dans KoboToolbox → projet → *Données*.\n"
            "2. **Test dans l'aperçu** : les réponses saisies dans l'aperçu (« Preview ») de KoboToolbox ne sont pas enregistrées.\n"
            "3. **Mauvais projet** : l'identifiant du formulaire ne correspond pas au projet qui reçoit les fiches "
            "(par exemple, la V7 déployée comme nouveau projet).\n"
            "4. **Données mises en cache** : cliquer sur **Actualiser les données** après l'envoi.")
        try:
            info = kobo.tester_connexion(serveur, token, uid)
            st.caption(f"Projet lu : « {info['nom']} » — {info['soumissions']} soumission(s) déclarée(s) par KoboToolbox.")
        except Exception as e:  # noqa: BLE001
            st.caption(f"Métadonnées du projet indisponibles : {e}")
        st.stop()
    if not brut.empty:
        theme.entete(TITRE, SOUS_TITRE, [("Source", f"{len(brut)} fiche(s) reçue(s) — aucune éligible", "alerte")])
        st.warning(f"KoboToolbox a renvoyé **{len(brut)} fiche(s)**, mais aucune n'est retenue : le tableau de bord "
                   "n'affiche que les enfants **éligibles** (résidence dans la ZS de Limete depuis au moins 6 mois, "
                   "enfant de 0 à 59 mois, consentement). Le détail ci-dessous indique le motif pour chaque fiche.")
        st.dataframe(kobo.diagnostic(brut), hide_index=True, width="stretch")
        with st.expander("Variables reçues de KoboToolbox (diagnostic technique)"):
            st.write(sorted(kobo.aplatir(brut).columns.tolist()))
        st.stop()
    theme.entete(TITRE, SOUS_TITRE, [("Source", "En attente de connexion", "alerte")])
    st.info("Renseigner le jeton d'API et l'identifiant du formulaire dans la barre latérale, "
            "ou activer le mode démonstration pour explorer le tableau de bord.")
    st.stop()

chips = [("Fiches", f"{len(df)}", ""),
         ("Dernière donnée",
          f"{max([j for j in df['jour'].dropna()]):%d/%m/%Y}" if df["jour"].notna().any() else "—", ""),
         ("Aires couvertes", f"{df['aire_sante'].nunique() if 'aire_sante' in df else 0} / 11", ""),
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

sro, n_d = part("k4")
zinc, _ = part("k5")
sro_zinc = float(((d.get("k4") == 1) & (d.get("k5") == 1)).mean()) if len(d) else 0.0
recours, _ = part("k7")

def carte(col, titre, valeur, note, accent=None):
    theme.carte(col, titre, valeur, note, accent or p["series"][0])

theme.section("Indicateurs clés", "Proportions calculées sur les fiches sélectionnées, avec intervalle de confiance à 95 %.")
c = st.columns(7, gap="small")
carte(c[0], "Fiches éligibles", f"{n_tot}", f"{df['aire_sante'].nunique() if 'aire_sante' in df else 0} aire(s) de santé")
carte(c[1], "Prévalence diarrhée (14 j)", f"{viz.fr(prev*100)} %",
      f"IC 95 % : {viz.fr(prev_b*100)} – {viz.fr(prev_h*100)} %", p["series"][1])
carte(c[2], "Cas de diarrhée", f"{len(d)}", "enfants concernés")
carte(c[3], "SRO", f"{viz.fr(sro*100, 0)} %", f"des {n_d} cas", p["good"])
carte(c[4], "SRO + zinc", f"{viz.fr(sro_zinc*100, 0)} %", "prise en charge complète", p["good"])
carte(c[5], "Recours aux soins", f"{viz.fr(recours*100, 0)} %", "hors domicile", p["series"][0])
if "malnutrition_aigue_pb" in df and df["malnutrition_aigue_pb"].notna().any():
    ma = df["malnutrition_aigue_pb"].dropna()
    carte(c[6], "Malnutrition aiguë (PB/œdèmes)", f"{viz.fr(ma.mean()*100)} %", f"{int(ma.sum())} enfant(s) sur {len(ma)} mesurés", p["bad"])
else:
    carte(c[6], "Malnutrition aiguë (PB/œdèmes)", "—", "mesures non disponibles", p["bad"])
st.write("")

onglets = st.tabs(["Suivi de la collecte", "Profil épidémiologique", "Facteurs associés",
                   "Prise en charge", "Connaissances", "Tableaux du mémoire", "Données"])

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
    if "enqueteur" in df:
        pe = df.groupby("enqueteur").agg(fiches=("enqueteur", "size"),
                                  duree=("duree_min", "median") if "duree_min" in df else ("enqueteur", "size")).reset_index()
        pe = pe.sort_values("fiches", ascending=False)
        g3.plotly_chart(viz.barres_proportions(
            pe["enqueteur"].tolist(), (pe["fiches"] / pe["fiches"].sum()).tolist(),
            (pe["fiches"] / pe["fiches"].sum()).tolist(), (pe["fiches"] / pe["fiches"].sum()).tolist(),
            pe["fiches"].tolist(), "Répartition des fiches par enquêteur", p), width="stretch")
        if "duree_min" in df:
            g4.markdown("**Durée médiane d'entretien par enquêteur**")
            g4.dataframe(pe.rename(columns={"enqueteur": "Enquêteur", "fiches": "Fiches", "duree": "Durée médiane (min)"})
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

    if "emaciation" in df:
        st.markdown("**État nutritionnel des enfants** — normes de croissance de l'OMS (2006)")
        nut = []
        for nom, colonne in [("Émaciation (P/T < −2 z)", "emaciation"), ("Retard de croissance (T/A < −2 z)", "retard_croissance"),
                             ("Insuffisance pondérale (P/A < −2 z)", "insuffisance_ponderale"),
                             ("Malnutrition aiguë (PB < 125 mm ou œdèmes)", "malnutrition_aigue_pb")]:
            s_ = df[colonne].dropna()
            if len(s_):
                v_, b_, h_ = viz.wilson(int(s_.sum()), len(s_))
                nut.append((nom, v_, b_, h_, len(s_)))
        if nut:
            n1, n2 = st.columns([3, 2])
            n1.plotly_chart(viz.barres_proportions([x[0] for x in nut], [x[1] for x in nut], [x[2] for x in nut],
                            [x[3] for x in nut], [x[4] for x in nut], "Malnutrition chez les enfants de 0 à 59 mois — IC 95 %", p,
                            couleur=p["series"][7]), width="stretch")
            if df["emaciation"].notna().sum() and (df["emaciation"] == 1).any():
                pr = [(g, *viz.wilson(int((df.loc[df["emaciation"] == k, "j1"] == 1).sum()), int((df["emaciation"] == k).sum())),
                       int((df["emaciation"] == k).sum())) for g, k in (("Enfants émaciés", 1), ("Enfants non émaciés", 0))]
                n2.plotly_chart(viz.barres_proportions([x[0] for x in pr], [x[1] for x in pr], [x[2] for x in pr],
                                [x[3] for x in pr], [x[4] for x in pr], "Prévalence de la diarrhée selon l'émaciation", p,
                                couleur=p["series"][1]), width="stretch")
            st.caption("z-scores calculés dans l'application (méthode LMS de l'OMS, écart moyen avec WHO Anthro ≈ 0,005 z). "
                       "Pour les chiffres définitifs du mémoire, confirmer avec WHO Anthro.")

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
            ("SRO reçus", (d.get("k4") == 1)),
            ("Zinc reçu", (d.get("k5") == 1)),
            ("SRO + zinc", (d.get("k4") == 1) & (d.get("k5") == 1)),
            ("Alimentation maintenue ou augmentée", d.get("k3").isin([1, 2])),
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

# 6 — tableaux du mémoire -------------------------------------------------------
def afficher_tableau(titre, t, note=""):
    st.markdown(f"**{titre}**")
    vis = [c for c in t.columns if not c.startswith("_")]
    t_aff = t.copy()
    for c_ in vis:
        t_aff[c_] = t_aff[c_].astype(str).replace({"nan": ""})
    if "_niv" in t.columns:
        sty = t_aff.style.apply(lambda r: ["font-weight:700; background-color:rgba(127,127,127,.10)" if r["_niv"] == "h" else ""
                                       for _ in r], axis=1)
    else:
        sty = t_aff
    st.dataframe(sty, column_order=vis, hide_index=True, width="stretch",
                 height=min(38 * (len(t) + 1) + 4, 620))
    st.caption((note + " " if note else "") + "Source : enquête ménage, Zone de Santé de Limete, 2026.")
    EXPORT.append((titre, t, note))


EXPORT = []
with onglets[5]:
    st.markdown("Les tableaux du chapitre IV du mémoire, recalculés en direct sur les fiches sélectionnées "
                "(les filtres en haut de page s'appliquent). Le bouton en bas de page télécharge tous les tableaux "
                "dans un classeur Excel, un tableau par feuille, prêts à être copiés dans le mémoire.")
    V = tableaux.variables(df, dico)
    cat = tableaux.catalogue(V)
    sections = ["Participation et prévalence", "Caractéristiques", "Facteurs associés", "Modèle multivarié",
                "Prévention et connaissances", "Prise en charge"]
    choix_sec = st.segmented_control("Partie du chapitre Résultats", sections, default=sections[0],
                                     label_visibility="collapsed") or sections[0]

    # --- tableaux 5 à 7 (toujours calculés pour l'export)
    part_ = kobo.participation(brut)
    t5 = pd.DataFrame([
        {"Indicateur": "Fiches envoyées (ménages visités et enregistrés)", "Effectif": part_.get("soumises", 0)},
        *[{"Indicateur": f"   Non éligibles — {k}", "Effectif": v} for k, v in part_.get("detail_non_elig", {}).items()],
        {"Indicateur": "Refus de participation (EL4 = Non)", "Effectif": part_.get("refus", 0)},
        {"Indicateur": "Ménages enquêtés (fiches éligibles)", "Effectif": part_.get("enquetes", 0)},
        {"Indicateur": "Taux de participation parmi les éligibles (%)",
         "Effectif": viz.fr(100 * part_.get("enquetes", 0) / max(1, part_.get("enquetes", 0) + part_.get("refus", 0)))},
    ])
    k6 = int((df["j1"] == 1).sum())
    v6, b6, h6 = viz.wilson(k6, len(df))
    t6 = pd.DataFrame([
        {"Diarrhée au cours des 14 derniers jours": "Oui", "Effectif (n)": k6, "Pourcentage (%)": viz.fr(100 * v6),
         "IC à 95 %": f"{viz.fr(100 * b6)} – {viz.fr(100 * h6)}"},
        {"Diarrhée au cours des 14 derniers jours": "Non", "Effectif (n)": len(df) - k6,
         "Pourcentage (%)": viz.fr(100 - 100 * v6), "IC à 95 %": ""},
        {"Diarrhée au cours des 14 derniers jours": "Total", "Effectif (n)": len(df), "Pourcentage (%)": "100,0", "IC à 95 %": ""}])
    lignes7 = []
    for aire, g in df.groupby("aire_sante") if "aire_sante" in df else []:
        kk = int((g["j1"] == 1).sum()); vv, bb, hh = viz.wilson(kk, len(g))
        lignes7.append({"Aire de santé": aire, "Enfants enquêtés (n)": len(g), "Cas de diarrhée (n)": kk,
                        "Prévalence (%)": viz.fr(100 * vv), "IC à 95 %": f"{viz.fr(100 * bb)} – {viz.fr(100 * hh)}"})
    lignes7.append({"Aire de santé": "Total", "Enfants enquêtés (n)": len(df), "Cas de diarrhée (n)": k6,
                    "Prévalence (%)": viz.fr(100 * v6), "IC à 95 %": f"{viz.fr(100 * b6)} – {viz.fr(100 * h6)}"})
    t7 = pd.DataFrame(lignes7)
    n5 = ("Calculé sur toutes les fiches envoyées (filtres non appliqués). Les absences (ménage revisité) "
          "sont suivies sur la fiche papier de suivi des ménages et ne figurent pas dans Kobo.")

    def rendu(sec):
        return choix_sec == sec

    if rendu("Participation et prévalence"):
        afficher_tableau("Tableau 5 : Participation à l'enquête", t5, n5)
        afficher_tableau("Tableau 6 : Prévalence de la diarrhée au cours des 14 jours précédant l'enquête chez les enfants de 0 à 59 mois", t6,
                         "IC à 95 % : méthode de Wilson.")
        afficher_tableau("Tableau 7 : Prévalence de la diarrhée selon l'aire de santé", t7)
    else:
        EXPORT += [("Tableau 5 : Participation à l'enquête", t5, n5),
                   ("Tableau 6 : Prévalence de la diarrhée au cours des 14 jours précédant l'enquête chez les enfants de 0 à 59 mois", t6, ""),
                   ("Tableau 7 : Prévalence de la diarrhée selon l'aire de santé", t7, "")]

    for spec in cat:
        titre = f"Tableau {spec['num']} : {spec['titre']}"
        if spec["type"] == "desc":
            t = tableaux.tableau_descriptif(spec["vars"]); note = spec.get("note", "")
        else:
            t, _ = tableaux.tableau_bivarie(df, spec["vars"]); note = (spec.get("note", "") + " " + tableaux.NOTE_BIV).strip()
        sec = "Prévalence" if spec["section"] == "Prévalence" else spec["section"]
        affiche = rendu(sec) or (sec == "Prévalence" and rendu("Participation et prévalence"))
        if affiche:
            afficher_tableau(titre, t, note)
        else:
            EXPORT.append((titre, t, note))

    # --- expositions binaires : ORb (forêt) et modèle multivarié
    E = tableaux.expositions_binaires(df)
    if rendu("Facteurs associés"):
        st.markdown("---")
        lib, o_, lo_, hi_ = [], [], [], []
        for nom, s_ in E.items():
            ok = s_.notna() & df["j1"].isin([0, 1])
            a_ = int(((s_ == 1) & (df["j1"] == 1) & ok).sum()); b_ = int(((s_ == 1) & (df["j1"] == 0) & ok).sum())
            c_ = int(((s_ == 0) & (df["j1"] == 1) & ok).sum()); d_ = int(((s_ == 0) & (df["j1"] == 0) & ok).sum())
            if min(a_ + b_, c_ + d_) > 0:
                o, lo, hi = tableaux._or_ic(a_, b_, c_, d_)
                lib.append(nom); o_.append(o); lo_.append(lo); hi_.append(hi)
        if lib:
            ordre = sorted(range(len(o_)), key=lambda i: -o_[i])
            st.plotly_chart(viz.points_ratios([lib[i] for i in ordre], [o_[i] for i in ordre], [lo_[i] for i in ordre],
                                              [hi_[i] for i in ordre], "Odds ratios bruts de la diarrhée selon les principales expositions", p,
                                              xtitre="Odds ratio brut (échelle log.)", nom="ORb"), width="stretch")

    p_bi = {nom: tableaux.p_bivarie(df, s_) for nom, s_ in E.items()}
    defaut = [n_ for n_, pv in p_bi.items() if pv == pv and pv < 0.20]
    if rendu("Modèle multivarié"):
        st.markdown("**Choix des variables du modèle** — présélection automatique des expositions avec p < 0,20 "
                    "en analyse bivariée ; ajouter les variables importantes sur le plan conceptuel.")
        retenues = st.multiselect("Variables du modèle", list(E), default=defaut, label_visibility="collapsed")
        st.session_state["vars_modele"] = retenues
    retenues = st.session_state.get("vars_modele", defaut)
    t22, info = (tableaux.regression_logistique(df, {k: E[k] for k in retenues}) if retenues
                 else (pd.DataFrame(), {"erreur": "Aucune variable sélectionnée."}))
    n22 = ("ORa : odds ratio ajusté ; IC 95 % : intervalle de confiance à 95 %. "
           + (f"n = {info['n']} enfants, {info['cas']} cas. Hosmer-Lemeshow : χ² = {viz.fr(info['hl'][0], 2)} ; ddl = {info['hl'][1]} ; "
              f"p = {tableaux.fmt_p(info['hl'][2])}. Pseudo-R² de McFadden = {viz.fr(info['pseudo_r2'], 3)}." if "hl" in info else ""))
    titre22 = "Tableau 22 : Facteurs indépendamment associés à la diarrhée : régression logistique multivariée"
    if rendu("Modèle multivarié"):
        if "erreur" in info:
            st.warning(info["erreur"])
        else:
            afficher_tableau(titre22, t22, n22)
            st.plotly_chart(viz.points_ratios(t22["Variables (exposé vs non exposé)"].tolist(), t22["_ora"].tolist(),
                                              t22["_lo"].tolist(), t22["_hi"].tolist(), "Odds ratios ajustés (IC 95 %)", p,
                                              xtitre="Odds ratio ajusté (échelle log.)", nom="ORa"), width="stretch")
            st.caption("Modèle exploratoire : le modèle final du mémoire se construit pas à pas (confusion, interactions, "
                       "colinéarité) et, si le plan de sondage le justifie, en tenant compte de l'effet grappe.")
    elif "erreur" not in info:
        EXPORT.append((titre22, t22, n22))

    st.markdown("---")
    EXPORT.sort(key=lambda x: int(x[0].split()[1]))
    st.download_button("Télécharger tous les tableaux du mémoire (Excel)", tableaux.exporter_excel(EXPORT),
                       file_name=f"tableaux_resultats_diarrhee_limete_{dt.date.today():%Y%m%d}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

# 7 — données ------------------------------------------------------------------
with onglets[6]:
    colonnes = [c for c in ["_id", "jour", "aire_sante", "a6", "enqueteur", "sexe", "b3", "tranche_age", "j1",
                            "k4", "k5", "k7", "poids_final", "taille_final", "pb_final", "whz", "haz", "waz",
                            "score_biens", "score_connaissances", "duree_min"] if c in df]
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
           "source : KoboToolbox, formulaire kobo_diarrhee_limete_2026 (V7).")
