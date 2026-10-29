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

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any, IO

import numpy as np
import pandas as pd

from . import auth, config, db, fees as fees_mod, market

TYPES = ["DEPOT", "RETRAIT", "ACHAT", "VENTE", "DIVIDENDE", "COUPON", "FRAIS"]
CASH_SIGN = {"DEPOT": 1, "RETRAIT": -1, "ACHAT": -1, "VENTE": 1, "DIVIDENDE": 1, "COUPON": 1, "FRAIS": -1}
BOND_PREFIX = "OBLIG"
DEFAULT_IRVM_PCT = 12.0
MAX_CSV_ROWS = 10_000
QTY_EPS = 1e-9


# ---------- portefeuilles ----------
OWNED = "COALESCE(owner, 'local') = ?"  # portefeuilles d'avant les comptes : rattachés au mode local


def create(name: str, note: str = "") -> int:
    """Crée un portefeuille vide pour le propriétaire courant ; renvoie son identifiant."""
    if not name.strip():
        raise ValueError("nom de portefeuille vide")
    if not db.df(f"SELECT 1 FROM portfolios WHERE name=? AND {OWNED}", (name, auth.owner())).empty:
        raise ValueError(f"tu as déjà un portefeuille nommé « {name} »")
    return db.execute("INSERT INTO portfolios (name, note, owner) VALUES (?, ?, ?)", (name, note, auth.owner()))


def list_all() -> pd.DataFrame:
    """Portefeuilles virtuels du propriétaire courant."""
    return db.df(f"SELECT * FROM portfolios WHERE {OWNED} ORDER BY id", (auth.owner(),))


def check_owner(pid: int) -> None:
    """PermissionError si le portefeuille n'existe pas ou n'appartient pas au propriétaire courant."""
    if pid <= 0:
        raise ValueError(f"portefeuille invalide : {pid}")
    if db.df(f"SELECT 1 FROM portfolios WHERE id=? AND {OWNED}", (pid, auth.owner())).empty:
        raise PermissionError(f"portefeuille {pid} introuvable dans ton compte")


def delete(pid: int) -> None:
    """Supprime un portefeuille et toutes ses opérations."""
    check_owner(pid)
    db.execute("DELETE FROM transactions WHERE portfolio_id=?", (pid,))
    db.execute("DELETE FROM portfolios WHERE id=?", (pid,))


# ---------- opérations ----------
@dataclass(frozen=True)
class Operation:
    """Une ligne d'avis d'opéré ou de relevé SGI."""

    day: str
    kind: str
    ticker: str | None = None
    quantity: float = 0.0
    price: float = 0.0
    amount: float | None = None  # montant saisi (dépôt, dividende, frais…) ; sinon quantité x cours
    fees: float | None = None  # None = frais calculés selon la grille
    note: str = ""
    dividend_is_gross: bool = False


def _dividend_tax(op: Operation, gross: float) -> float:
    """IRVM retenu à la source sur un dividende saisi en brut (0 si saisi en net)."""
    if not (op.dividend_is_gross and op.ticker):
        return 0.0
    country = market.securities()["country"].get(op.ticker, "ci")
    rate = float(auth.get_user_setting("irvm", config.DEFAULT_IRVM).get(country, DEFAULT_IRVM_PCT)) / 100
    return gross * rate  # IRVM retenu à la source


def amounts(op: Operation) -> tuple[float, float, float]:
    """(brut, frais ou IRVM, net) d'une opération ; ValueError si elle est incohérente."""
    if op.kind not in TYPES:
        raise ValueError(f"Type inconnu : {op.kind}")
    if op.quantity < 0 or op.price < 0 or (op.amount is not None and op.amount < 0) or (op.fees or 0) < 0:
        raise ValueError("quantité, cours, montant et frais doivent être positifs")
    if op.kind in ("ACHAT", "VENTE"):
        if not op.ticker or op.quantity <= 0 or op.price <= 0:
            raise ValueError("Achat/vente : ticker, quantité et cours sont obligatoires.")
        gross = op.quantity * op.price
        fees = op.fees
        if fees is None:
            fees = 0.0 if op.ticker.startswith(BOND_PREFIX) else fees_mod.order_fees(gross).total
        return gross, fees, gross + fees if op.kind == "ACHAT" else gross - fees
    gross = float(op.amount if op.amount is not None else op.quantity * op.price)
    if op.kind == "DIVIDENDE":
        tax = _dividend_tax(op, gross)
        return gross, tax, gross - tax
    return gross, op.fees or 0.0, gross


