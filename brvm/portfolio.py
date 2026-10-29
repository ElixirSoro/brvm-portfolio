"""Portefeuille virtuel : copie fidèle du portefeuille réel, frais et dividendes compris.

Types d'opération :
  DEPOT, RETRAIT        mouvements d'argent sur le compte SGI
  ACHAT, VENTE          quantité x cours ; frais calculés selon la grille ou saisis depuis l'avis d'opéré
  DIVIDENDE             montant net reçu (ou brut, l'IRVM est alors déduit)
  COUPON                intérêts d'obligation reçus
  FRAIS                 droits de garde, tenue de compte, autres
Les quantités et cours antérieurs à un fractionnement sont convertis en actions actuelles.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from . import config, db, fees as fees_mod, market

TYPES = ["DEPOT", "RETRAIT", "ACHAT", "VENTE", "DIVIDENDE", "COUPON", "FRAIS"]
CASH_SIGN = {"DEPOT": 1, "RETRAIT": -1, "ACHAT": -1, "VENTE": 1, "DIVIDENDE": 1, "COUPON": 1, "FRAIS": -1}
BOND_PREFIX = "OBLIG"


# ---------- portefeuilles ----------
def create(name: str, note: str = "") -> int:
    return db.execute("INSERT INTO portfolios (name, note) VALUES (?, ?)", (name, note))


def list_all() -> pd.DataFrame:
    return db.df("SELECT * FROM portfolios ORDER BY id")


def delete(pid: int) -> None:
    db.execute("DELETE FROM transactions WHERE portfolio_id=?", (pid,))
    db.execute("DELETE FROM portfolios WHERE id=?", (pid,))


# ---------- opérations ----------
def add(pid: int, day: str, kind: str, ticker: str | None = None, quantity: float = 0, price: float = 0,
        amount: float | None = None, fees: float | None = None, note: str = "", dividend_is_gross: bool = False) -> int:
    kind = kind.upper()
    if kind not in TYPES:
        raise ValueError(f"Type inconnu : {kind}")
    ticker = (ticker or "").upper() or None
    gross = float(amount if amount is not None else quantity * price)
    if kind in ("ACHAT", "VENTE"):
        if not ticker or quantity <= 0 or price <= 0:
            raise ValueError("Achat/vente : ticker, quantité et cours sont obligatoires.")
        gross = quantity * price
        if fees is None:
            fees = 0.0 if ticker.startswith(BOND_PREFIX) else fees_mod.order_fees(gross).total
        net = gross + fees if kind == "ACHAT" else gross - fees
    elif kind == "DIVIDENDE":
        fees = 0.0
        if dividend_is_gross and ticker:
            country = market.securities()["country"].get(ticker, "ci")
            rate = db.get_setting("irvm", config.DEFAULT_IRVM).get(country, 12.0) / 100
            fees = gross * rate          # IRVM retenu à la source
        net = gross - fees
    else:
        fees = fees or 0.0
        net = gross
    return db.execute(
        "INSERT INTO transactions (portfolio_id, date, type, ticker, quantity, price, gross, fees, net, note) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (pid, day, kind, ticker, quantity, price, gross, fees, net, note))


def remove(tx_id: int) -> None:
    db.execute("DELETE FROM transactions WHERE id=?", (tx_id,))


def transactions(pid: int) -> pd.DataFrame:
    tx = db.df("SELECT * FROM transactions WHERE portfolio_id=? ORDER BY date, id", (pid,))
    if tx.empty:
        return tx
    tx["date"] = pd.to_datetime(tx["date"])
    # conversion en actions actuelles pour les opérations antérieures à un fractionnement
    tx["adj_qty"] = tx["quantity"].astype(float)
    tx["adj_price"] = tx["price"].astype(float)
    for _, ca in db.df("SELECT * FROM corporate_actions").iterrows():
        m = (tx["ticker"] == ca["ticker"]) & (tx["date"] < pd.Timestamp(ca["date"]))
        tx.loc[m, "adj_qty"] *= ca["ratio"]
        tx.loc[m, "adj_price"] /= ca["ratio"]
    return tx


def import_csv(pid: int, csv_file) -> int:
    """CSV attendu : date,type,ticker,quantite,cours,montant,frais,note (colonnes vides permises)."""
    d = pd.read_csv(csv_file).fillna("")
    n = 0
    for _, r in d.iterrows():
        add(pid, str(r["date"])[:10], str(r["type"]), str(r.get("ticker", "")) or None,
            float(r.get("quantite") or 0), float(r.get("cours") or 0),
            float(r["montant"]) if str(r.get("montant", "")) != "" else None,
            float(r["frais"]) if str(r.get("frais", "")) != "" else None, str(r.get("note", "")))
        n += 1
    return n


# ---------- positions et valorisation ----------
def positions(pid: int, at: pd.Timestamp | None = None, tx: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    tx = transactions(pid) if tx is None else tx
    empty = pd.DataFrame(columns=["ticker", "quantity", "avg_cost", "cost", "realized"])
    if tx.empty:
        return empty, {"cash": 0.0, "deposits": 0.0, "withdrawals": 0.0, "fees": 0.0, "dividends": 0.0,
                       "realized": 0.0, "irvm": 0.0}
    if at is not None:
        tx = tx[tx["date"] <= at]
    book: dict[str, dict] = {}
    cash = deposits = withdrawals = fees_paid = dividends = realized = irvm = 0.0
    for _, t in tx.iterrows():
        k = t["type"]
        cash += CASH_SIGN[k] * t["net"]
        if k == "DEPOT":
            deposits += t["net"]
        elif k == "RETRAIT":
            withdrawals += t["net"]
        elif k == "FRAIS":
            fees_paid += t["net"]
        elif k in ("DIVIDENDE", "COUPON"):
            dividends += t["net"]
            irvm += t["fees"] or 0
        elif k == "ACHAT":
            fees_paid += t["fees"]
            b = book.setdefault(t["ticker"], {"quantity": 0.0, "cost": 0.0, "realized": 0.0})
            b["quantity"] += t["adj_qty"]
            b["cost"] += t["net"]
        elif k == "VENTE":
            fees_paid += t["fees"]
            b = book.setdefault(t["ticker"], {"quantity": 0.0, "cost": 0.0, "realized": 0.0})
            avg = b["cost"] / b["quantity"] if b["quantity"] else 0.0
            sold_cost = avg * t["adj_qty"]
            b["realized"] += t["net"] - sold_cost
            realized += t["net"] - sold_cost
            b["quantity"] -= t["adj_qty"]
            b["cost"] -= sold_cost
    rows = [{"ticker": tk, "quantity": b["quantity"], "cost": b["cost"],
             "avg_cost": b["cost"] / b["quantity"] if b["quantity"] > 1e-9 else 0.0, "realized": b["realized"]}
            for tk, b in book.items() if abs(b["quantity"]) > 1e-9]
    pos = pd.DataFrame(rows) if rows else empty
    return pos, {"cash": cash, "deposits": deposits, "withdrawals": withdrawals, "fees": fees_paid,
                 "dividends": dividends, "realized": realized, "irvm": irvm}


def valuation(pid: int) -> tuple[pd.DataFrame, dict]:
    pos, acc = positions(pid)
    quotes = market.latest_quotes()
    secs = market.securities()
    if not pos.empty:
        def price_of(t):
            if t.startswith(BOND_PREFIX):
                return float(pos.loc[pos["ticker"] == t, "avg_cost"].iloc[0])  # obligations au prix de revient
            return float(quotes["last"].get(t, np.nan)) if not quotes.empty else np.nan
        pos["name"] = pos["ticker"].map(lambda t: secs["name"].get(t, "Obligations") if not t.startswith(BOND_PREFIX) else "Obligations")
        pos["sector"] = pos["ticker"].map(lambda t: secs["sector"].get(t, "Obligations") if not t.startswith(BOND_PREFIX) else "Obligations")
        pos["price"] = pos["ticker"].map(price_of)
        pos["value"] = pos["quantity"] * pos["price"]
        pos["gain"] = pos["value"] - pos["cost"]
        pos["gain_pct"] = pos["gain"] / pos["cost"]
        pos["change_day"] = pos["ticker"].map(lambda t: quotes["change_day"].get(t, np.nan) if not quotes.empty else np.nan)
        # frais de sortie estimés si l'on vendait tout aujourd'hui
        pos["exit_fees"] = pos.apply(lambda r: 0.0 if r["ticker"].startswith(BOND_PREFIX)
                                     else fees_mod.order_fees(r["value"]).total if r["value"] > 0 else 0.0, axis=1)
        total_value = pos["value"].sum()
        pos["weight"] = pos["value"] / (total_value + max(acc["cash"], 0))
    else:
        total_value = 0.0
    net_invested = acc["deposits"] - acc["withdrawals"]
    total = total_value + acc["cash"]
    summary = {**acc, "securities_value": total_value, "total": total, "net_invested": net_invested,
               "gain": total - net_invested, "gain_pct": (total / net_invested - 1) if net_invested else np.nan,
               "exit_fees": float(pos["exit_fees"].sum()) if not pos.empty else 0.0,
               "custody_accrued": custody_accrued(pid, total_value)}
    summary["liquidation_value"] = total - summary["exit_fees"] - summary["custody_accrued"]
    return pos, summary


def custody_accrued(pid: int, value: float) -> float:
    tx = transactions(pid)
    if tx.empty:
        return 0.0
    garde = tx[(tx["type"] == "FRAIS") & tx["note"].str.contains("garde", case=False, na=False)]
    since = garde["date"].max() if not garde.empty else tx["date"].min()
    days = (pd.Timestamp(date.today()) - since).days
    return fees_mod.custody_fee(value, max(days, 0))


def history(pid: int) -> pd.DataFrame:
    """Valeur quotidienne du portefeuille, performance hors versements (TWR) et BRVM Composite rebasé."""
    tx = transactions(pid)
    if tx.empty:
        return pd.DataFrame()
    start = tx["date"].min()
    years = (pd.Timestamp(date.today()) - start).days / 365.25 + 0.1
    tickers = [t for t in tx["ticker"].dropna().unique() if not t.startswith(BOND_PREFIX)]
    panel = market.close_panel(years=years, tickers=tickers + ["BRVMC"])
    days = pd.bdate_range(start, pd.Timestamp(date.today()))
    panel = panel.reindex(days).ffill() if not panel.empty else pd.DataFrame(index=days)
    flows = tx[tx["type"].isin(["DEPOT", "RETRAIT"])].copy()
    flows["signed"] = flows["net"] * flows["type"].map({"DEPOT": 1, "RETRAIT": -1})
    flow_by_day = flows.groupby(flows["date"].dt.normalize())["signed"].sum().reindex(days).fillna(0)

    values = []
    for d in days:
        pos, acc = positions(pid, at=d, tx=tx)
        v = acc["cash"]
        for _, p in pos.iterrows():
            if p["ticker"].startswith(BOND_PREFIX):
                v += p["cost"]
            elif p["ticker"] in panel.columns and not np.isnan(panel.at[d, p["ticker"]]):
                v += p["quantity"] * panel.at[d, p["ticker"]]
            else:
                v += p["cost"]
        values.append(v)
    out = pd.DataFrame({"value": values, "flows": flow_by_day.values}, index=days)
    prev = out["value"].shift(1)
    r = (out["value"] - out["flows"]) / prev - 1
    r = r.replace([np.inf, -np.inf], np.nan).fillna(0)
    out["twr_index"] = 100 * (1 + r).cumprod()
    if "BRVMC" in panel.columns and panel["BRVMC"].notna().any():
        b = panel["BRVMC"].ffill().bfill()
        out["brvmc_index"] = 100 * b / b.iloc[0]
    return out


def dividend_suggestions(pid: int) -> pd.DataFrame:
    """Dividendes du calendrier auxquels le portefeuille avait droit et qui ne sont pas encore saisis."""
    tx = transactions(pid)
    div = market.dividend_table()
    if tx.empty or div.empty:
        return pd.DataFrame()
    recorded = tx[tx["type"] == "DIVIDENDE"]
    rows = []
    for _, d in div.iterrows():
        ex = pd.Timestamp(d["ex_date"])
        if ex < tx["date"].min():
            continue
        pos, _ = positions(pid, at=ex - pd.Timedelta(days=1), tx=tx)
        held = pos.loc[pos["ticker"] == d["ticker"], "quantity"]
        if held.empty or held.iloc[0] <= 0:
            continue
        already = recorded[(recorded["ticker"] == d["ticker"]) &
                           (recorded["date"] >= ex - pd.Timedelta(days=5)) &
                           (recorded["date"] <= pd.Timestamp(d["pay_date"]) + pd.Timedelta(days=30))]
        if not already.empty:
            continue
        q = held.iloc[0]
        rows.append({"ticker": d["ticker"], "ex_date": d["ex_date"], "pay_date": d["pay_date"], "quantity": q,
                     "net_per_share": d["net"], "net_total": q * d["net"]})
    return pd.DataFrame(rows)


def mirror_from_orders(name: str, orders: pd.DataFrame, day: str, deposit: float | None = None) -> int:
    """Crée un portefeuille virtuel à partir des ordres proposés par l'optimiseur."""
    pid = create(name, "Créé depuis l'optimiseur")
    total = float(orders["total"].sum())
    add(pid, day, "DEPOT", amount=deposit or total, note="Dépôt initial")
    for _, o in orders.iterrows():
        add(pid, day, "ACHAT", o["ticker"], o["quantity"], o["price"],
            fees=o["fees"], note="Ordre proposé par l'optimiseur")
    return pid
