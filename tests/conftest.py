"""Base de test isolée remplie de cours synthétiques (aucun accès réseau)."""

import os
import sys
import tempfile
from urllib.parse import urlparse
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_TMP = tempfile.mkdtemp()
os.environ["BRVM_DB_PATH"] = str(Path(_TMP) / "test.db")
# TEST_DATABASE_URL=postgresql://… pytest  → toute la suite tourne aussi sur PostgreSQL
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brvm import db, universe  # noqa: E402
from brvm.data import loader  # noqa: E402


def _synthetic_prices(seed: int = 7) -> list[tuple]:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2019-01-01", pd.Timestamp.today().normalize())
    rows = []
    tickers = [t for t, *_ in universe.SECURITIES] + list(universe.INDEX_TICKERS)
    market_f = rng.normal(0.0003, 0.007, len(days))  # facteur commun : le marché BRVM
    for i, t in enumerate(tickers):
        beta, idio = 0.6 + 0.1 * (i % 6), 0.010 + 0.002 * (i % 4)
        r = beta * market_f + rng.normal(0.0001 * (i % 4), idio, len(days))
        start = 1000 + 500 * (i % 20)
        p = start * np.exp(np.cumsum(r))
        if t == "SNTS":  # simule un historique non ajusté du fractionnement 1:10
            p = np.where(days < pd.Timestamp("2026-10-26"), p * 10, p)
        vol_t = rng.integers(500, 5000, len(days))
        rows += [(t, d.date().isoformat(), x, x, x, x, float(v)) for d, x, v in zip(days, p, vol_t, strict=True)]
    return rows


def _reset_test_postgres() -> None:
    """Base PostgreSQL de test vidée avant la suite : chaque exécution repart de zéro.

    Garde-fou : on ne vide qu'une base dont le nom contient « test » (jamais la base de production).
    """
    url = os.environ["DATABASE_URL"]
    if not url:
        return
    name = urlparse(url).path.lstrip("/")
    assert "test" in name, f"TEST_DATABASE_URL doit viser une base de test (reçu « {name} »)"
    for table in db.TABLES:
        db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


@pytest.fixture(scope="session", autouse=True)
def seeded_db():
    _reset_test_postgres()
    db.init()
    db.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)", _synthetic_prices())
    loader.load_dividends()
    yield
