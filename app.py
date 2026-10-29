"""BRVM Portfolio — point d'entrée.  Lancer :  streamlit run app.py"""

import streamlit as st

from brvm import auth, ui

st.set_page_config(page_title=ui.APP_NAME, page_icon="◆", layout="wide")

PAGES = [
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
LOGIN = [st.Page("views/connexion.py", title="Connexion", icon=":material/login:", default=True)]

ui.brand()
ui._init_db()
user = ui.current_user()
signed_out = auth.enabled() and user is None
# chaque exécution fixe le propriétaire des données personnelles avant d'afficher quoi que ce soit
auth.set_owner(user.id if user else auth.LOCAL_OWNER)
nav = st.navigation(LOGIN if signed_out else PAGES)
if not signed_out:
    ui.sidebar()
    ui.account_box()
nav.run()
ui.footer()
