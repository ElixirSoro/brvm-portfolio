"""Page Administration : maintenance des comptes utilisateurs (réservée aux administrateurs)."""

# DÉROGATION règle 4 : page Streamlit exécutée de haut en bas à chaque interaction ;
# les règles d'accès et les écritures sont dans brvm/admin.py.
import streamlit as st

from brvm import admin, db, ui

ui.setup(
    "Administration",
    "Comptes utilisateurs",
    "Maintenance des comptes : mot de passe provisoire, suspension, suppression et droits d'administration. "
    "Le contenu des portefeuilles reste privé : seuls leur nombre et celui des opérations apparaissent ici.",
)
current = ui.current_user()
if current is None or not current.is_admin:
    st.error("Page réservée aux administrateurs.")
    st.stop()
assert current is not None  # st.stop() a interrompu la page sinon
actor = current

ERRORS: tuple[type[Exception], ...] = (ValueError, PermissionError, *db.DB_ERRORS)
acc = admin.accounts(actor)
ui.metric_cards(
    [
        (ui.nb(len(acc)), "comptes", True),
        (ui.nb(int(acc["suspended"].sum()) if not acc.empty else 0), "suspendus", False),
        (ui.nb(int(acc["admin"].sum()) if not acc.empty else 0), "administrateurs", False),
        (ui.nb(int(acc["portfolios"].sum()) if not acc.empty else 0), "portefeuilles", False),
    ]
)
if acc.empty:
    st.info("Aucun compte pour l'instant.")
    st.stop()

st.dataframe(
    acc[["email", "created", "last_login", "portfolios", "operations", "suspended", "admin"]].rename(
        columns={
            "email": "E-mail",
            "created": "Créé le",
            "last_login": "Dernière connexion",
            "portfolios": "Portefeuilles",
            "operations": "Opérations",
            "suspended": "Suspendu",
            "admin": "Administrateur",
        }
    ),
    hide_index=True,
    width="stretch",
)

ui.section("Maintenance", "Agir sur un compte")
others = acc[acc["id"] != actor.id]
if others.empty:
    st.info("Aucun autre compte que le tien.")
    st.stop()
uid = st.selectbox("Compte", others["id"], format_func=lambda i: others.set_index("id").loc[i, "email"])
row = others.set_index("id").loc[uid]
c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("**Mot de passe oublié**")
    if st.button("Créer un mot de passe provisoire", icon=":material/key:"):
        try:
            temp = admin.reset_password(actor, uid)
            st.success("Transmets ce mot de passe à l'utilisateur ; il pourra se connecter tout de suite :")
            st.code(temp, language=None)
        except ERRORS as e:
            st.error(str(e))

with c2:
    st.markdown("**Accès**")
    label = "Réactiver le compte" if row["suspended"] else "Suspendre le compte"
    if st.button(label, icon=":material/block:"):
        try:
            admin.suspend(actor, uid, not row["suspended"])
            st.rerun()
        except ERRORS as e:
            st.error(str(e))
    rights = "Retirer les droits d'administration" if row["admin"] else "Nommer administrateur"
    if st.button(rights, icon=":material/shield_person:"):
        try:
            admin.set_admin(actor, row["email"], not row["admin"])
            st.rerun()
        except ERRORS as e:
            st.error(str(e))

with c3:
    st.markdown("**Suppression définitive**")
    typed = st.text_input("Recopie l'e-mail du compte pour confirmer", key="confirm_delete")
    if st.button("Supprimer le compte et ses données", icon=":material/delete_forever:", disabled=typed != row["email"]):
        try:
            admin.delete_account(actor, uid)
            st.success(f"Compte {row['email']} supprimé.")
            st.rerun()
        except ERRORS as e:
            st.error(str(e))
