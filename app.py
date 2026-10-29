"""BRVM Portfolio — point d'entrée.  Lancer :  streamlit run app.py"""

import streamlit as st

from brvm import ui

st.set_page_config(page_title="BRVM Portfolio", page_icon="◆", layout="wide")

pages = [
    st.Page("views/accueil.py", title="Accueil", icon=":material/home:", default=True),
    st.Page("views/tutoriel.py", title="Tutoriel", icon=":material/school:"),
    st.Page("views/marche.py", title="Marché", icon=":material/candlestick_chart:"),
    st.Page("views/optimiseur.py", title="Profil et optimiseur", icon=":material/tune:"),
    st.Page("views/simulations.py", title="Simulations", icon=":material/insights:"),
    st.Page("views/portefeuille.py", title="Mon portefeuille", icon=":material/account_balance_wallet:"),
    st.Page("views/veille.py", title="Veille", icon=":material/radar:"),
    st.Page("views/documents.py", title="Documents officiels", icon=":material/description:"),
    st.Page("views/reglages.py", title="Réglages", icon=":material/settings:"),
]
nav = st.navigation(pages)

ui.brand()
ui._init_db()
ui.sidebar()
nav.run()
ui.footer()
