"""Page Réglages : historique, grille de frais, IRVM, dividendes, clé IA, flux RSS."""

# DÉROGATION règle 4 : page Streamlit exécutée de haut en bas à chaque interaction ;
# la logique est dans le paquet brvm, la page ne fait qu'afficher.
from pathlib import Path

import pandas as pd
import streamlit as st

from brvm import config, db, fees, ui
from brvm.bots import sources
from brvm.data import loader, sika

WHERE = "dans ta base Supabase (en ligne, privée)" if db.engine() == "postgres" else "sur ton ordinateur, dans data/brvm.db"
ui.setup("Réglages", "Données, frais et sources", f"Tout ce qui est enregistré ici reste {WHERE}.")

# ---------------- données ----------------
ui.section("Données", "Cours de bourse")
n = db.df("SELECT COUNT(*) AS n, COUNT(DISTINCT ticker) AS t, MIN(date) AS a, MAX(date) AS b FROM prices").iloc[0]
st.markdown(
    f'<p class="elx-sub">En base : <span class="elx-num">{ui.nb(n["n"])}</span> cours, '
    f'<span class="elx-num">{n["t"]}</span> valeurs, du <span class="elx-num">{n["a"] or "—"}</span> '
    f'au <span class="elx-num">{n["b"] or "—"}</span></p>',
    unsafe_allow_html=True,
)
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Importer l'historique de Cote_scrapper**")
    path = st.text_input("Dossier BRVM_DATA_SCRAP", str(config.SCRAP_DIR))
    if st.button("Importer ce dossier", icon=":material/upload_file:"):
        with st.spinner("Import…"):
            r = loader.import_scrap_dir(Path(path).expanduser())
        st.cache_data.clear()
        (st.success if r["rows"] else st.error)(f"{ui.nb(r['rows'])} cours importés pour {r['tickers']} valeurs. {r['message']}")
with c2:
    st.markdown("**Télécharger depuis Sika Finance**")
    years = st.slider("Années d'historique (premier téléchargement)", 1, 15, 10)
    if st.button("Télécharger / compléter l'historique", icon=":material/cloud_download:"):
        bar = st.progress(0.0, "Téléchargement…")
        r = sika.update_history(years=years, progress=lambda p, t: bar.progress(p, f"{t}"))
        st.cache_data.clear()
        st.success(f"{r['ok']} séries à jour, {ui.nb(r['rows'])} lignes.")
        if r["errors"]:
            st.warning("Erreurs : " + " · ".join(r["errors"][:5]))

# ---------------- frais ----------------
ui.section("Frais", "Ta grille de frais SGI")
st.caption("Recopie la grille de ta SGI : elle sert au portefeuille virtuel, à l'optimiseur et aux simulations.")
f = fees.current_fees()
labels = {
    "courtage_pct": "Courtage SGI (% du montant)",
    "courtage_min": "Courtage minimum par ordre (F)",
    "brvm_pct": "Commission BRVM (%)",
    "dcbr_pct": "Commission DC/BR (%)",
    "amf_pct": "Redevance AMF-UMOA (%)",
    "tva_courtage_pct": "TVA sur le courtage (%)",
    "garde_annuel_pct": "Droits de garde annuels (%)",
}
cols = st.columns(4)
new = {}
for i, (k, lab) in enumerate(labels.items()):
    new[k] = cols[i % 4].number_input(lab, 0.0, 100_000.0, float(f[k]), 0.05 if "pct" in k else 500.0, key=k)
ex = fees.order_fees(500_000, new)
st.markdown(
    f'Exemple : un achat de <span class="elx-num">500 000 F</span> coûte <span class="elx-num">{ui.fcfa(ex.total)}</span> '
    f'de frais, soit <span class="elx-num">{ui.pct(ex.rate, 2)}</span> ; un aller-retour '
    f'<span class="elx-num">{ui.pct(2 * ex.rate, 2)}</span>.',
    unsafe_allow_html=True,
)
irvm = db.get_setting("irvm", config.DEFAULT_IRVM)
st.markdown("**IRVM sur dividendes, par pays de l'émetteur (%)**")
ir_cols = st.columns(8)
new_irvm = {
    c: ir_cols[i].number_input(c.upper(), 0.0, 50.0, float(irvm.get(c, 10.0)), 0.5, key=f"irvm_{c}")
    for i, c in enumerate(config.DEFAULT_IRVM)
}
if st.button("Enregistrer les frais", type="primary"):
    db.set_setting("fees", new)
    db.set_setting("irvm", new_irvm)
    st.cache_data.clear()
    st.toast("Frais enregistrés.")

# ---------------- dividendes ----------------
ui.section("Dividendes", "Calendrier des dividendes")
st.caption("is_gross = 1 si le montant publié est brut (l'IRVM sera déduit). À compléter à chaque saison (avril–septembre).")
div = (
    pd.read_csv(loader.DIVIDENDS_CSV)
    if loader.DIVIDENDS_CSV.exists()
    else pd.DataFrame(columns=["ticker", "ex_date", "pay_date", "amount", "is_gross"])
)
edited = st.data_editor(div, num_rows="dynamic", width="stretch", height=300)
if st.button("Enregistrer le calendrier"):
    edited.to_csv(loader.DIVIDENDS_CSV, index=False)
    db.execute("DELETE FROM dividends")
    loader.load_dividends()
    st.cache_data.clear()
    st.toast(f"{len(edited)} dividendes enregistrés.")

# ---------------- veille ----------------
ui.section("Veille", "Clé IA et sources")
if config.ANTHROPIC_API_KEY:
    st.success(f"Clé API Claude détectée · modèle {config.ANTHROPIC_MODEL}")
else:
    st.info(
        "Pas de clé API : les bots notent les articles par mots-clés. Pour l'analyse par IA, crée une clé sur "
        "console.anthropic.com, puis écris dans le fichier `.env` du projet : `ANTHROPIC_API_KEY=sk-ant-...` "
        "et relance l'application."
    )
st.markdown(
    f"**{len(sources.google_news_feeds())} recherches Google Actualités** générées depuis la carte des facteurs "
    "(`brvm/bots/exposures.py`)."
)
rss = sources.RSS_FILE.read_text(encoding="utf-8") if sources.RSS_FILE.exists() else sources.DEFAULT_RSS
txt = st.text_area("Flux RSS supplémentaires (une URL par ligne)", rss, height=140)
if st.button("Enregistrer les flux"):
    sources.RSS_FILE.write_text(txt, encoding="utf-8")
    st.toast("Flux enregistrés.")
