"""Canonical serialization, hashing, and atomic artifact helpers."""

import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from . import constants as const


def _validate_json_value(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number at %s" % path)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_json_value(item, "%s[%d]" % (path, index))
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object key at %s is not a string" % path)
            _validate_json_value(item, "%s.%s" % (path, key))
        return
    raise TypeError("unsupported canonical JSON value at %s: %r" % (path, type(value)))


def canonical_json_bytes(value: Any) -> bytes:
    _validate_json_value(value)
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_bytes(path: Path, data: bytes, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and path.exists():
        raise FileExistsError(str(path))
    descriptor, temporary_name = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive and path.exists():
            raise FileExistsError(str(path))
        os.replace(str(temporary_path), str(path))
        directory_fd = os.open(str(path.parent), os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def atomic_write_text(path: Path, text: str, *, exclusive: bool = False) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), exclusive=exclusive)


def atomic_write_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value), exclusive=exclusive)


def atomic_write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    data = b"".join(canonical_json_bytes(dict(row)) for row in rows)
    atomic_write_bytes(path, data)


def atomic_write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise", lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fields})
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary_path), str(path))
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def source_tree_sha256(source_root: Path = const.EXPERIMENT_DIR) -> str:
    digest = hashlib.sha256()
    included = []
    for path in source_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source_root)
        if any(
            part in {"__pycache__", "results", ".pytest_cache", "build"}
            for part in relative.parts
        ):
            continue
        if path.suffix not in {".py", ".cpp", ".h", ".md", ".json", ".txt", ".sh"} and path.name != "Makefile":
            continue
        included.append((relative.as_posix(), path))
    for relative, path in sorted(included):
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _git_output(args: Sequence[str], repo: Path) -> str:
    try:
        completed = subprocess.run(
            ["git"] + list(args),
            cwd=str(repo),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return completed.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def repository_manifest(repo: Path) -> Dict[str, str]:
    diff = _git_output(["diff", "--binary", "HEAD"], repo).encode("utf-8")
    status = _git_output(["status", "--short"], repo)
    return {
        "git_commit": _git_output(["rev-parse", "HEAD"], repo),
        "git_short_sha": _git_output(["rev-parse", "--short", "HEAD"], repo),
        "git_status": status,
        "tracked_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "source_tree_sha256": source_tree_sha256(),
    }


def _version_line(command: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            list(command),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        lines = completed.stdout.strip().splitlines()
        return lines[0] if lines else "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def build_manifest(engine_executable: Path) -> Dict[str, Any]:
    return {
        "protocol_version": const.PROTOCOL_VERSION,
        "engine_path": str(engine_executable.resolve()),
        "engine_sha256": sha256_file(engine_executable.resolve()),
        "cmake": _version_line(("cmake", "--version")),
        "cxx": _version_line(("g++", "--version")),
        "openssl": _version_line(("openssl", "version")),
        "cmake_build_type": "Release",
        "cxx_standard": "C++17",
    }


def environment_manifest() -> Dict[str, Any]:
    return {
        "protocol_version": const.PROTOCOL_VERSION,
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "timezone": datetime.now().astimezone().tzname(),
    }


def make_run_id(experiment: str, config_sha256: str, repo: Path) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short_sha = _git_output(["rev-parse", "--short", "HEAD"], repo)
    if short_sha == "unavailable":
        short_sha = "nogit"
    return "%s-%s-%s-%s" % (experiment, timestamp, short_sha, config_sha256[:12])


TERMINAL_STATES = frozenset(
    {
        "calibration_unbracketed",
        "no_eligible_candidate",
        "relative_search_boundary",
        "confirmation_failed",
        "confirmed",
        "selected",
        "complete",
        "failed",
    }
)


class RunDirectory:
    """A run directory that refuses reuse after a terminal state."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def create(cls, path: Path, initial_state: str, identity: Mapping[str, Any]) -> "RunDirectory":
        path.mkdir(parents=True, exist_ok=False)
        instance = cls(path)
        atomic_write_json(path / "run_identity.json", dict(identity), exclusive=True)
        atomic_write_json(
            path / "run_state.json",
            {"sequence": 0, "status": initial_state, "protocol_version": const.PROTOCOL_VERSION},
            exclusive=True,
        )
        atomic_write_text(path / "errors.log", "", exclusive=True)
        return instance

    @classmethod
    def open_for_resume(cls, path: Path) -> "RunDirectory":
        instance = cls(path)
        state = instance.read_state()
        if state["status"] in TERMINAL_STATES:
            raise RuntimeError("terminal run directories are immutable: %s" % state["status"])
        return instance

    def read_state(self) -> Dict[str, Any]:
        return json.loads((self.path / "run_state.json").read_text(encoding="utf-8"))

    def transition(self, expected: str, new: str, extra: Optional[Mapping[str, Any]] = None) -> None:
        state = self.read_state()
        if state["status"] != expected:
            raise RuntimeError("state transition expected %s, found %s" % (expected, state["status"]))
        next_state: Dict[str, Any] = {
            "sequence": int(state["sequence"]) + 1,
            "status": new,
            "protocol_version": const.PROTOCOL_VERSION,
        }
        if extra:
            next_state.update(extra)
        atomic_write_json(self.path / "run_state.json", next_state)

    def record_error(self, message: str) -> None:
        old = (self.path / "errors.log").read_text(encoding="utf-8")
        atomic_write_text(self.path / "errors.log", old + message.rstrip() + "\n")
