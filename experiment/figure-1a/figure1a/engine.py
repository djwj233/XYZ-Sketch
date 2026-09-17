import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from . import constants as const
from .config import ConfigSpec, derive_seed


@dataclass(frozen=True)
class EngineTrial:
    dataset: Mapping[str, Any]
    results: Mapping[str, Mapping[str, Any]]


class CppEngine:
    def __init__(self, executable: Path) -> None:
        self.executable = executable.resolve()
        if not self.executable.is_file():
            raise FileNotFoundError(str(self.executable))

    def self_test(self) -> str:
        completed = subprocess.run(
            [str(self.executable), "--self-test"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("engine self-test failed: %s" % completed.stderr.strip())
        return completed.stdout.strip()

    def evaluate(
        self,
        *,
        phase: str,
        k: int,
        ell: int,
        trial_index: int,
        specs: Sequence[ConfigSpec],
        set_size: int = const.SET_SIZE,
        difference: int = const.D,
        workers: int = const.WORKERS,
    ) -> EngineTrial:
        if not specs or any(spec.k != k or spec.ell != ell for spec in specs):
            raise ValueError("engine batch specs must share one panel")
        seeds = {
            role: derive_seed(phase, k, ell, trial_index, role)
            for role in const.SEED_ROLES
        }
        lines = [
            const.ENGINE_PROTOCOL,
            "%d %d %d %d %d %d %d"
            % (set_size, difference, k, ell, trial_index, len(specs), workers),
            "%d %d %d %d %d"
            % tuple(seeds[role] for role in const.SEED_ROLES),
        ]
        for spec in specs:
            lines.append(
                "%s %s %d %.17g %d"
                % (spec.config_id, spec.mode, spec.M, spec.a, spec.z)
            )
        completed = subprocess.run(
            [str(self.executable)],
            input="\n".join(lines) + "\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "engine batch failed (%d): %s" % (completed.returncode, completed.stderr.strip())
            )
        output = completed.stdout.splitlines()
        if len(output) != len(specs) + 2 or output[0] != const.ENGINE_PROTOCOL:
            raise RuntimeError("engine returned malformed batch length/header")
        dataset_fields = output[1].split("\t")
        if len(dataset_fields) != 9 or dataset_fields[0] != "D":
            raise RuntimeError("engine returned malformed dataset row")
        dataset = {
            "trial_index": int(dataset_fields[1]),
            "dataset_seconds": float(dataset_fields[2]),
            "dataset_sha256": dataset_fields[3],
            "dataset_seed": int(dataset_fields[4]),
            "alice_order_seed": int(dataset_fields[5]),
            "bob_order_seed": int(dataset_fields[6]),
            "decoder_seed": int(dataset_fields[7]),
            "hash_family_seed": int(dataset_fields[8]),
        }
        results: Dict[str, Mapping[str, Any]] = {}
        for line in output[2:]:
            fields = line.split("\t")
            if len(fields) != 13 or fields[0] != "R":
                raise RuntimeError("engine returned malformed result row")
            config_id = fields[1]
            if config_id in results:
                raise RuntimeError("engine duplicated config result")
            results[config_id] = {
                "success": fields[2] == "1",
                "failure_reason": fields[3],
                "logical_state_bits": int(fields[4]),
                "state_bits": int(fields[5]),
                "control_bits": int(fields[6]),
                "total_payload_bits": int(fields[7]),
                "alice_encode_seconds": float(fields[8]),
                "serialization_seconds": float(fields[9]),
                "bob_encode_seconds": float(fields[10]),
                "decode_seconds": float(fields[11]),
                "total_seconds": float(fields[12]),
            }
        if set(results) != {spec.config_id for spec in specs}:
            raise RuntimeError("engine omitted or added config results")
        return EngineTrial(dataset, results)
