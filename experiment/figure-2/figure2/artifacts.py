import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping


_SOURCE_TREE_EXCLUDED_ROOT_FILES = frozenset({"implementation_audited.json"})
_GENERATED_AUDIT_REPORT = re.compile(
    r"IMPLEMENTATION_(?:[A-Z0-9]+_)*(?:AUDIT|REAUDIT)_REPORT\.md"
)


def _validate(value: Any) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite JSON value")
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate(item)
        return
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical JSON keys must be strings")
        for item in value.values():
            _validate(item)
        return
    raise TypeError("unsupported JSON value")


def canonical_json_bytes(value: Any) -> bytes:
    _validate(value)
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _generated_audit_artifact(relative: Path) -> bool:
    if len(relative.parts) != 1:
        return False
    return relative.name in _SOURCE_TREE_EXCLUDED_ROOT_FILES \
        or _GENERATED_AUDIT_REPORT.fullmatch(relative.name) is not None


def source_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in {"build", "results", "implementation", "__pycache__", ".pytest_cache"}
               for part in relative.parts):
            continue
        if _generated_audit_artifact(relative):
            continue
        if path.suffix not in {
            ".py", ".cpp", ".hpp", ".h", ".go", ".md", ".json", ".mod", ".sum",
        } \
                and path.name != "CMakeLists.txt":
            continue
        files.append((relative.as_posix(), path))
    for relative, path in sorted(files):
        name = relative.encode()
        content = path.read_bytes()
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_json(path: Path, value: Any) -> None:
    atomic_write(path, canonical_json_bytes(value))


def atomic_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    atomic_write(path, b"".join(canonical_json_bytes(dict(row)) for row in rows))
