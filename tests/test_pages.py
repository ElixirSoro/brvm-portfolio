"""Pages : chacune s'exécute de bout en bout depuis app.py sans exception ; en ligne, la connexion est exigée."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from brvm import db

ROOT = Path(__file__).resolve().parents[1]
PAGES = sorted(p.name for p in (ROOT / "views").glob("*.py") if p.name not in {"administration.py", "connexion.py"})
TIMEOUT_S = 120
LOCAL = db.engine() == "sqlite"


def _app() -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=TIMEOUT_S)
    at.run()
    return at


@pytest.mark.skipif(not LOCAL, reason="en ligne, les pages exigent un compte (voir test suivant)")
@pytest.mark.parametrize("page", PAGES)
def test_page_runs_without_exception(page: str) -> None:
    at = _app()
    at.switch_page(f"views/{page}").run()
    assert not at.exception, f"{page} : {[e.value for e in at.exception]}"
    assert at.title, f"{page} : aucun titre affiché"


@pytest.mark.skipif(LOCAL, reason="comptes actifs seulement avec PostgreSQL")
def test_signed_out_visitor_only_sees_login() -> None:
    at = _app()
    assert not at.exception, [e.value for e in at.exception]
    assert [t.value for t in at.title] == ["Bienvenue sur Mr investor"]
    with pytest.raises(ValueError):
        at.switch_page("views/portefeuille.py")


@pytest.mark.skipif(not LOCAL, reason="en ligne, les pages exigent un compte")
def test_optimizer_with_signal_tilt() -> None:
    """Régression : déplacer « Poids donné aux signaux de veille » ne doit pas planter, avec ou sans signaux."""
    at = _app()
    at.switch_page("views/optimiseur.py").run()
    slider = next(s for s in at.slider if s.label == "Poids donné aux signaux de veille")
    slider.set_value(2.0).run()
    assert not at.exception, [e.value for e in at.exception]
