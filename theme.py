"""Feuille de style de l'interface (mode clair / sombre) et composants d'habillage."""
from __future__ import annotations
import streamlit as st
import viz

def _vars(p: dict, sombre: bool) -> str:
    fond = "#1a1a19" if sombre else "#fcfcfb"
    panneau = "#222220" if sombre else "#ffffff"
    bordure = p["grid"]
    return f"""
      --fond:{fond}; --panneau:{panneau}; --bordure:{bordure};
      --texte:{p['text']}; --texte2:{p['text2']}; --muted:{p['muted']};
      --accent:{p['series'][0]}; --accent2:{p['series'][1]}; --ok:{p['good']};
    """

CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root { __VARS__ }

html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
button, input, textarea, select, p, span, label, h1, h2, h3, h4, li, td, th {
  font-family: 'Inter', 'Segoe UI', system-ui, sans-serif !important;
}
/* ne jamais écraser la police des icônes Material de Streamlit */
[data-testid="stIconMaterial"], .material-icons, .material-symbols-rounded,
span[class*="material-symbols"], span[class*="material-icons"] {
  font-family: 'Material Symbols Rounded', 'Material Icons' !important;
}
[data-testid="stToolbar"], [data-testid="stDecoration"] { display: none; }
[data-testid="stSidebar"] { border-right: 1px solid var(--bordure); }
button[kind="primary"], button[kind="primary"] * { color: #fff !important; background: var(--accent) !important; border: none !important; }
button[kind="primary"]:hover { filter: brightness(1.08); }
[data-testid="stSidebar"] h3 {
  color: var(--texte); font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
  font-weight: 700; margin: 4px 0 2px;
}
.block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1500px; }
h1, h2, h3, h4, p, span, label, li { color: var(--texte); }
#MainMenu, footer { visibility: hidden; }

/* --- marque (barre latérale) --- */
.marque { display: flex; gap: 10px; align-items: center; padding: 6px 2px 14px; border-bottom: 1px solid var(--bordure); margin-bottom: 10px; }
.marque .ico { font-size: 22px; line-height: 1; }
.marque .txt { font-size: 13.5px; font-weight: 700; color: var(--texte) !important; line-height: 1.25; }
.marque em { display: block; font-size: 11px; font-weight: 500; font-style: normal; color: var(--muted) !important; margin-top: 2px; }

/* --- bandeau de titre --- */
.entete {
  background: var(--panneau); border: 1px solid var(--bordure); border-radius: 14px;
  padding: 18px 22px; margin-bottom: 14px; position: relative; overflow: hidden;
}
.entete::before {
  content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
  background: linear-gradient(180deg, var(--accent), var(--accent2));
}
.entete h1 { font-size: 21px; font-weight: 700; margin: 0 0 4px; line-height: 1.3; letter-spacing: -.01em; }
.entete p { font-size: 13px; color: var(--texte2); margin: 0; }
.chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.chip {
  font-size: 11.5px; font-weight: 600; color: var(--texte2); background: var(--fond);
  border: 1px solid var(--bordure); border-radius: 999px; padding: 4px 11px; white-space: nowrap;
}
.chip b { color: var(--texte); font-weight: 700; }
.chip.alerte { color: __WARN__; border-color: __WARN__55; }
.chip.direct { color: __GOOD__; border-color: __GOOD__55; }

/* --- cartes d'indicateurs --- */
.carte {
  background: var(--panneau); border: 1px solid var(--bordure); border-radius: 12px;
  padding: 13px 15px 12px; height: 100%; min-height: 124px; display: flex; flex-direction: column;
  transition: border-color .15s ease, transform .15s ease;
}
.carte .n { margin-top: auto; }
.carte:hover { border-color: var(--accent); transform: translateY(-1px); }
.carte .k {
  font-size: 10.5px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase;
  color: var(--muted); margin-bottom: 6px; display: block; line-height: 1.35; min-height: 28px;
}
.carte .v { font-size: 27px; font-weight: 700; line-height: 1.1; font-variant-numeric: tabular-nums; }
.carte .n { font-size: 11.5px; color: var(--texte2); margin-top: 4px; display: block; }

/* --- titres de section --- */
.section { margin: 18px 0 6px; }
.section .t { font-size: 15.5px; font-weight: 700; color: var(--texte); }
.section .s { font-size: 12.5px; color: var(--texte2); margin-top: 2px; }

/* --- onglets --- */
[data-testid="stTabs"] [role="tablist"] { gap: 4px; border-bottom: 1px solid var(--bordure); }
[data-testid="stTabs"] [role="tab"] {
  padding: 8px 14px; border-radius: 8px 8px 0 0; font-size: 13.5px; font-weight: 600; color: var(--texte2);
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] { color: var(--accent); background: var(--panneau); }

