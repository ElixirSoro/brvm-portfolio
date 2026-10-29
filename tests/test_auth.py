"""Comptes utilisateurs : appels Supabase Auth simulés et cloisonnement des données par propriétaire."""

import pytest
import requests

from brvm import auth, fees, portfolio


class FakeResponse:
    def __init__(self, status: int, payload: object) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> object:
        return self._payload


@pytest.fixture
def as_owner():
    """Change de propriétaire le temps d'un test, puis revient au mode local."""
    yield auth.set_owner
    auth.set_owner(auth.LOCAL_OWNER)


def test_sign_in_and_sign_up(monkeypatch):
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(url)
        if url.endswith("signup"):
            return FakeResponse(200, {"id": "u-2", "email": json["email"]})  # confirmation e-mail exigée
        return FakeResponse(200, {"access_token": "t", "user": {"id": "u-1", "email": json["email"]}})

    monkeypatch.setattr(auth.requests, "post", fake_post)
    user = auth.sign_in(" Elixir@Example.com ", "motdepasse1")
    assert user == auth.User("u-1", "elixir@example.com")
    assert auth.sign_up("nouveau@example.com", "motdepasse1") is None
    assert calls[0].endswith("/auth/v1/token?grant_type=password")


def test_auth_errors_are_translated(monkeypatch):
    monkeypatch.setattr(
        auth.requests, "post", lambda *a, **k: FakeResponse(400, {"error_description": "Invalid login credentials"})
    )
    with pytest.raises(auth.AuthError, match="incorrect"):
        auth.sign_in("a@b.co", "motdepasse1")

    def down(*a, **k):
        raise requests.ConnectionError("hors ligne")

    monkeypatch.setattr(auth.requests, "post", down)
    with pytest.raises(auth.AuthError, match="injoignable"):
        auth.sign_in("a@b.co", "motdepasse1")


@pytest.mark.parametrize(("email", "password"), [("pas-un-email", "motdepasse1"), ("a@b.co", "court")])
def test_invalid_credentials_rejected_before_any_call(monkeypatch, email, password):
    monkeypatch.setattr(auth.requests, "post", lambda *a, **k: pytest.fail("aucun appel réseau attendu"))
    with pytest.raises(auth.AuthError):
        auth.sign_up(email, password)


def test_each_account_only_sees_its_own_portfolios(as_owner):
    as_owner("alice")
    pid = portfolio.create("Retraite")
    portfolio.add(pid, portfolio.Operation("2026-07-01", "DEPOT", amount=100_000))
    as_owner("bob")
    assert "Retraite" not in portfolio.list_all()["name"].tolist()
    for attempt in (lambda: portfolio.transactions(pid), lambda: portfolio.delete(pid),
                    lambda: portfolio.add(pid, portfolio.Operation("2026-07-02", "DEPOT", amount=1))):  # fmt: skip
        with pytest.raises(PermissionError):
            attempt()
    portfolio.create("Retraite")  # même nom, autre compte : autorisé
    as_owner("alice")
    assert len(portfolio.transactions(pid)) == 1
    with pytest.raises(ValueError, match="déjà"):
        portfolio.create("Retraite")


def test_fee_grid_is_personal(as_owner):
    as_owner("alice")
    auth.set_user_setting("fees", {"courtage_min": 5000.0})
    assert fees.current_fees()["courtage_min"] == 5000.0
    as_owner("bob")
    assert fees.current_fees()["courtage_min"] != 5000.0


def test_admin_flag_and_owner_validation():
    assert auth.User("x", "ELIXIRSORO1@gmail.com").is_admin
    assert not auth.User("y", "autre@example.com").is_admin
    with pytest.raises(ValueError):
        auth.set_owner("")
