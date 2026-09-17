"""Load the prevalidated threshold artifact without recomputing it."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

from . import constants as const


@dataclass(frozen=True)
class Threshold:
    c_peel: float
    c_orient: float
    sha256: str

    @property
    def ratio(self) -> float:
        return self.c_peel / self.c_orient


def load_threshold(path: Path = const.THRESHOLD_PATH) -> Threshold:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != const.EXPECTED_THRESHOLD_SHA256:
        raise ValueError(
            "threshold artifact SHA-256 mismatch: expected %s, got %s"
            % (const.EXPECTED_THRESHOLD_SHA256, digest)
        )
    values: List[Any] = json.loads(raw.decode("utf-8"))
    if len(values) != const.EXPECTED_THRESHOLD_ENTRIES:
        raise ValueError("threshold artifact must contain exactly 48 entries")
    matches = [row for row in values if row.get("k") == const.K and row.get("ell") == const.ELL]
    if len(matches) != 1:
        raise ValueError("threshold artifact must contain exactly one (k,ell)=(2,6) row")
    row = matches[0]
    c_peel = float(row["c_peel"])
    c_orient = float(row["c_orient"])
    if not 0.0 < c_peel <= c_orient:
        raise ValueError("invalid (2,6) threshold ordering")
    return Threshold(c_peel=c_peel, c_orient=c_orient, sha256=digest)
