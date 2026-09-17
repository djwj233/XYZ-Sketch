"""Candidate and placement models shared by calibration and holdout."""

import math
from dataclasses import dataclass
from typing import Dict, Optional

from .artifacts import canonical_sha256
from .simulator import PlacementGeometry
from .threshold import Threshold


@dataclass(frozen=True)
class PlacementSpec:
    candidate_id: str
    C: Optional[float]
    gamma: Optional[float]
    a: float
    z_raw: float
    z: int
    valid: bool
    status: str
    is_frozen_prediction: bool = False

    def geometry(self, M: int) -> PlacementGeometry:
        if not self.valid:
            raise ValueError("invalid candidate has no placement geometry")
        return PlacementGeometry.create(M, self.a, self.z)

    def config_value(self, M: int) -> Dict[str, object]:
        value: Dict[str, object] = {
            "candidate_id": self.candidate_id,
            "C": self.C,
            "gamma": self.gamma,
            "a": self.a,
            "z_raw": self.z_raw,
            "z": self.z,
            "M": M,
            "valid": self.valid,
            "status": self.status,
            "is_frozen_prediction": self.is_frozen_prediction,
        }
        if self.valid:
            geometry = self.geometry(M)
            value.update(
                {
                    "range_length": geometry.range_length,
                    "naive_base_range": geometry.naive_base_range,
                    "extra_circular_anchors": geometry.extra_circular_anchors,
                    "circular_base_range": geometry.circular_base_range,
                }
            )
        return value

    def config_sha256(self, M: int) -> str:
        return canonical_sha256(self.config_value(M))


@dataclass(frozen=True, order=True)
class CalibrationCandidate:
    c_units: int
    gamma_units: int

    def __post_init__(self) -> None:
        if self.c_units <= 0 or self.gamma_units <= 0:
            raise ValueError("C and gamma fixed-point units must be positive")

    @property
    def candidate_id(self) -> str:
        return "C%04d-G%04d" % (self.c_units, self.gamma_units)

    @property
    def C(self) -> float:
        return self.c_units / 1000.0

    @property
    def gamma(self) -> float:
        return self.gamma_units / 1000.0

    def placement(self, M: int, threshold: Threshold) -> PlacementSpec:
        if M <= 0:
            raise ValueError("M must be positive")
        a = self.C * threshold.ratio
        one_minus_a = 1.0 - a
        if one_minus_a < 0:
            z_raw = float("nan")
        else:
            z_raw = self.gamma * math.pow(one_minus_a, 2.0 / 3.0) * math.pow(M, 1.0 / 3.0)
        z = math.floor(z_raw + 0.5) if math.isfinite(z_raw) else -1
        valid = 0.0 <= a < 1.0 and 1 <= z < M
        return PlacementSpec(
            candidate_id=self.candidate_id,
            C=self.C,
            gamma=self.gamma,
            a=a,
            z_raw=z_raw if math.isfinite(z_raw) else -1.0,
            z=z,
            valid=valid,
            status="ok" if valid else "invalid_placement",
        )


def direct_holdout_spec(a_units: int, z: int, *, frozen_prediction: bool = False) -> PlacementSpec:
    a = a_units / 1000.0
    candidate_id = "holdout-a%04d-z%03d%s" % (
        a_units,
        z,
        "-frozen" if frozen_prediction else "",
    )
    return PlacementSpec(
        candidate_id=candidate_id,
        C=None,
        gamma=None,
        a=a,
        z_raw=float(z),
        z=z,
        valid=True,
        status="ok",
        is_frozen_prediction=frozen_prediction,
    )


def frozen_holdout_spec(C: float, gamma: float, a: float, M: int) -> PlacementSpec:
    z_raw = gamma * math.pow(1.0 - a, 2.0 / 3.0) * math.pow(M, 1.0 / 3.0)
    z = math.floor(z_raw + 0.5)
    valid = 0.0 <= a < 1.0 and 1 <= z < M
    return PlacementSpec(
        candidate_id="frozen-prediction",
        C=C,
        gamma=gamma,
        a=a,
        z_raw=z_raw,
        z=z,
        valid=valid,
        status="ok" if valid else "invalid_placement",
        is_frozen_prediction=True,
    )
