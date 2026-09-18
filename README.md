# Tableau de bord — Diarrhée chez les enfants de moins de 5 ans, ZS de Limete

Visualisation dynamique des données collectées avec **KoboCollect** (formulaire
`kobo_diarrhee_limete_2026`, version V3). Le tableau de bord lit les soumissions
**en direct** via l'API REST de KoboToolbox : aucune exportation manuelle n'est nécessaire.

## 1. Contenu du dépôt

| Fichier | Rôle |
|---|---|
| `app.py` | Application Streamlit (interface, filtres, onglets) |
| `theme.py` | Habillage : bandeau de titre, cartes d'indicateurs, onglets, listes déroulantes |
| `kobo.py` | Connexion à l'API KoboToolbox, dictionnaire des variables, préparation des données |
| `viz.py` | Thème graphique, intervalles de confiance, ratios de prévalence, graphiques |
| `KoboCollect_XLSForm_Diarrhee_Limete_2026_V3.xlsx` | Le formulaire : sert de dictionnaire (codes → libellés) |
| `requirements.txt` | Dépendances Python |
| `.streamlit/config.toml` | Thème de l'interface |
| `.streamlit/secrets.toml.example` | Modèle de configuration des accès (Streamlit Cloud) |
| `config_kobo.py` | Connexion enregistrée une fois pour toutes (usage local) — jamais sur GitHub |

## 2. Obtenir les paramètres de connexion

1. **Jeton d'API** : KoboToolbox → votre compte (en haut à droite) → **Paramètres du compte** → **Sécurité** → *Jeton d'API*. Copier la chaîne affichée.
2. **Identifiant du formulaire (asset UID)** : ouvrir le projet ; l'URL contient `/forms/aXXXXXXXXXXXX/` — c'est cet identifiant.
3. **Serveur** : `https://eu.kobotoolbox.org` (serveur européen) ou `https://kf.kobotoolbox.org`.

Le compte utilisé doit avoir au minimum le droit **« Voir les soumissions »** sur le projet.

### Enregistrer la connexion une fois pour toutes

Le tableau de bord lit les paramètres dans cet ordre, et n'affiche les champs de saisie
que s'il ne trouve rien :

| Où | Quand l'utiliser |
|---|---|
| **Secrets de Streamlit Cloud** | application en ligne — voir section 4 |
| **`config_kobo.py`** | sur votre ordinateur : ouvrir le fichier, coller le jeton et l'identifiant, enregistrer |
| **Variables d'environnement** `KOBO_TOKEN`, `KOBO_ASSET_UID`, `KOBO_SERVER` | serveur ou poste partagé |

Une fois l'un de ces trois moyens renseigné, la connexion est automatique à chaque
ouverture ; la barre latérale affiche simplement « Connecté » et un volet repliable
permet de changer ponctuellement de projet.

> **Sécurité.** Le jeton donne accès à *tout* votre compte KoboToolbox, y compris aux
> données nominatives des ménages enquêtés. Il ne doit donc jamais être écrit dans un
> fichier publié sur GitHub : `config_kobo.py` et `.streamlit/secrets.toml` sont pour
> cette raison listés dans `.gitignore`. Si un jeton a été exposé par erreur, le
> régénérer immédiatement dans KoboToolbox (l'ancien cesse alors de fonctionner).

## 3. Utilisation en local

```bash
pip install -r requirements.txt
# ouvrir config_kobo.py et y coller le jeton d'API et l'identifiant du formulaire
streamlit run app.py
```

Sans jeton, l'application démarre en **mode démonstration** avec des données fictives :
utile pour présenter le tableau de bord avant le début de la collecte.

## 4. Mise en ligne (Streamlit Community Cloud, gratuit)

1. Créer un dépôt **GitHub** et y pousser ces fichiers — **sans** `secrets.toml`.
2. Aller sur [share.streamlit.io](https://share.streamlit.io) → *New app* → choisir le dépôt, la branche et `app.py`.
3. Dans **Settings → Secrets**, coller le contenu de `secrets.toml.example` complété.
4. Déployer. L'application est accessible par un lien à partager avec l'équipe.

Pour restreindre l'accès : Streamlit Cloud permet de limiter l'application à des adresses e-mail autorisées.

## 5. Ce que montre le tableau de bord

- **Cartes de synthèse** : fiches éligibles, prévalence de la diarrhée sur 14 jours avec IC 95 %, nombre de cas, SRO, SRO + zinc, recours aux soins.
- **Suivi de la collecte** : fiches par jour, cumul, répartition et durée médiane d'entretien par enquêteur.
- **Profil épidémiologique** : prévalence par aire de santé, par tranche d'âge et selon le sexe, avec intervalles de confiance de Wilson.
- **Facteurs associés** : niveaux de service WASH selon l'échelle JMP, et ratios de prévalence bruts (graphique en forêt + tableau) pour les expositions clés — inondation, eaux stagnantes, eau non améliorée, latrine partagée, absence de savon, surpeuplement.
- **Prise en charge** : cascade SRO / zinc / liquides / alimentation / recours aux soins, et premier lieu de recours.
- **Connaissances** : distribution du score sur 8, score moyen, score selon le niveau d'études du répondant.
- **Données** : tableau filtrable et export Excel ou CSV des données filtrées.

## 6. Apparence

L'interface suit le thème défini dans `.streamlit/config.toml` :

- **mode clair** : configuration livrée par défaut ;
- **mode sombre** : remplacer le bloc `[theme]` par le bloc commenté juste en dessous dans ce fichier.

Interface, listes déroulantes, tableaux et graphiques basculent ensemble. Sur Streamlit Cloud,
il suffit de modifier le fichier : l'application se redéploie automatiquement.

## 7. Notes méthodologiques

- Les proportions sont accompagnées d'un **intervalle de confiance à 95 % (méthode de Wilson)**, adapté aux petits effectifs.
- Les **ratios de prévalence** sont bruts, non ajustés (IC selon la méthode de Katz) : ils servent à explorer les données pendant la collecte, pas à conclure. L'analyse finale passe par la régression prévue au protocole.
- Seules les fiches avec `eligible = 1` (consentement, résidence et enfant éligible) sont retenues.
- Les données sont mises en cache **5 minutes** ; le bouton *Actualiser* force la relecture.

## 8. Adapter le tableau de bord

- Le formulaire évolue ? Remplacer le fichier XLSForm du dépôt : les libellés des questions et des modalités suivent automatiquement.
- Ajouter un indicateur : le calculer dans `kobo.preparer()`, puis l'afficher dans l'onglet voulu de `app.py`.
- La palette de couleurs (modes clair et sombre) est dans `viz.py` ; l'habillage de l'interface dans `theme.py`.
