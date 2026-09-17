import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from . import constants as const


@dataclass(frozen=True)
class EngineResult:
    algorithm: str
    success: bool
    failure_reason: str
    logical_state_bits: int
    state_bits: int
    control_bits: int
    total_payload_bits: int
    update_alice_cpu: float
    update_bob_cpu: float
    sender_cpu: float
    transfer_cpu: float
    receiver_cpu: float
    alice_output_sha256: str
    bob_output_sha256: str
    residual_sha256: str
    required_symbols: int

    @property
    def decode_cpu(self) -> float:
        return self.sender_cpu + self.transfer_cpu + self.receiver_cpu


class EngineExecutionError(RuntimeError):
    def __init__(self, returncode: int, stderr: str) -> None:
        super().__init__("engine failed (%d): %s" % (returncode, stderr))
        self.returncode = returncode
        self.stderr = stderr


class Figure2Engines:
    def __init__(
        self,
        executables: Mapping[str, Path] = const.EXECUTABLES,
        *,
        cpu_affinity: Optional[int] = None,
        memory_limit_bytes: Optional[int] = None,
    ) -> None:
        self.executables = {name: path.resolve() for name, path in executables.items()}
        missing = [name for name, path in self.executables.items() if not path.is_file()]
        if missing:
            raise FileNotFoundError("missing Figure 2 executables: %s" % ", ".join(missing))
        self.cpu_affinity = cpu_affinity
        self.memory_limit_bytes = memory_limit_bytes

    def _execute(self, command: Sequence[str], timeout: Optional[float] = None) -> str:
        actual_command = list(command)
        if self.memory_limit_bytes is not None:
            actual_command = [
                "prlimit", "--as=%d" % self.memory_limit_bytes, "--"
            ] + actual_command
        if self.cpu_affinity is not None:
            actual_command = ["taskset", "-c", str(self.cpu_affinity)] + actual_command
        completed = subprocess.run(
            actual_command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout,
        )
        if completed.returncode != 0:
            raise EngineExecutionError(completed.returncode, completed.stderr.strip())
        return completed.stdout.strip()

    def self_tests(self) -> Dict[str, Any]:
        output = {}
        for name, path in self.executables.items():
            output[name] = json.loads(self._execute((str(path), "--self-test"), timeout=60))
        return output

    def create_dataset(
        self,
        output: Path,
        *,
        full: bool,
        d: int,
        set_size: int,
        identity_seed: int,
        alice_seed: int,
        bob_seed: int,
    ) -> Dict[str, Any]:
        return json.loads(self._execute((
            str(self.executables["dataset"]), str(output), "full" if full else "difference",
            str(d), str(set_size), str(identity_seed), str(alice_seed), str(bob_seed),
        ), timeout=300))

    def create_equivalence_pair(
        self,
        full_path: Path,
        difference_path: Path,
        *,
        d: int,
        set_size: int,
        identity_seed: int,
        alice_seed: int,
        bob_seed: int,
    ) -> Dict[str, Any]:
        return json.loads(self._execute((
            str(self.executables["dataset"]), "--equivalence", str(full_path),
            str(difference_path), str(d), str(set_size), str(identity_seed),
            str(alice_seed), str(bob_seed), "figure2-equivalence-v1",
        ), timeout=300))

    @staticmethod
    def _parse(line: str) -> EngineResult:
        fields = line.split("\t")
        if len(fields) != 17 or fields[0] != const.ENGINE_PROTOCOL:
            raise RuntimeError("malformed Figure 2 engine output")
        result = EngineResult(
            algorithm=fields[1], success=fields[2] == "1", failure_reason=fields[3],
            logical_state_bits=int(fields[4]), state_bits=int(fields[5]),
            control_bits=int(fields[6]), total_payload_bits=int(fields[7]),
            update_alice_cpu=float(fields[8]), update_bob_cpu=float(fields[9]),
            sender_cpu=float(fields[10]), transfer_cpu=float(fields[11]),
            receiver_cpu=float(fields[12]), alice_output_sha256=fields[13],
            bob_output_sha256=fields[14], residual_sha256=fields[15],
            required_symbols=int(fields[16]),
        )
        if result.total_payload_bits != result.state_bits + result.control_bits:
            raise RuntimeError("engine payload accounting mismatch")
        return result

    def run(
        self,
        algorithm: str,
        dataset: Path,
        *,
        resource: Optional[int] = None,
        a: Optional[float] = None,
        z: Optional[int] = None,
        internal_seed: int = 0,
        siphash_k0: int = 0,
        siphash_k1: int = 0,
        timeout: Optional[float] = None,
        discover_riblt: bool = False,
    ) -> EngineResult:
        executable = str(self.executables[algorithm])
        if algorithm == "xyz":
            command = (executable, "--run", str(dataset), str(resource), repr(a), str(z), str(internal_seed))
        elif algorithm == "minisketch":
            command = (executable, "--run", str(dataset), str(internal_seed))
        elif algorithm in {"external_iblt", "project_iblt"}:
            command = (executable, "--run", str(dataset), str(resource))
        elif algorithm == "riblt":
            command = (
                executable, "--discover" if discover_riblt else "--run", str(dataset),
                str(resource), str(siphash_k0), str(siphash_k1), str(internal_seed),
            )
        elif algorithm == "cpisync":
            command = (executable, "--run", str(dataset))
        else:
            raise ValueError("unknown algorithm")
        result = self._parse(self._execute(command, timeout=timeout))
        if result.algorithm != algorithm:
            raise RuntimeError("engine algorithm label mismatch")
        return result
