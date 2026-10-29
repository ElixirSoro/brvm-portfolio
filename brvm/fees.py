"""Frais d'un ordre de bourse BRVM et droits de garde."""
from __future__ import annotations

from dataclasses import dataclass

from . import config, db


def current_fees() -> dict:
    fees = dict(config.DEFAULT_FEES)
    fees.update(db.get_setting("fees", {}) or {})
    return fees


@dataclass
class OrderFees:
    gross: float
    courtage: float
    tva: float
    brvm: float
    dcbr: float
    amf: float

    @property
    def total(self) -> float:
        return self.courtage + self.tva + self.brvm + self.dcbr + self.amf

    @property
    def rate(self) -> float:
        return self.total / self.gross if self.gross else 0.0

    def as_dict(self) -> dict:
        return {"Courtage SGI": self.courtage, "TVA sur courtage": self.tva, "Commission BRVM": self.brvm,
                "Commission DC/BR": self.dcbr, "Redevance AMF-UMOA": self.amf, "Total": self.total}


def order_fees(gross: float, fees: dict | None = None) -> OrderFees:
    """Frais d'un achat ou d'une vente d'un montant brut (quantité x cours)."""
    f = fees or current_fees()
    if gross <= 0:
        return OrderFees(0, 0, 0, 0, 0, 0)
    courtage = max(gross * f["courtage_pct"] / 100, f["courtage_min"])
    return OrderFees(
        gross=gross,
        courtage=courtage,
        tva=courtage * f["tva_courtage_pct"] / 100,
        brvm=gross * f["brvm_pct"] / 100,
        dcbr=gross * f["dcbr_pct"] / 100,
        amf=gross * f["amf_pct"] / 100,
    )


def buy_cost(quantity: float, price: float, fees: dict | None = None) -> tuple[float, OrderFees]:
    """Montant total débité pour un achat : brut + frais."""
    of = order_fees(quantity * price, fees)
    return of.gross + of.total, of


def sell_proceeds(quantity: float, price: float, fees: dict | None = None) -> tuple[float, OrderFees]:
    """Montant crédité pour une vente : brut - frais."""
    of = order_fees(quantity * price, fees)
    return of.gross - of.total, of


def custody_fee(value: float, days: int, fees: dict | None = None) -> float:
    f = fees or current_fees()
    return value * f["garde_annuel_pct"] / 100 * days / 365


def round_trip_rate(gross: float, fees: dict | None = None) -> float:
    """Coût d'un aller-retour (achat puis vente) en % du montant."""
    return 2 * order_fees(gross, fees).rate
