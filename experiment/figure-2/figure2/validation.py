import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping

from . import constants as const
from .artifacts import canonical_sha256, sha256_file
from .config import derive_internal_seed, profile_manifest
from .engine import Figure2Engines


def golden_results(engines: Figure2Engines) -> Dict[str, Any]:
    tests = engines.self_tests()
    expected = {
        "dataset": None,
        "xyz": 368,
        "minisketch": 64,
        "external_iblt": 352,
        "project_iblt": 288,
        "riblt": 312,
        "cpisync": 392,
    }
    for algorithm, bits in expected.items():
        if tests[algorithm].get("passed") is not True:
            raise RuntimeError("golden self-test failed: %s" % algorithm)
        if bits is not None and int(tests[algorithm]["golden_total_bits"]) != bits:
            raise RuntimeError("golden bit count differs: %s" % algorithm)
        if algorithm not in {"dataset", "cpisync"} \
                and tests[algorithm].get("malformed_state_rejected") is not True:
            raise RuntimeError("malformed state was not rejected: %s" % algorithm)
    if int(tests["cpisync"].get("golden_state_bits", -1)) != 64 \
            or int(tests["cpisync"].get("golden_control_bits", -1)) != 328:
        raise RuntimeError("CPISync golden state/control split differs")
    if tests["riblt"].get("encoder_sketch_equivalent") is not True:
        raise RuntimeError("RIBLT Encoder and fixed-cap Sketch differ")
    if int(tests["riblt"].get("encoder_sketch_equivalence_cases", 0)) != 18:
        raise RuntimeError("RIBLT Encoder/Sketch equivalence coverage differs")
    return {
        "status": "passed",
        "protocol_version": const.PROTOCOL_VERSION,
        "tests": tests,
        "executable_sha256": {
            name: sha256_file(path) for name, path in engines.executables.items()
        },
    }


def _equivalence_seed(profile_hash: str, fixture_index: int, role: str) -> int:
    material = "figure2|equivalence|%s|%d|%s" % (profile_hash, fixture_index, role)
    return int.from_bytes(hashlib.sha256(material.encode("ascii")).digest()[:8], "big")


def equivalence_results(engines: Figure2Engines, profiles: Mapping[str, Any]) -> Dict[str, Any]:
    resources = {
        "xyz": (10, 25, 40),
        "external_iblt": (50, 100, 150),
        "project_iblt": (80, 190, 300),
        "riblt": (100, 200, 300),
    }
    rows: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="figure2-equivalence-") as temporary:
        root = Path(temporary)
        for algorithm, algorithm_resources in resources.items():
            profile_hash = profiles["profiles"][algorithm]["profile_hash"]
            for fixture_index in range(10):
                full = root / ("%s-%02d-full.bin" % (algorithm, fixture_index))
                difference = root / ("%s-%02d-difference.bin" % (algorithm, fixture_index))
                seeds = {
                    role: _equivalence_seed(profile_hash, fixture_index, role)
                    for role in ("identity", "alice_order", "bob_order")
                }
                dataset = engines.create_equivalence_pair(
                    full, difference, d=100, set_size=1000,
                    identity_seed=seeds["identity"], alice_seed=seeds["alice_order"],
                    bob_seed=seeds["bob_order"],
                )
                for resource in algorithm_resources:
                    arguments: Dict[str, Any] = {"resource": resource, "timeout": 60}
                    if algorithm == "xyz":
                        arguments.update({"a": 0.2, "z": 1, "internal_seed": seeds["identity"]})
                    elif algorithm == "riblt":
                        arguments.update({
                            "siphash_k0": _equivalence_seed(profile_hash, fixture_index, "siphash_k0"),
                            "siphash_k1": _equivalence_seed(profile_hash, fixture_index, "siphash_k1"),
                            "internal_seed": seeds["identity"],
                        })
                    full_result = engines.run(algorithm, full, **arguments)
                    difference_result = engines.run(algorithm, difference, **arguments)
                    matched = (
                        full_result.residual_sha256 == difference_result.residual_sha256
                        and full_result.success == difference_result.success
                        and full_result.failure_reason == difference_result.failure_reason
                        and full_result.alice_output_sha256 == difference_result.alice_output_sha256
                        and full_result.bob_output_sha256 == difference_result.bob_output_sha256
                    )
                    if not matched:
                        raise RuntimeError("equivalence failed for %s fixture %d resource %d" % (
                            algorithm, fixture_index, resource
                        ))
                    rows.append({
                        "algorithm": algorithm,
                        "profile_hash": profile_hash,
                        "fixture_index": fixture_index,
                        "resource": resource,
                        "dataset": dataset,
                        "residual_sha256": full_result.residual_sha256,
                        "decode_success": full_result.success,
                        "failure_reason": full_result.failure_reason,
                        "matched": True,
                    })
    return {
        "status": "passed",
        "protocol_version": const.PROTOCOL_VERSION,
        "fixture_count": 10,
        "configuration_rows": len(rows),
        "rows": rows,
    }


def smoke_results(engines: Figure2Engines, profiles: Mapping[str, Any]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="figure2-smoke-") as temporary:
        dataset_path = Path(temporary) / "shared.bin"
        dataset = engines.create_dataset(
            dataset_path, full=False, d=100, set_size=0,
            identity_seed=101, alice_seed=102, bob_seed=103,
        )
        arguments = {
            "xyz": {"resource": 40, "a": profiles["profiles"]["xyz"]["a"], "z": 1, "internal_seed": 104},
            "minisketch": {"internal_seed": 105},
            "external_iblt": {"resource": 150},
            "project_iblt": {"resource": 300},
            "riblt": {"resource": 300, "siphash_k0": 106, "siphash_k1": 107, "internal_seed": 108},
            "cpisync": {},
        }
        rows = []
        for algorithm in const.ALGORITHMS:
            result = engines.run(algorithm, dataset_path, timeout=60, **arguments[algorithm])
            if not result.success or result.alice_output_sha256 != dataset["alice_only_sha256"] \
                    or result.bob_output_sha256 != dataset["bob_only_sha256"]:
                raise RuntimeError("shared smoke failed: %s" % algorithm)
            rows.append({
                "algorithm": algorithm,
                "success": True,
                "state_bits": result.state_bits,
                "control_bits": result.control_bits,
                "total_payload_bits": result.total_payload_bits,
                "alice_output_sha256": result.alice_output_sha256,
                "bob_output_sha256": result.bob_output_sha256,
            })
    return {
        "status": "passed",
        "formal_data": False,
        "protocol_version": const.PROTOCOL_VERSION,
        "dataset": dataset,
        "algorithms": rows,
    }