def add(pid: int, op: Operation) -> int:
    """Enregistre une opération dans le portefeuille `pid` ; renvoie son identifiant."""
    check_owner(pid)
    op = replace(op, kind=op.kind.upper(), ticker=(op.ticker or "").upper() or None)
    gross, fees, net = amounts(op)
    if op.kind == "VENTE":
        pos, _ = positions(pid, at=pd.Timestamp(op.day))
        held = float(pos.loc[pos["ticker"] == op.ticker, "quantity"].sum())
        if op.quantity > held + QTY_EPS:
            raise ValueError(f"Vente de {op.quantity:g} {op.ticker} : seulement {held:g} titres détenus à cette date.")
    return db.execute(
        "INSERT INTO transactions (portfolio_id, date, type, ticker, quantity, price, gross, fees, net, note) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (pid, op.day, op.kind, op.ticker, op.quantity, op.price, gross, fees, net, op.note),
    )


def remove(tx_id: int) -> None:
    """Supprime une opération d'un portefeuille du propriétaire courant."""
    row = db.df("SELECT portfolio_id FROM transactions WHERE id=?", (tx_id,))
    if row.empty:
        raise ValueError(f"opération {tx_id} introuvable")
    check_owner(int(row["portfolio_id"].iloc[0]))
    db.execute("DELETE FROM transactions WHERE id=?", (tx_id,))


def transactions(pid: int) -> pd.DataFrame:
    """Opérations d'un portefeuille, avec quantités et cours convertis en actions actuelles (fractionnements)."""
    check_owner(pid)
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


def _opt_float(value: object) -> float | None:
    """Nombre lu dans une cellule CSV ; None si la cellule est vide."""
    return None if str(value).strip() == "" else float(str(value))


def import_csv(pid: int, csv_file: str | IO[Any]) -> int:
    """CSV attendu : date,type,ticker,quantite,cours,montant,frais,note (colonnes vides permises)."""
    d = pd.read_csv(csv_file).fillna("")
    missing = {"date", "type"} - set(d.columns)
    if missing:
        raise ValueError(f"colonnes manquantes : {', '.join(sorted(missing))}")
    if len(d) > MAX_CSV_ROWS:
        raise ValueError(f"{len(d)} lignes, au-delà de {MAX_CSV_ROWS}")
    for _, r in d.iterrows():
        add(
            pid,
            Operation(
                str(r["date"])[:10],
                str(r["type"]),
                str(r.get("ticker", "")) or None,
                _opt_float(r.get("quantite", "")) or 0.0,
                _opt_float(r.get("cours", "")) or 0.0,
                _opt_float(r.get("montant", "")),
                _opt_float(r.get("frais", "")),
                str(r.get("note", "")),
            ),
        )
    return len(d)


# ---------- positions et valorisation ----------
ACCOUNTS = ("cash", "deposits", "withdrawals", "fees", "dividends", "realized", "irvm")
POSITION_COLUMNS = ["ticker", "quantity", "avg_cost", "cost", "realized"]


@dataclass
class _Ledger:
    """Livre de comptes construit opération par opération (état propre, jamais partagé)."""

    acc: dict[str, float] = field(default_factory=lambda: dict.fromkeys(ACCOUNTS, 0.0))
    book: dict[str, dict[str, float]] = field(default_factory=dict)

    def apply(self, t: pd.Series) -> None:
        """Applique une opération (ligne de `transactions`) aux comptes et aux positions."""
        k = t["type"]
        if k not in CASH_SIGN:
            raise ValueError(f"type d'opération inconnu en base : {k}")
        self.acc["cash"] += CASH_SIGN[k] * t["net"]
        if k in ("DEPOT", "RETRAIT", "FRAIS"):
            self.acc[{"DEPOT": "deposits", "RETRAIT": "withdrawals", "FRAIS": "fees"}[k]] += t["net"]
            return
        if k in ("DIVIDENDE", "COUPON"):
            self.acc["dividends"] += t["net"]
            self.acc["irvm"] += t["fees"] or 0
            return
        self.acc["fees"] += t["fees"]
        b = self.book.setdefault(t["ticker"], {"quantity": 0.0, "cost": 0.0, "realized": 0.0})
        if k == "ACHAT":
            b["quantity"] += t["adj_qty"]
            b["cost"] += t["net"]
            return
        sold_cost = (b["cost"] / b["quantity"] if b["quantity"] else 0.0) * t["adj_qty"]
        b["realized"] += t["net"] - sold_cost
        self.acc["realized"] += t["net"] - sold_cost
        b["quantity"] -= t["adj_qty"]
        b["cost"] -= sold_cost


