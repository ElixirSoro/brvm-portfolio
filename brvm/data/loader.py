"""Import de l'historique déjà téléchargé par Cote_scrapper (BRVM_DATA_SCRAP) et du calendrier des dividendes."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .. import config, db, universe

DIVIDENDS_CSV = config.ROOT / "data" / "dividendes.csv"


def import_scrap_dir(scrap_dir: Path | None = None) -> dict:
    """Lit BRVM_historique_complet_toutes_entreprises.csv (ou les CSV par titre) et remplit la table prices."""
    scrap_dir = Path(scrap_dir or config.SCRAP_DIR)
    big = scrap_dir / "BRVM_historique_complet_toutes_entreprises.csv"
    if big.exists():
        frames = [pd.read_csv(big)]
    else:
        frames = [
            pd.read_csv(p).assign(Ticker=p.name.split("_historique")[0]) for p in scrap_dir.glob("*/*_historique_cotations.csv")
        ]
    if not frames:
        return {"rows": 0, "tickers": 0, "message": f"Aucun CSV trouvé dans {scrap_dir}"}
    raw = pd.concat(frames, ignore_index=True)
    raw["ticker"] = raw["Ticker"].astype(str).str.split(".").str[0].str.upper()
    raw["date"] = pd.to_datetime(raw["Date"]).dt.date.astype(str)
    known = set(universe.by_ticker())
    raw = raw[raw["ticker"].isin(known)]
    rows = list(
        raw[["ticker", "date", "Ouverture", "Plus_haut", "Plus_bas", "Cloture", "Volume_titres"]].itertuples(
            index=False, name=None
        )
    )
    db.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)", rows)
    db.mark_update("prices")
    return {"rows": len(rows), "tickers": raw["ticker"].nunique(), "message": "ok"}


def load_dividends(csv_path: Path | None = None) -> int:
    path = Path(csv_path or DIVIDENDS_CSV)
    if not path.exists():
        return 0
    d = pd.read_csv(path)
    rows = list(d[["ticker", "ex_date", "pay_date", "amount", "is_gross"]].itertuples(index=False, name=None))
    db.executemany("INSERT OR REPLACE INTO dividends VALUES (?,?,?,?,?)", rows)
    return len(rows)
