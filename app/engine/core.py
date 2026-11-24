"""Moteur de calcul — POINT D'ENTRÉE À REMPLACER PAR LE MOTEUR MÉTIER.

Règle simple : ce module ne connaît ni FastAPI, ni la session, ni la base. Il reçoit des données
Python et renvoie des données Python. On peut ainsi le tester seul (tests/test_engine.py), l'appeler
depuis la page web, l'API JSON ou un script, et le remplacer sans toucher à l'authentification.

L'exemple ci-dessous calcule des statistiques descriptives sur une série de nombres.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass


class EngineError(ValueError):
    """Erreur de saisie à afficher telle quelle à l'utilisateur."""


@dataclass
class EngineInput:
    values: list[float]
    label: str = ""


@dataclass
class EngineResult:
    label: str
    count: int
    minimum: float
    maximum: float
    mean: float
    median: float
    stdev: float

    def as_dict(self) -> dict:
        return asdict(self)


def parse_values(raw: str) -> list[float]:
    """« 12,5 ; 13 14.2 » → [12.5, 13.0, 14.2] (virgule décimale acceptée)."""
    tokens = raw.replace(";", " ").replace("\n", " ").split()
    values = []
    for token in tokens:
        try:
            values.append(float(token.replace(",", ".")))
        except ValueError as exc:
            raise EngineError(f"« {token} » n'est pas un nombre.") from exc
    return values


def run(data: EngineInput) -> EngineResult:
    if len(data.values) < 2:
        raise EngineError("Saisissez au moins deux valeurs.")
    if len(data.values) > 100_000:
        raise EngineError("100 000 valeurs au maximum.")
    return EngineResult(
        label=data.label.strip() or "Série",
        count=len(data.values),
        minimum=min(data.values),
        maximum=max(data.values),
        mean=statistics.fmean(data.values),
        median=statistics.median(data.values),
        stdev=statistics.stdev(data.values),
    )
