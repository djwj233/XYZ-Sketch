"""Strict subprocess adapter for the C++17 simulation engine."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

from . import constants as const
from .simulator import PlacementGeometry


ENGINE_PROTOCOL = "figure1bc-engine-v1"


@dataclass(frozen=True)
class EngineTrial:
    trial_index: int
    stream_sha256: str
    residual_by_group: Mapping[str, int]


class CppEngine:
    def __init__(self, executable: Path) -> None:
        self.executable = executable.resolve()
        if not self.executable.is_file():
            raise FileNotFoundError(str(self.executable))
        if not self.executable.stat().st_mode & 0o111:
            raise PermissionError("C++ engine is not executable: %s" % self.executable)

    def evaluate(
        self,
        *,
        base_seed: int,
        domain: str,
        d: int,
        M: int,
        trials: int,
        geometries: Mapping[str, PlacementGeometry],
    ) -> Tuple[EngineTrial, ...]:
        if domain not in const.SEED_DOMAINS:
            raise ValueError("unknown engine seed domain")
        ordered = sorted(geometries.items())
        lines = [
            ENGINE_PROTOCOL,
            "%d\t%s\t%d\t%d\t%d\t%d"
            % (base_seed, domain, d, M, trials, len(ordered)),
        ]
        for group_id, geometry in ordered:
            if any(character.isspace() for character in group_id):
                raise ValueError("engine group id may not contain whitespace")
            lines.append(
                "%s\t%d\t%d"
                % (group_id, geometry.circular_base_range, geometry.z)
            )
        payload = ("\n".join(lines) + "\n").encode("ascii")
        completed = subprocess.run(
            [str(self.executable)],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "C++ engine failed (%d): %s"
                % (completed.returncode, completed.stderr.decode("utf-8", "replace").strip())
            )
        output = completed.stdout.decode("ascii").splitlines()
        if not output or output[0] != ENGINE_PROTOCOL:
            raise RuntimeError("C++ engine returned an invalid protocol header")

        results: List[EngineTrial] = []
        current_trial = None
        current_stream = None
        current_groups: Dict[str, int] = {}
        expected_groups = {group_id for group_id, _ in ordered}
        for line in output[1:]:
            fields = line.split("\t")
            if fields[0] == "T" and len(fields) == 3:
                if current_trial is not None:
                    if set(current_groups) != expected_groups:
                        raise RuntimeError("C++ engine omitted or duplicated a placement group")
                    results.append(
                        EngineTrial(current_trial, current_stream, dict(current_groups))
                    )
                current_trial = int(fields[1])
                current_stream = fields[2]
                if len(current_stream) != 64:
                    raise RuntimeError("C++ engine returned an invalid stream SHA-256")
                current_groups = {}
            elif fields[0] == "G" and len(fields) == 4 and current_trial is not None:
                group_id = fields[1]
                residual = int(fields[2])
                success = int(fields[3])
                if group_id in current_groups or group_id not in expected_groups:
                    raise RuntimeError("C++ engine returned an unexpected placement group")
                if not 0 <= residual <= d or success != int(residual == 0):
                    raise RuntimeError("C++ engine returned an invalid peel result")
                current_groups[group_id] = residual
            else:
                raise RuntimeError("C++ engine returned a malformed row: %s" % line)
        if current_trial is not None:
            if set(current_groups) != expected_groups:
                raise RuntimeError("C++ engine omitted or duplicated a placement group")
            results.append(EngineTrial(current_trial, current_stream, dict(current_groups)))
        if [row.trial_index for row in results] != list(range(trials)):
            raise RuntimeError("C++ engine returned a noncanonical trial sequence")
        return tuple(results)

    def place_fixture(
        self,
        M: int,
        a: float,
        z: int,
        words: Tuple[int, int, int],
    ) -> Tuple[int, int, int, Tuple[int, ...]]:
        completed = subprocess.run(
            [
                str(self.executable),
                "place",
                str(M),
                repr(a),
                str(z),
                str(words[0]),
                str(words[1]),
                str(words[2]),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "C++ placement fixture failed: %s"
                % completed.stderr.decode("utf-8", "replace").strip()
            )
        fields = completed.stdout.decode("ascii").strip().split("\t")
        if len(fields) not in (4, 5):
            raise RuntimeError("C++ placement fixture returned a malformed row")
        return (
            int(fields[0]),
            int(fields[1]),
            int(fields[2]),
            tuple(int(value) for value in fields[3:]),
        )
