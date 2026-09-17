"""Canonical, atomic, and reproducible Figure 1(a) artifacts."""

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


def _validate_json(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number at %s" % path)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_json(item, "%s[%d]" % (path, index))
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("non-string JSON key at %s" % path)
            _validate_json(item, "%s.%s" % (path, key))
        return
    raise TypeError("unsupported JSON value at %s: %r" % (path, type(value)))


def canonical_json_bytes(value: Any) -> bytes:
    _validate_json(value)
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ) + "\n").encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_bytes(path: Path, data: bytes, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and path.exists():
        raise FileExistsError(str(path))
    descriptor, temporary_name = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive and path.exists():
            raise FileExistsError(str(path))
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_text(path: Path, value: str, *, exclusive: bool = False) -> None:
    atomic_write_bytes(path, value.encode("utf-8"), exclusive=exclusive)


def atomic_write_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value), exclusive=exclusive)


def atomic_write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    atomic_write_bytes(path, b"".join(canonical_json_bytes(dict(row)) for row in rows))


def atomic_write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise", lineterminator="\n")
            writer.writeheader()
            for row in rows:
                encoded = {}
                for field in fields:
                    value = row.get(field, "")
                    encoded[field] = json.dumps(value, sort_keys=True, separators=(",", ":")) \
                        if isinstance(value, (dict, list)) else value
                writer.writerow(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def _git_output(repo: Path, arguments: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            ["git"] + list(arguments), cwd=str(repo), check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        return completed.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def source_tree_sha256(roots: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    files = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if any(part in {"__pycache__", ".pytest_cache", "build", "results"} for part in relative.parts):
                continue
            if path.suffix not in {".py", ".cpp", ".cc", ".h", ".md", ".json", ".txt"} \
                    and path.name not in {"CMakeLists.txt", "Makefile"}:
                continue
            files.append((root.name + "/" + relative.as_posix(), path))
    for relative, path in sorted(files):
        name = relative.encode("utf-8")
        content = path.read_bytes()
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def repository_manifest(repo: Path) -> Dict[str, Any]:
    tracked_diff = _git_output(repo, ["diff", "--binary", "HEAD"])
    return {
        "git_commit": _git_output(repo, ["rev-parse", "HEAD"]),
        "git_short_sha": _git_output(repo, ["rev-parse", "--short", "HEAD"]),
        "git_status": _git_output(repo, ["status", "--short"]),
        "tracked_diff_sha256": hashlib.sha256(tracked_diff.encode("utf-8")).hexdigest(),
        "figure1a_and_core_source_sha256": source_tree_sha256(
            (const.EXPERIMENT_DIR, repo / "XYZ-Sketch")
        ),
    }


def _version_line(command: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            list(command), check=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True,
        )
        return completed.stdout.strip().splitlines()[0]
    except (OSError, subprocess.CalledProcessError, IndexError):
        return "unavailable"


def build_manifest(engine: Path) -> Dict[str, Any]:
    return {
        "protocol_version": const.PROTOCOL_VERSION,
        "engine_path": str(engine.resolve()),
        "engine_sha256": sha256_file(engine.resolve()),
        "cmake": _version_line(("cmake", "--version")),
        "cxx": _version_line(("g++", "--version")),
        "openssl": _version_line(("openssl", "version")),
        "build_type": "Release",
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
        "logical_cpu_count": os.cpu_count(),
        "timezone": datetime.now().astimezone().tzname(),
    }


def make_run_id(config_sha256: str, repo: Path) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    short_sha = _git_output(repo, ["rev-parse", "--short", "HEAD"])
    if short_sha == "unavailable":
        short_sha = "nogit"
    return "figure1a-%s-%s-%s" % (timestamp, short_sha, config_sha256[:12])


class RunDirectory:
    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def create(cls, path: Path, identity: Mapping[str, Any]) -> "RunDirectory":
        path.mkdir(parents=True, exist_ok=False)
        instance = cls(path)
        atomic_write_json(path / "run_identity.json", dict(identity), exclusive=True)
        atomic_write_json(path / "run_state.json", {
            "sequence": 0, "status": "created", "protocol_version": const.PROTOCOL_VERSION,
        }, exclusive=True)
        atomic_write_text(path / "errors.log", "", exclusive=True)
        return instance

    @classmethod
    def resume(cls, path: Path) -> "RunDirectory":
        instance = cls(path.resolve())
        if instance.read_state()["status"] not in {"created", "coarse_running", "dense_running"}:
            raise RuntimeError("run is not resumable")
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
        current = (self.path / "errors.log").read_text(encoding="utf-8")
        atomic_write_text(self.path / "errors.log", current + message.rstrip() + "\n")
