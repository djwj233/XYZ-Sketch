import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from . import constants as const
from .artifacts import canonical_sha256, sha256_file


def derive_seed(domain: str, d: int, trial: int, role: str) -> int:
    material = "figure2|%d|%s|%d|%d|%s" % (const.BASE_SEED, domain, d, trial, role)
    return int.from_bytes(hashlib.sha256(material.encode("ascii")).digest()[:8], "big")


def derive_internal_seed(
    domain: str, d: int, trial: int, algorithm: str, profile_hash: str, role: str
) -> int:
    material = "figure2|%d|%s|%d|%d|%s|%s|%s" % (
        const.BASE_SEED, domain, d, trial, algorithm, profile_hash, role
    )
    return int.from_bytes(hashlib.sha256(material.encode("ascii")).digest()[:8], "big")


def rounded_resource(ratio_units: int, d: int, scale: int = 1000) -> int:
    return (ratio_units * d * 2 + scale) // (2 * scale)


def actual_external_cells(expected: int) -> int:
    cells = expected + expected // 2
    while cells % 4:
        cells += 1
    return cells


def _external_representatives(d: int) -> Dict[int, Tuple[int, int]]:
    grid = const.RATIO_GRIDS["external_iblt"]
    representatives: Dict[int, Tuple[int, int]] = {}
    for units in range(grid["minimum"], grid["maximum"] + 1, grid["fine_step"]):
        resource = rounded_resource(units, d, grid["scale"])
        identity = actual_external_cells(resource)
        current = representatives.get(identity)
        if current is None or (resource, units) < current:
            representatives[identity] = (resource, units)
    return representatives


def _candidate(algorithm: str, d: int, grid_units: int) -> Dict[str, Any]:
    grid = const.RATIO_GRIDS[algorithm]
    resource = rounded_resource(grid_units, d, grid["scale"])
    identity = actual_external_cells(resource) if algorithm == "external_iblt" else resource
    expected_units = grid_units
    if algorithm == "external_iblt":
        resource, expected_units = _external_representatives(d)[identity]
    return {
        "grid_ratio_units": grid_units,
        "ratio_units": expected_units,
        "expected_ratio_units": expected_units,
        "ratio": expected_units / grid["scale"],
        "resource": resource,
        "actual_cells": identity if algorithm == "external_iblt" else resource,
    }


def coarse_candidates(algorithm: str, d: int) -> Tuple[Dict[str, Any], ...]:
    grid = const.RATIO_GRIDS[algorithm]
    rows = []
    seen = set()
    for units in range(grid["minimum"], grid["maximum"] + 1, grid["coarse_step"]):
        candidate = _candidate(algorithm, d, units)
        identity = int(candidate["actual_cells"] if algorithm == "external_iblt" else
                       candidate["resource"])
        if identity in seen:
            continue
        seen.add(identity)
        rows.append(candidate)
    return tuple(rows)


def possible_fine_candidates(algorithm: str, d: int) -> Tuple[Dict[str, Any], ...]:
    grid = const.RATIO_GRIDS[algorithm]
    rows = []
    coarse_identities = {
        int(row["actual_cells"] if algorithm == "external_iblt" else row["resource"])
        for row in coarse_candidates(algorithm, d)
    }
    for left in range(grid["minimum"], grid["maximum"], grid["coarse_step"]):
        values = []
        seen = set(coarse_identities)
        for units in range(left + grid["fine_step"], left + grid["coarse_step"], grid["fine_step"]):
            candidate = _candidate(algorithm, d, units)
            identity = int(candidate["actual_cells"] if algorithm == "external_iblt" else
                           candidate["resource"])
            if identity in seen:
                continue
            seen.add(identity)
            values.append(candidate)
        rows.append({"left_ratio_units": left, "right_ratio_units": left + grid["coarse_step"], "candidates": values})
    return tuple(rows)


