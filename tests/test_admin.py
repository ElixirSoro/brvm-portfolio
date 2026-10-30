"""Administration des comptes : tests sur PostgreSQL uniquement (schéma auth simulé, jamais sur Supabase)."""

import os
import uuid

import pytest

from brvm import admin, auth, db, portfolio

pytestmark = pytest.mark.skipif(
    db.engine() != "postgres" or "supabase" in os.environ.get("DATABASE_URL", ""),
    reason="nécessite une base PostgreSQL de test (TEST_DATABASE_URL)",
)

ADMIN = auth.User(str(uuid.uuid4()), "elixirsoro1@gmail.com")


@pytest.fixture
def users():
    """Schéma auth minimal (comme Supabase) avec deux comptes, et pgcrypto dans le schéma extensions."""
    with db.session() as con:
        for stmt in (
            "CREATE SCHEMA IF NOT EXISTS extensions",
            "CREATE EXTENSION IF NOT EXISTS pgcrypto SCHEMA extensions",
            "CREATE SCHEMA IF NOT EXISTS auth",
            "DROP TABLE IF EXISTS auth.users",
            "CREATE TABLE auth.users (id uuid PRIMARY KEY, email text, created_at timestamptz DEFAULT now(), "
            "updated_at timestamptz, last_sign_in_at timestamptz, banned_until timestamptz, encrypted_password text)",
        ):
            con.execute(stmt)
    bob = auth.User(str(uuid.uuid4()), "bob@example.com")
    for u in (ADMIN, bob):
        db.execute("INSERT INTO auth.users (id, email) VALUES (?::uuid, ?)", (u.id, u.email))
    auth.set_owner(bob.id)
    pid = portfolio.create("Portefeuille de Bob")
    portfolio.add(pid, portfolio.Operation("2026-07-01", "DEPOT", amount=10_000))
    auth.set_user_setting("fees", {"courtage_min": 1000.0})
    auth.set_owner(auth.LOCAL_OWNER)
    yield bob
    db.set_setting(auth.ADMIN_SETTING, [])


def test_only_admins_can_maintain(users):
    with pytest.raises(PermissionError):
        admin.accounts(users)
    acc = admin.accounts(ADMIN).set_index("email")
    assert acc.loc["bob@example.com", "portfolios"] == 1 and acc.loc["bob@example.com", "operations"] == 1
    assert bool(acc.loc["elixirsoro1@gmail.com", "admin"]) and not bool(acc.loc["bob@example.com", "admin"])


def test_reset_password_and_suspend(users):
    temp = admin.reset_password(ADMIN, users.id)
    ok = db.df(
        "SELECT encrypted_password = extensions.crypt(?, encrypted_password) AS ok FROM auth.users WHERE id::text = ?",
        (temp, users.id),
    )
    assert bool(ok["ok"].iloc[0])
    admin.suspend(ADMIN, users.id, True)
    assert not auth.is_active(users.id)
    admin.suspend(ADMIN, users.id, False)
    assert auth.is_active(users.id)
    with pytest.raises(PermissionError):
        admin.suspend(ADMIN, ADMIN.id, True)
    with pytest.raises(ValueError):
        admin.reset_password(ADMIN, "pas-un-uuid")


def test_admin_rights(users):
    admin.set_admin(ADMIN, users.email, True)
    assert auth.has_admin_rights(users.email) and users.is_admin
    admin.set_admin(ADMIN, users.email, False)
    assert not users.is_admin
    with pytest.raises(PermissionError):
        admin.set_admin(ADMIN, ADMIN.email, False)


def test_delete_account_removes_all_personal_data(users):
    with pytest.raises(PermissionError):
        admin.delete_account(ADMIN, ADMIN.id)
    admin.delete_account(ADMIN, users.id)
    assert db.df("SELECT 1 FROM auth.users WHERE id::text = ?", (users.id,)).empty
    assert db.df("SELECT 1 FROM portfolios WHERE owner = ?", (users.id,)).empty
    assert db.df("SELECT 1 FROM settings WHERE key LIKE ?", (f"{users.id}/%",)).empty
    assert not auth.is_active(users.id)


def test_admin_page_runs_for_an_admin(users):
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from brvm import ui

    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=120)
    at.session_state[ui.SESSION_USER] = {"id": ADMIN.id, "email": ADMIN.email}
    at.run()
    at.switch_page("views/administration.py").run()
    assert not at.exception, [e.value for e in at.exception]
    assert "Créer un mot de passe provisoire" in [b.label for b in at.button]
