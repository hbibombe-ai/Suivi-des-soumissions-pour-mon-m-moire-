"""Partage du tableau de bord : lien, lien vers la vue filtrée, QR code, WhatsApp, e-mail, SMS.

L'adresse publique de l'application est lue dans les Secrets (`[app] url = "https://…streamlit.app"`) ;
à défaut, elle est déduite de l'adresse ouverte dans le navigateur.
"""
from __future__ import annotations

VERSION_TDB = "6"  # doit correspondre à app.py
import io
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

import streamlit as st

SEP = "|"  # séparateur des valeurs multiples dans l'adresse


def url_application() -> str:
    try:
        u = st.secrets["app"]["url"]
        if u:
            return str(u).rstrip("/")
    except Exception:  # noqa: BLE001 — pas de secrets
        pass
    try:
        u = st.context.url or ""
    except Exception:  # noqa: BLE001 — version de Streamlit trop ancienne
        u = ""
    parts = urlsplit(u)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")).rstrip("/") if u else ""


# ------------------------------------------------------------ filtres ↔ adresse
def lire_liste(cle: str) -> list[str]:
    v = st.query_params.get(cle, "")
    return [x for x in v.split(SEP) if x] if v else []


def lire_texte(cle: str, defaut: str = "") -> str:
    return st.query_params.get(cle, defaut)


def ecrire_filtres(filtres: dict) -> None:
    """Reporte les filtres courants dans l'adresse du navigateur (sans recharger la page)."""
    voulu = {k: (SEP.join(v) if isinstance(v, (list, tuple)) else str(v)) for k, v in filtres.items() if v not in (None, "", [], ())}
    actuel = {k: st.query_params.get(k) for k in st.query_params.keys()}
    if voulu != actuel:
        st.query_params.clear()
        st.query_params.update(voulu)


def lien(base: str, filtres: dict | None) -> str:
    if not base:
        return ""
    if not filtres:
        return base
    q = {k: (SEP.join(v) if isinstance(v, (list, tuple)) else str(v)) for k, v in filtres.items() if v not in (None, "", [], ())}
    return f"{base}/?{urlencode(q)}" if q else base


def qr_png(texte: str) -> bytes | None:
    try:
        import qrcode
    except ImportError:
        return None
    img = qrcode.make(texte, box_size=8, border=2)
    tampon = io.BytesIO()
    img.save(tampon, format="PNG")
    return tampon.getvalue()


# ---------------------------------------------------------------- panneau
def panneau(filtres: dict, resume: str, titre_app: str) -> None:
    """Bloc « Partager » de la barre latérale."""
    base = url_application()
    with st.expander("🔗 Partager le tableau de bord", expanded=False):
        if not base:
            st.info("Adresse de l'application inconnue : déployez-la sur Streamlit Cloud, puis indiquez "
                    "son adresse dans les Secrets (`[app] url = \"https://….streamlit.app\"`).")
            return
        avec_filtres = st.toggle("Partager la vue filtrée", value=bool(filtres),
                                 help="Le destinataire ouvrira le tableau de bord avec les mêmes filtres "
                                      "(période, aires, sexe, tranches d'âge).")
        url = lien(base, filtres if avec_filtres else None)
        st.code(url, language=None, wrap_lines=True)
        st.caption("Bouton de copie en haut à droite du cadre.")
        message = f"{titre_app}\n{resume}\n\nTableau de bord : {url}"
        st.link_button("Envoyer par WhatsApp", f"https://wa.me/?text={quote(message)}", icon=":material/chat:", width="stretch")
        st.link_button("Envoyer par e-mail", f"mailto:?subject={quote(titre_app)}&body={quote(message)}", icon=":material/mail:", width="stretch")
        st.link_button("Envoyer par SMS", f"sms:?&body={quote(message)}", icon=":material/sms:", width="stretch")
        png = qr_png(url)
        if png:
            st.image(png, caption="QR code à projeter en réunion ou à imprimer", width=180)
            st.download_button("Télécharger le QR code", png, file_name="qr_tableau_de_bord_diarrhee_limete.png",
                               mime="image/png", width="stretch")
        st.caption("⚠️ Le lien ne donne accès aux données que si l'application l'autorise : sur Streamlit Cloud, "
                   "*Share* → réservez l'accès aux adresses e-mail invitées. Les données contiennent des positions GPS "
                   "de ménages : ne rendez pas l'application publique.")
