"""Comptes utilisateurs : inscription et connexion par e-mail via Supabase Auth, propriétaire courant.

Contrat
- Actif seulement pour la version en ligne (base PostgreSQL) ; en local (SQLite), propriétaire « local », sans compte.
- sign_up(email, mot de passe) → User, ou None si Supabase exige une confirmation par e-mail.
- sign_in(email, mot de passe) → User ; AuthError (message en français) si refusé ou injoignable.
- Propriétaire courant : défini à chaque exécution de page par set_owner(), lu par owner() ; les portefeuilles
  et les réglages personnels (frais, IRVM) sont rangés par propriétaire.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import requests

from . import config, db

LOCAL_OWNER = "local"
TIMEOUT_S = 15
MIN_PASSWORD = 8
MAX_FIELD = 200
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MESSAGES = {
    "invalid login credentials": "E-mail ou mot de passe incorrect.",
    "user already registered": "Un compte existe déjà avec cet e-mail : connecte-toi.",
    "email not confirmed": "Confirme d'abord ton adresse avec le lien reçu par e-mail.",
    "signups not allowed": "Les inscriptions sont fermées pour le moment.",
    "rate limit": "Trop de tentatives : réessaie dans quelques minutes.",
    "password": "Mot de passe trop faible : au moins 8 caractères, avec lettres et chiffres.",
}

# DÉROGATION règle 6 : le propriétaire courant est un état par exécution (une variable de contexte par fil
# Streamlit), pas une globale partagée : chaque page le fixe avant toute lecture des données personnelles.
_OWNER: ContextVar[str] = ContextVar("brvm_owner", default=LOCAL_OWNER)


class AuthError(RuntimeError):
    """Inscription ou connexion refusée ; le message est affichable tel quel."""


@dataclass(frozen=True)
class User:
    """Utilisateur connecté."""

    id: str
    email: str

    @property
    def is_admin(self) -> bool:
        """Vrai si l'utilisateur peut modifier les données communes."""
        return self.email.lower() in config.ADMIN_EMAILS


def enabled() -> bool:
    """Vrai si les comptes sont exigés (version en ligne, base PostgreSQL)."""
    return db.engine() == "postgres" and bool(config.SUPABASE_URL and config.SUPABASE_PUBLISHABLE_KEY)


def owner() -> str:
    """Identifiant du propriétaire des données personnelles pour l'exécution en cours."""
    return _OWNER.get()


def set_owner(user_id: str) -> None:
    """Fixe le propriétaire courant (identifiant Supabase, ou LOCAL_OWNER)."""
    if not user_id or len(user_id) > MAX_FIELD:
        raise ValueError("identifiant de propriétaire invalide")
    _OWNER.set(user_id)


def user_key(name: str) -> str:
    """Clé de réglage personnel : préfixée par le propriétaire, sauf en local."""
    if not name:
        raise ValueError("nom de réglage vide")
    who = owner()
    return name if who == LOCAL_OWNER else f"{who}/{name}"


def get_user_setting(name: str, default: Any = None) -> Any:
    """Réglage personnel, à défaut le réglage commun, à défaut `default`."""
    return db.get_setting(user_key(name), db.get_setting(name, default))


def set_user_setting(name: str, value: Any) -> None:
    """Enregistre un réglage personnel."""
    db.set_setting(user_key(name), value)


def _check_credentials(email: str, password: str) -> str:
    """Adresse normalisée ; AuthError si l'e-mail ou le mot de passe est invalide."""
    address = email.strip().lower()
    if not EMAIL.match(address) or len(address) > MAX_FIELD:
        raise AuthError("Adresse e-mail invalide.")
    if not MIN_PASSWORD <= len(password) <= MAX_FIELD:
        raise AuthError(f"Le mot de passe doit faire au moins {MIN_PASSWORD} caractères.")
    return address


def _message(payload: dict[str, Any]) -> str:
    """Message d'erreur Supabase traduit en français."""
    raw = str(payload.get("msg") or payload.get("error_description") or payload.get("message") or "")
    for key, text in MESSAGES.items():
        if key in raw.lower():
            return text
    return f"Refus du service de comptes : {raw or 'raison inconnue'}"


def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """Appel à l'API Supabase Auth ; AuthError si le service refuse ou ne répond pas."""
    url = f"{config.SUPABASE_URL}/auth/v1/{path}"
    headers = {"apikey": config.SUPABASE_PUBLISHABLE_KEY, "Content-Type": "application/json"}
    try:
        r = requests.post(url, json=body, headers=headers, timeout=TIMEOUT_S)
    except requests.RequestException as e:
        raise AuthError("Service de comptes injoignable : réessaie dans un instant.") from e
    try:
        payload = r.json()
    except ValueError:
        payload = {}
    if r.status_code >= 400:
        raise AuthError(_message(payload if isinstance(payload, dict) else {}))
    if not isinstance(payload, dict):
        raise AuthError("Réponse inattendue du service de comptes.")
    return payload


def _user(payload: dict[str, Any]) -> User:
    """Utilisateur extrait d'une réponse Supabase (avec ou sans session)."""
    nested = payload.get("user")
    data: dict[str, Any] = nested if isinstance(nested, dict) else payload
    uid, email = str(data.get("id") or ""), str(data.get("email") or "")
    if not uid or not email:
        raise AuthError("Réponse incomplète du service de comptes.")
    return User(uid, email)


def sign_in(email: str, password: str) -> User:
    """Connexion par e-mail et mot de passe."""
    address = _check_credentials(email, password)
    payload = _post("token?grant_type=password", {"email": address, "password": password})
    if not payload.get("access_token"):
        raise AuthError("Connexion refusée par le service de comptes.")
    return _user(payload)


def sign_up(email: str, password: str) -> User | None:
    """Création de compte ; None si un e-mail de confirmation a été envoyé avant la première connexion."""
    address = _check_credentials(email, password)
    payload = _post("signup", {"email": address, "password": password})
    if not payload.get("access_token"):
        return None
    return _user(payload)