/* --- conteneurs de graphiques --- */
[data-testid="stVerticalBlockBorderWrapper"] > div:has(> [data-testid="stVerticalBlock"]) { border-radius: 12px; }
div[data-testid="stExpander"], div[data-testid="stDataFrame"] { border-radius: 10px; }
.js-plotly-plot .plotly .modebar { opacity: .25; }
.js-plotly-plot .plotly .modebar:hover { opacity: 1; }

/* --- listes déroulantes et filtres --- */
[data-baseweb="select"] > div {
  border: 1px solid var(--bordure) !important; border-radius: 10px !important;
  min-height: 40px; font-size: 13.5px; transition: border-color .15s ease;
}
[data-baseweb="select"] > div:hover { border-color: var(--accent) !important; }
[data-baseweb="select"] > div:focus-within {
  border-color: var(--accent) !important; box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent) !important;
}
[data-baseweb="select"] svg { fill: var(--muted) !important; }
/* étiquettes des choix multiples */
[data-baseweb="tag"] {
  background: color-mix(in srgb, var(--accent) 12%, var(--panneau)) !important;
  border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent) !important;
  border-radius: 8px !important; color: var(--accent) !important; font-size: 12px !important; font-weight: 600;
}
[data-baseweb="tag"] span, [data-baseweb="tag"] svg { color: var(--accent) !important; fill: var(--accent) !important; }
/* menu déroulant ouvert */
[data-baseweb="popover"] [role="listbox"], [data-baseweb="menu"] {
  border: 1px solid var(--bordure) !important; border-radius: 10px !important;
  box-shadow: 0 12px 34px rgba(0,0,0,.18) !important; padding: 4px !important;
}
[role="option"] { font-size: 13.5px !important; border-radius: 7px !important; margin: 1px 2px !important; padding: 8px 10px !important; }
[role="option"]:hover, [role="option"][aria-selected="true"] {
  background: color-mix(in srgb, var(--accent) 12%, transparent) !important; color: var(--accent) !important;
}
/* barre de filtres */
.barre-filtres { background: var(--panneau); border: 1px solid var(--bordure); border-radius: 12px; padding: 6px 14px 2px; margin-bottom: 10px; }
.filtre-titre { font-size: 10.5px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; color: var(--muted); margin-bottom: 2px; }
[data-testid="stWidgetLabel"] p { font-size: 11.5px !important; font-weight: 600; color: var(--texte2) !important; }
[data-testid="stDateInput"] input, [data-testid="stTextInput"] input { font-size: 13.5px !important; }
[data-testid="stDateInput"] > div > div, [data-testid="stTextInput"] > div > div { border-radius: 10px !important; }
button[kind="secondary"], button[kind="primary"] { border-radius: 10px !important; font-weight: 600; font-size: 13px; }

/* --- champs de saisie --- */
[data-testid="stExpander"] summary span, [data-testid="stExpander"] summary p { font-size: 13px; font-weight: 600; }
[data-testid="stExpander"] details { border-radius: 10px; border-color: var(--bordure) !important; }

/* --- graphiques en carte --- */
[data-testid="stPlotlyChart"] {
  background: var(--panneau); border: 1px solid var(--bordure); border-radius: 12px;
  padding: 10px 14px 6px; margin-bottom: 6px;
}
[data-testid="stDataFrame"] { border: 1px solid var(--bordure); border-radius: 12px; overflow: hidden; }

/* --- divers --- */
.pdp { font-size: 11.5px; color: var(--muted); margin-top: 2px; }
hr { border-color: var(--bordure); }
</style>"""


def appliquer(sombre: bool) -> None:
    """Injecte la feuille de style adaptée au mode clair ou sombre."""
    p = viz.palette(sombre)
    css = (CSS.replace("__VARS__", _vars(p, sombre))
              .replace("__WARN__", p["warn"])
              .replace("__GOOD__", p["good"]))
    st.markdown(css, unsafe_allow_html=True)


def entete(titre: str, sous_titre: str, chips: list[tuple[str, str, str]]) -> None:
    """Bandeau de titre avec pastilles d'état : (libellé, valeur, style)."""
    html = "".join(f'<span class="chip {cls}">{lib} <b>{val}</b></span>' for lib, val, cls in chips)
    st.markdown(f'<div class="entete"><h1>{titre}</h1><p>{sous_titre}</p>'
                f'<div class="chips">{html}</div></div>', unsafe_allow_html=True)


def carte(col, titre: str, valeur: str, note: str, couleur: str) -> None:
    col.markdown(f'<div class="carte"><span class="k">{titre}</span>'
                 f'<div class="v" style="color:{couleur}">{valeur}</div>'
                 f'<span class="n">{note}</span></div>', unsafe_allow_html=True)


def section(titre: str, sous_titre: str = "") -> None:
    s = f'<div class="s">{sous_titre}</div>' if sous_titre else ""
    st.markdown(f'<div class="section"><div class="t">{titre}</div>{s}</div>', unsafe_allow_html=True)