def candidate_budget() -> Dict[str, Any]:
    algorithms = []
    total_d = sum(const.DIFFERENCES)
    for algorithm in const.RATIO_GRIDS:
        scales = []
        for d in const.DIFFERENCES:
            coarse = coarse_candidates(algorithm, d)
            fine_intervals = possible_fine_candidates(algorithm, d)
            maximum = len(coarse) + max(len(row["candidates"]) for row in fine_intervals)
            if maximum > const.MAX_CANDIDATES[algorithm]:
                raise ValueError("candidate budget exceeds protocol")
            scales.append({
                "d": d,
                "coarse": list(coarse),
                "possible_fine_intervals": list(fine_intervals),
                "maximum_executed_candidates": maximum,
                "maximum_updates": maximum * const.DISCOVERY_TRIALS * d,
            })
        update_bound = const.MAX_DISCOVERY_UPDATE_MULTIPLIER[algorithm] * total_d
        if sum(row["maximum_updates"] for row in scales) > update_bound:
            raise ValueError("global update budget exceeds protocol")
        algorithms.append({
            "algorithm": algorithm,
            "scales": scales,
            "global_maximum_updates": sum(row["maximum_updates"] for row in scales),
            "protocol_update_bound": update_bound,
        })
    return {
        "protocol_version": const.PROTOCOL_VERSION,
        "executes_trials": False,
        "d_values": list(const.DIFFERENCES),
        "discovery_trials": const.DISCOVERY_TRIALS,
        "algorithms": algorithms,
        "riblt": {"trials_per_d": 100, "maximum_symbols_per_trial": "3d", "quantile": "q[90]"},
    }


def _git_commit(path: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(path), check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ).stdout.strip()


def load_frozen(path: Path = const.DEFAULT_FROZEN) -> Tuple[Dict[str, Any], str]:
    value = json.loads(path.read_text())
    if value.get("status") != "selected" or value.get("protocol_version") != "figure1bc-v4":
        raise ValueError("Figure 2 requires selected figure1bc-v4 parameters")
    return value, sha256_file(path)


def profile_manifest(frozen_path: Path = const.DEFAULT_FROZEN) -> Dict[str, Any]:
    frozen, frozen_sha = load_frozen(frozen_path)
    threshold = json.loads(const.THRESHOLD.read_text())
    row = next(item for item in threshold if item["k"] == 2 and item["ell"] == 6)
    a = float(frozen["C_cal"]) * float(row["c_peel"]) / float(row["c_orient"])
    external_patch = subprocess.run(
        ["git", "diff", "--", "iblt.h", "iblt.cpp"],
        cwd=str(const.REPO_DIR / "external" / "IBLT_Cplusplus"), check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    profiles = {
        "xyz": {"k": 2, "ell": 6, "mode": "circular", "dedup": True, "a": a, "gamma": frozen["gamma_cal"]},
        "minisketch": {"bits": 30, "capacity": "d", "decode_max_elements": "d", "implementation_rule": "2_if_supported_else_0"},
        "external_iblt": {"N_HASH": 4, "N_HASHCHECK": 11, "value_size": 0, "count_bits": 25, "key_sum_bits": 30, "key_check_bits": 32, "cell_bits": 87, "source_commit": const.SOURCE_COMMITS["external_iblt"], "allowed_wire_patch_sha256": hashlib.sha256(external_patch).hexdigest()},
        "project_iblt": {"hash_count_rule": "4_if_d<200_else_3", "fingerprint_seed": 229},
        "riblt": {"symbol_bits": 30, "hash_bits": 49, "count_bits": 25, "coded_symbol_bits": 104, "hash": "SipHash-2-4-truncated", "max_d_hash_collision_union_bound": 0.001, "source_commit": const.SOURCE_COMMITS["riblt"]},
        "cpisync": {"m_bar": "d", "bits": 30, "epsilon": 4, "redundant": 0, "hashes": False, "one_way": True, "source_commit": const.SOURCE_COMMITS["cpisync"]},
    }
    for algorithm, value in profiles.items():
        value["profile_hash"] = canonical_sha256(value)
    execution_rules = {
        "xyz": {"payload": "packed_sketch_state_only"},
        "minisketch": {"payload": "serialized_syndrome_only", "bob_membership": "prepared_input_set"},
        "external_iblt": {"payload": "serialized_cells_only"},
        "project_iblt": {"payload": "serialized_cells_only", "batch_input_transfer": "move_prepared_vector"},
        "riblt": {"payload": "coded_symbols_only", "fixed_cap_api": "Sketch"},
        "cpisync": {"payload": "upstream_CommString_transcript", "data_object_construction_timed": False},
    }
    return {
        "protocol_version": const.PROTOCOL_VERSION,
        "frozen_parameters_sha256": frozen_sha,
        "threshold_sha256": const.THRESHOLD_SHA256,
        "profiles": profiles,
        "execution_rules": execution_rules,
        "shared_session_configuration": [
            "algorithm", "d", "w", "selected_resource", "profile", "public_randomness"
        ],
        "wrapper_payload_bytes": 0,
        "presentation": None,
        "presentation_affects_trials": False,
    }
