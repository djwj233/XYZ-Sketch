import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from . import constants as const


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_thresholds() -> Dict[Tuple[int, int], Mapping[str, Any]]:
    if sha256_file(const.THRESHOLD_PATH) != const.EXPECTED_THRESHOLD_SHA256:
        raise ValueError("threshold artifact SHA-256 mismatch")
    rows = json.loads(const.THRESHOLD_PATH.read_text(encoding="utf-8"))
    if len(rows) != 48:
        raise ValueError("threshold artifact must contain 48 rows")
    result = {(int(row["k"]), int(row["ell"])): row for row in rows}
    for panel in const.PANELS:
        if panel not in result:
            raise ValueError("threshold artifact lacks panel %r" % (panel,))
    return result


def load_frozen(path: Path) -> Tuple[Dict[str, Any], str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("status") != "selected" or value.get("protocol_version") != "figure1bc-v4":
        raise ValueError("Figure 1(a) requires selected figure1bc-v4 parameters")
    if float(value["delta"]) != const.DELTA:
        raise ValueError("frozen delta differs from 0.1")
    expected_d = float(value["gamma_cal"]) * math.pow(math.log(1.0 / const.DELTA), 1.0 / 3.0)
    if not math.isclose(expected_d, float(value["D_cal"]), rel_tol=0.0, abs_tol=1e-15):
        raise ValueError("frozen D/gamma relation is invalid")
    return value, sha256_file(path)


def derive_seed(phase: str, k: int, ell: int, trial_index: int, role: str) -> int:
    if role not in const.SEED_ROLES:
        raise ValueError("unknown seed role")
    material = "figure1a|%d|%s|%d|%d|%d|%s" % (
        const.BASE_SEED, phase, k, ell, trial_index, role
    )
    return int.from_bytes(hashlib.sha256(material.encode("ascii")).digest()[:8], "big")


@dataclass(frozen=True)
class PanelParameters:
    k: int
    ell: int
    c_peel: float
    c_orient: float
    C: float
    gamma: float
    D: float
    delta: float
    circular_a: float

    @classmethod
    def create(
        cls,
        k: int,
        ell: int,
        thresholds: Mapping[Tuple[int, int], Mapping[str, Any]],
        frozen: Mapping[str, Any],
    ) -> "PanelParameters":
        row = thresholds[(k, ell)]
        c_peel = float(row["c_peel"])
        c_orient = float(row["c_orient"])
        C = float(frozen["C_cal"])
        circular_a = C * c_peel / c_orient
        if not 0.0 <= circular_a < 1.0:
            raise ValueError("circular a is invalid")
        return cls(
            k, ell, c_peel, c_orient, C, float(frozen["gamma_cal"]),
            float(frozen["D_cal"]), float(frozen["delta"]), circular_a,
        )

    def placement(self, mode: str, M: int) -> Tuple[float, float, int]:
        if mode == "iid":
            return 0.0, 0.0, 0
        a = 0.0 if mode == "naive" else self.circular_a
        z_raw = self.gamma * math.pow(1.0 - a, 2.0 / 3.0) * math.pow(M, 1.0 / 3.0)
        z = math.floor(z_raw + 0.5)
        if not 1 <= z < M:
            raise ValueError("spatial placement has invalid z")
        return a, z_raw, z

    def center(self, mode: str) -> int:
        if mode == "iid":
            return math.ceil(const.D / self.c_peel)
        a = 0.0 if mode == "naive" else self.circular_a
        M = math.ceil(const.D / self.c_orient)
        seen = set()
        for _ in range(100):
            if M in seen:
                raise RuntimeError("spatial M0 iteration entered a cycle")
            seen.add(M)
            _a, _z_raw, z = self.placement(mode, M)
            denominator = z if mode == "naive" else z + a
            next_M = math.ceil((z + 1.0) / denominator * const.D / self.c_orient)
            if next_M == M:
                return M
            M = next_M
        raise RuntimeError("spatial M0 iteration did not converge")


@dataclass(frozen=True)
class ConfigSpec:
    k: int
    ell: int
    mode: str
    M: int
    C: float
    gamma: float
    D: float
    delta: float
    a: float
    z_raw: float
    z: int

    @property
    def config_id(self) -> str:
        return "k%d-l%d-%s-M%06d" % (self.k, self.ell, self.mode, self.M)

    @property
    def bits_per_cell(self) -> int:
        return 30 * self.ell + math.ceil(math.log2(2 * self.ell + 1))

    @property
    def logical_state_bits(self) -> int:
        return self.M * self.bits_per_cell

    @property
    def state_bits(self) -> int:
        return 8 * math.ceil(self.logical_state_bits / 8)

    @property
    def total_payload_bits(self) -> int:
        return self.state_bits + const.CONTROL_BITS

    @property
    def R_w30(self) -> float:
        return self.total_payload_bits / (30.0 * const.D)


def make_spec(parameters: PanelParameters, mode: str, M: int) -> ConfigSpec:
    a, z_raw, z = parameters.placement(mode, M)
    return ConfigSpec(
        parameters.k, parameters.ell, mode, M, parameters.C, parameters.gamma,
        parameters.D, parameters.delta, a, z_raw, z,
    )


def initial_m_values(parameters: PanelParameters, mode: str) -> Tuple[int, ...]:
    center = parameters.center(mode)
    step = const.COARSE_STEP[parameters.ell]
    radius_steps = math.ceil(0.15 * center / step)
    return tuple(center + offset * step for offset in range(-radius_steps, radius_steps + 1))


def extended_m_values(parameters: PanelParameters, mode: str, rounds: int, direction: str) -> Tuple[int, ...]:
    if rounds <= 0 or direction not in {"lower", "upper"}:
        raise ValueError("invalid extension request")
    center = parameters.center(mode)
    step = const.COARSE_STEP[parameters.ell]
    previous_steps = math.ceil((0.15 + 0.10 * (rounds - 1)) * center / step)
    next_steps = math.ceil((0.15 + 0.10 * rounds) * center / step)
    if direction == "lower":
        values = (center - offset * step for offset in range(previous_steps + 1, next_steps + 1))
    else:
        values = (center + offset * step for offset in range(previous_steps + 1, next_steps + 1))
    return tuple(sorted(value for value in values if value > 1))


def build_initial_manifest(frozen: Mapping[str, Any], frozen_sha256: str) -> Dict[str, Any]:
    thresholds = load_thresholds()
    curves = []
    total_points = 0
    for k, ell in const.PANELS:
        parameters = PanelParameters.create(k, ell, thresholds, frozen)
        for mode in const.MODES:
            values = initial_m_values(parameters, mode)
            total_points += len(values)
            curves.append(
                {
                    "k": k,
                    "ell": ell,
                    "mode": mode,
                    "M0": parameters.center(mode),
                    "coarse_step": const.COARSE_STEP[ell],
                    "initial_M": list(values),
                    "c_peel": parameters.c_peel,
                    "c_orient": parameters.c_orient,
                    "a": 0.0 if mode != "circular" else parameters.circular_a,
                }
            )
    return {
        "protocol_version": const.PROTOCOL_VERSION,
        "executes_trials": False,
        "d": const.D,
        "set_size_A": const.SET_SIZE,
        "set_size_B": const.SET_SIZE,
        "common_size": const.COMMON_SIZE,
        "difference_A": const.ONE_DIRECTION,
        "difference_B": const.ONE_DIRECTION,
        "coarse_trials_per_point": const.COARSE_TRIALS,
        "initial_point_count": total_points,
        "initial_logical_cell_trials": total_points * const.COARSE_TRIALS,
        "workers": const.WORKERS,
        "frozen_parameters_sha256": frozen_sha256,
        "threshold_sha256": const.EXPECTED_THRESHOLD_SHA256,
        "curves": curves,
    }
