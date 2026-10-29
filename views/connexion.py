"""Page Connexion : se connecter ou créer un compte pour accéder à son propre espace."""

# DÉROGATION règle 4 : page Streamlit exécutée de haut en bas à chaque interaction.
import streamlit as st

from brvm import auth, ui

ui.setup(
    "Connexion",
    f"Bienvenue sur {ui.APP_NAME}",
    "Chaque compte a son propre espace : tes portefeuilles, tes opérations et ta grille de frais ne sont visibles "
    "que par toi. Les cours, les documents officiels et la veille sont communs à tous.",
)

tab_in, tab_up = st.tabs(["Se connecter", "Créer un compte"])

with tab_in, st.form("connexion"):
    email = st.text_input("E-mail", autocomplete="email")
    password = st.text_input("Mot de passe", type="password", autocomplete="current-password")
    if st.form_submit_button("Se connecter", type="primary"):
        try:
            ui.remember(auth.sign_in(email, password))
            st.rerun()
        except auth.AuthError as e:
            st.error(str(e))

with tab_up, st.form("inscription"):
    new_email = st.text_input("E-mail", key="new_email", autocomplete="email")
    new_pw = st.text_input(
        f"Mot de passe ({auth.MIN_PASSWORD} caractères minimum)", type="password", key="new_pw",
        autocomplete="new-password",
    )  # fmt: skip
    confirm = st.text_input("Confirme le mot de passe", type="password", key="confirm_pw", autocomplete="new-password")
    if st.form_submit_button("Créer mon compte", type="primary"):
        if new_pw != confirm:
            st.error("Les deux mots de passe ne sont pas identiques.")
        else:
            try:
                user = auth.sign_up(new_email, new_pw)
                if user is None:
                    st.success("Compte créé : ouvre le lien reçu par e-mail pour le confirmer, puis connecte-toi.")
                else:
                    ui.remember(user)
                    st.rerun()
            except auth.AuthError as e:
                st.error(str(e))
