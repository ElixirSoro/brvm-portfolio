"""Maintenance des comptes (version en ligne), réservée aux administrateurs.

Contrat
- Chaque fonction reçoit l'administrateur qui agit (`actor`) et lève PermissionError s'il n'en est pas un.
- accounts() : un compte par ligne (e-mail, dates, suspendu, administrateur, nombre de portefeuilles et
  d'opérations) ; le contenu des portefeuilles reste privé.
- reset_password() renvoie un mot de passe provisoire à transmettre à l'utilisateur ; suspend() / delete_account()
  / set_admin() refusent d'agir sur son propre compte, pour ne jamais se retirer l'accès par erreur.
- delete_account() efface en une transaction le compte, ses portefeuilles, ses opérations et ses réglages.
"""

from __future__ import annotations

import secrets
import uuid

import pandas as pd

from . import auth, config, db

MAX_ACCOUNTS = 1000
TEMP_PASSWORD_BYTES = 9  # 12 caractères
ACCOUNTS_SQL = """
SELECT u.id::text AS id, u.email, u.created_at::text AS created, u.last_sign_in_at::text AS last_login,
       (u.banned_until IS NOT NULL AND u.banned_until > now()) AS suspended,
       (SELECT COUNT(*) FROM portfolios p WHERE p.owner = u.id::text) AS portfolios,
       (SELECT COUNT(*) FROM transactions t JOIN portfolios p ON p.id = t.portfolio_id
         WHERE p.owner = u.id::text) AS operations
FROM auth.users u ORDER BY u.created_at LIMIT ?
"""


def _require(actor: auth.User) -> None:
    """PermissionError si l'utilisateur n'est pas administrateur ou si les comptes ne sont pas actifs."""
    if not auth.enabled():
        raise PermissionError("pas de comptes utilisateurs en mode local")
    if not actor.is_admin:
        raise PermissionError("action réservée aux administrateurs")


def _target(actor: auth.User, user_id: str) -> str:
    """Identifiant validé d'un autre compte que celui de l'administrateur."""
    try:
        uid = str(uuid.UUID(user_id))
    except ValueError as e:
        raise ValueError(f"identifiant de compte invalide : {user_id}") from e
    if uid == actor.id:
        raise PermissionError("action impossible sur ton propre compte")
    return uid


def accounts(actor: auth.User) -> pd.DataFrame:
    """Liste des comptes avec leur activité (sans le détail des portefeuilles)."""
    _require(actor)
    d = db.df(ACCOUNTS_SQL, (MAX_ACCOUNTS,))
    d["admin"] = d["email"].map(auth.has_admin_rights) if not d.empty else pd.Series(dtype=bool)
    assert len(d) <= MAX_ACCOUNTS
    return d


def reset_password(actor: auth.User, user_id: str) -> str:
    """Remplace le mot de passe par un mot de passe provisoire, renvoyé pour être transmis à l'utilisateur."""
    _require(actor)
    uid = _target(actor, user_id)
    temp = secrets.token_urlsafe(TEMP_PASSWORD_BYTES)
    with db.session() as con:
        cur = con.execute(
            "UPDATE auth.users SET encrypted_password = extensions.crypt(?, extensions.gen_salt('bf')), "
            "updated_at = now() WHERE id::text = ?",
            (temp, uid),
        )
        if cur.rowcount != 1:
            raise ValueError(f"compte {uid} introuvable")
    assert len(temp) >= auth.MIN_PASSWORD
    return temp


def suspend(actor: auth.User, user_id: str, suspended: bool) -> None:
    """Suspend (connexion refusée, session coupée) ou réactive un compte."""
    _require(actor)
    uid = _target(actor, user_id)
    sql = (
        "UPDATE auth.users SET banned_until = 'infinity'::timestamptz WHERE id::text = ?"
        if suspended
        else "UPDATE auth.users SET banned_until = NULL WHERE id::text = ?"
    )
    with db.session() as con:
        if con.execute(sql, (uid,)).rowcount != 1:
            raise ValueError(f"compte {uid} introuvable")


def delete_account(actor: auth.User, user_id: str) -> None:
    """Supprime définitivement un compte et toutes ses données personnelles."""
    _require(actor)
    uid = _target(actor, user_id)
    with db.session() as con:
        con.execute("DELETE FROM transactions WHERE portfolio_id IN (SELECT id FROM portfolios WHERE owner = ?)", (uid,))
        con.execute("DELETE FROM portfolios WHERE owner = ?", (uid,))
        con.execute("DELETE FROM settings WHERE key LIKE ?", (f"{uid}/%",))
        if con.execute("DELETE FROM auth.users WHERE id::text = ?", (uid,)).rowcount != 1:
            raise ValueError(f"compte {uid} introuvable")


def set_admin(actor: auth.User, email: str, admin: bool) -> None:
    """Donne ou retire les droits d'administration à une adresse (sauf soi-même et les administrateurs permanents)."""
    _require(actor)
    address = email.strip().lower()
    if not auth.EMAIL.match(address):
        raise ValueError(f"adresse invalide : {email}")
    if address == actor.email.lower():
        raise PermissionError("tu ne peux pas modifier tes propres droits")
    if not admin and address in config.ADMIN_EMAILS:
        raise PermissionError("administrateur permanent (configuration) : droits non modifiables ici")
    named = {str(e).lower() for e in (db.get_setting(auth.ADMIN_SETTING, []) or [])}
    named = named | {address} if admin else named - {address}
    db.set_setting(auth.ADMIN_SETTING, sorted(named))
