"""Frais d'un ordre de bourse BRVM et droits de garde."""

from __future__ import annotations

from typing import Any

import math
from dataclasses import dataclass

from . import auth, config

DAYS_PER_YEAR = 365
FEE_KEYS = ("courtage_pct", "courtage_min", "tva_courtage_pct", "brvm_pct", "dcbr_pct", "amf_pct")


def current_fees() -> dict[str, Any]:
    """Grille de frais en vigueur : valeurs par défaut complétées par les réglages de l'utilisateur."""
    fees = dict(config.DEFAULT_FEES)
    fees.update(auth.get_user_setting("fees", {}) or {})
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
        """Total des frais de l'ordre (courtage, TVA, BRVM, DC/BR, AMF)."""
        return self.courtage + self.tva + self.brvm + self.dcbr + self.amf

    @property
    def rate(self) -> float:
        """Frais en proportion du montant brut (0 pour un ordre nul)."""
        return self.total / self.gross if self.gross else 0.0

    def as_dict(self) -> dict[str, Any]:
        """Détail des frais par poste, pour affichage."""
        return {
            "Courtage SGI": self.courtage,
            "TVA sur courtage": self.tva,
            "Commission BRVM": self.brvm,
            "Commission DC/BR": self.dcbr,
            "Redevance AMF-UMOA": self.amf,
            "Total": self.total,
        }


def order_fees(gross: float, fees: dict[str, Any] | None = None) -> OrderFees:
    """Frais d'un achat ou d'une vente d'un montant brut (quantité x cours)."""
    if math.isnan(gross) or gross < 0:
        raise ValueError(f"montant brut invalide : {gross}")
    f = fees or current_fees()
    missing = set(FEE_KEYS) - set(f)
    if missing:
        raise KeyError(f"grille de frais incomplète : {', '.join(sorted(missing))}")
    if gross == 0:
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


def _check_order(quantity: float, price: float) -> None:
    """Lève ValueError si la quantité ou le cours est négatif."""
    if quantity < 0 or price < 0:
        raise ValueError(f"quantité et cours positifs attendus (reçu {quantity} x {price})")


def buy_cost(quantity: float, price: float, fees: dict[str, Any] | None = None) -> tuple[float, OrderFees]:
    """Montant total débité pour un achat : brut + frais."""
    _check_order(quantity, price)
    of = order_fees(quantity * price, fees)
    return of.gross + of.total, of


def sell_proceeds(quantity: float, price: float, fees: dict[str, Any] | None = None) -> tuple[float, OrderFees]:
    """Montant crédité pour une vente : brut - frais."""
    _check_order(quantity, price)
    of = order_fees(quantity * price, fees)
    return of.gross - of.total, of


def custody_fee(value: float, days: int, fees: dict[str, Any] | None = None) -> float:
    """Droits de garde courus sur `days` jours pour un portefeuille de valeur `value`."""
    if value < 0 or days < 0:
        raise ValueError("valeur et nombre de jours doivent être positifs")
    f = fees or current_fees()
    return value * float(f["garde_annuel_pct"]) / 100 * days / DAYS_PER_YEAR


def round_trip_rate(gross: float, fees: dict[str, Any] | None = None) -> float:
    """Coût d'un aller-retour (achat puis vente) en % du montant."""
    return 2 * order_fees(gross, fees).rate