def positions(pid: int, at: pd.Timestamp | None = None, tx: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Positions détenues et comptes (liquidités, versements, frais, dividendes…) à la date `at`."""
    tx = transactions(pid) if tx is None else tx
    ledger = _Ledger()
    if tx.empty:
        return pd.DataFrame(columns=POSITION_COLUMNS), ledger.acc
    if at is not None:
        tx = tx[tx["date"] <= at]
    for _, t in tx.iterrows():
        ledger.apply(t)
    acc, book = ledger.acc, ledger.book
    rows = [
        {
            "ticker": tk,
            "quantity": b["quantity"],
            "cost": b["cost"],
            "avg_cost": b["cost"] / b["quantity"] if b["quantity"] > QTY_EPS else 0.0,
            "realized": b["realized"],
        }
        for tk, b in book.items()
        if abs(b["quantity"]) > QTY_EPS
    ]
    pos = pd.DataFrame(rows) if rows else pd.DataFrame(columns=POSITION_COLUMNS)
    assert pos.empty or bool((pos["quantity"] > 0).all()), "position négative : vente de plus de titres que détenus"
    return pos, acc


def valuation(pid: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Positions valorisées au dernier cours et synthèse (valeur, plus-value, frais de sortie, valeur liquidative)."""
    pos, acc = positions(pid)
    quotes = market.latest_quotes()
    secs = market.securities()
    if not pos.empty:

        def price_of(t: str) -> float:
            """Cours de valorisation : dernier cours, ou prix de revient pour les obligations."""
            if t.startswith(BOND_PREFIX):
                return float(pos.loc[pos["ticker"] == t, "avg_cost"].iloc[0])  # obligations au prix de revient
            return float(quotes["last"].get(t, np.nan)) if not quotes.empty else np.nan

        pos["name"] = pos["ticker"].map(
            lambda t: secs["name"].get(t, "Obligations") if not t.startswith(BOND_PREFIX) else "Obligations"
        )
        pos["sector"] = pos["ticker"].map(
            lambda t: secs["sector"].get(t, "Obligations") if not t.startswith(BOND_PREFIX) else "Obligations"
        )
        pos["price"] = pos["ticker"].map(price_of)
        pos["value"] = pos["quantity"] * pos["price"]
        pos["gain"] = pos["value"] - pos["cost"]
        pos["gain_pct"] = pos["gain"] / pos["cost"]
        pos["change_day"] = pos["ticker"].map(lambda t: quotes["change_day"].get(t, np.nan) if not quotes.empty else np.nan)
        # frais de sortie estimés si l'on vendait tout aujourd'hui
        pos["exit_fees"] = pos.apply(
            lambda r: (
                0.0 if r["ticker"].startswith(BOND_PREFIX) else fees_mod.order_fees(r["value"]).total if r["value"] > 0 else 0.0
            ),
            axis=1,
        )
        total_value = pos["value"].sum()
        pos["weight"] = pos["value"] / (total_value + max(acc["cash"], 0))
    else:
        total_value = 0.0
    net_invested = acc["deposits"] - acc["withdrawals"]
    total = total_value + acc["cash"]
    summary = {
        **acc,
        "securities_value": total_value,
        "total": total,
        "net_invested": net_invested,
        "gain": total - net_invested,
        "gain_pct": (total / net_invested - 1) if net_invested else np.nan,
        "exit_fees": float(pos["exit_fees"].sum()) if not pos.empty else 0.0,
        "custody_accrued": custody_accrued(pid, total_value),
    }
    summary["liquidation_value"] = total - summary["exit_fees"] - summary["custody_accrued"]
    return pos, summary


def custody_accrued(pid: int, value: float) -> float:
    """Droits de garde courus depuis le dernier prélèvement saisi (ou depuis la première opération)."""
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
    panel = market.close_panel(years=years, tickers=[*tickers, "BRVMC"])
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
        already = recorded[
            (recorded["ticker"] == d["ticker"])
            & (recorded["date"] >= ex - pd.Timedelta(days=5))
            & (recorded["date"] <= pd.Timestamp(d["pay_date"]) + pd.Timedelta(days=30))
        ]
        if not already.empty:
            continue
        q = held.iloc[0]
        rows.append(
            {
                "ticker": d["ticker"],
                "ex_date": d["ex_date"],
                "pay_date": d["pay_date"],
                "quantity": q,
                "net_per_share": d["net"],
                "net_total": q * d["net"],
            }
        )
    return pd.DataFrame(rows)


def mirror_from_orders(name: str, orders: pd.DataFrame, day: str, deposit: float | None = None) -> int:
    """Crée un portefeuille virtuel à partir des ordres proposés par l'optimiseur."""
    pid = create(name, "Créé depuis l'optimiseur")
    total = float(orders["total"].sum())
    if orders.empty:
        raise ValueError("aucun ordre à copier")
    add(pid, Operation(day, "DEPOT", amount=deposit or total, note="Dépôt initial"))
    for _, o in orders.iterrows():
        add(
            pid,
            Operation(
                day,
                "ACHAT",
                o["ticker"],
                float(o["quantity"]),
                float(o["price"]),
                fees=float(o["fees"]),
                note="Ordre proposé par l'optimiseur",
            ),
        )
    return pid
