"""Base de test isolée remplie de cours synthétiques (aucun accès réseau)."""

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_TMP = tempfile.mkdtemp()
os.environ["BRVM_DB_PATH"] = str(Path(_TMP) / "test.db")
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


@pytest.fixture(scope="session", autouse=True)
def seeded_db():
    db.init()
    db.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)", _synthetic_prices())
    loader.load_dividends()
    yield
