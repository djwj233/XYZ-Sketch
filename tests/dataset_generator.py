#!/usr/bin/env python3
"""Shared dataset generation utilities for benchmark scripts."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DATASET_FORMAT = "compare-dataset-v1"
DEFAULT_VALUE_MODULUS = 998244353
DEFAULT_MIN_VALUE = 1


@dataclass(frozen=True)
class DatasetConfig:
    d: int
    ca: int
    cb: int
    seed: int
    value_modulus: int = DEFAULT_VALUE_MODULUS
    min_value: int = DEFAULT_MIN_VALUE
    overlap_policy: str = "replace_common_positions"
    shuffle_policy: str = "shuffle_both"
    duplicate_policy: str = "unique"


@dataclass(frozen=True)
class Dataset:
    alice: list[int]
    bob: list[int]
    metadata: dict[str, Any]


def choose_set_sizes(d: int, max_set_size: int, scale: int, minimum: int = 1000) -> tuple[int, int]:
    base = max(minimum, d * scale)
    base = min(base, max_set_size)
    if base <= d:
        base = d + 2
    ca = base
    cb = base - (d % 2)
    if cb <= 0:
        cb = ca
    return ca, cb


def trial_seed(base_seed: int, trial: int) -> int:
    return int(base_seed) + int(trial)


def dataset_id(config: DatasetConfig, trial: int | None = None) -> str:
    base = f"d{config.d}_ca{config.ca}_cb{config.cb}_seed{config.seed}"
    if trial is None:
        return base
    return f"{base}_trial{trial}"


def validate_config(config: DatasetConfig) -> None:
    if config.d <= 0:
        raise ValueError("d must be positive")
    if config.ca <= 0 or config.cb <= 0:
        raise ValueError("ca and cb must be positive")
    if config.value_modulus <= config.min_value:
        raise ValueError("value_modulus must be greater than min_value")
    if config.d < abs(config.ca - config.cb):
        raise ValueError("d must be at least abs(ca - cb)")
    if (config.d - abs(config.ca - config.cb)) % 2 != 0:
        raise ValueError("d and abs(ca - cb) must have the same parity")
    replacements = (config.d - abs(config.ca - config.cb)) // 2
    if replacements > min(config.ca, config.cb):
        raise ValueError("requested difference is too large for ca/cb")
    required_unique_values = max(config.ca, config.cb) + replacements
    available_values = config.value_modulus - config.min_value
    if required_unique_values > available_values:
        raise ValueError("value domain is too small for unique dataset generation")
    if config.overlap_policy != "replace_common_positions":
        raise ValueError(f"unsupported overlap_policy: {config.overlap_policy}")
    if config.shuffle_policy != "shuffle_both":
        raise ValueError(f"unsupported shuffle_policy: {config.shuffle_policy}")
    if config.duplicate_policy != "unique":
        raise ValueError(f"unsupported duplicate_policy: {config.duplicate_policy}")


def validate_dataset(dataset: Dataset) -> None:
    d = int(dataset.metadata["d"])
    ca = int(dataset.metadata["ca"])
    cb = int(dataset.metadata["cb"])
    if len(dataset.alice) != ca:
        raise ValueError("Alice set size does not match metadata")
    if len(dataset.bob) != cb:
        raise ValueError("Bob set size does not match metadata")
    if len(set(dataset.alice)) != len(dataset.alice):
        raise ValueError("Alice contains duplicate values")
    if len(set(dataset.bob)) != len(dataset.bob):
        raise ValueError("Bob contains duplicate values")
    difference = len(set(dataset.alice).symmetric_difference(set(dataset.bob)))
    if difference != d:
        raise ValueError(f"symmetric difference is {difference}, expected {d}")


def make_dataset(config: DatasetConfig, trial: int = 0) -> Dataset:
    validate_config(config)
    current_trial_seed = trial_seed(config.seed, trial)
    replacements = (config.d - abs(config.ca - config.cb)) // 2

    rng = random.Random(current_trial_seed)
    used: set[int] = set()

    def next_value() -> int:
        value = rng.randrange(config.min_value, config.value_modulus)
        while value in used:
            value = rng.randrange(config.min_value, config.value_modulus)
        used.add(value)
        return value

    base = [next_value() for _ in range(max(config.ca, config.cb))]
    alice = base[: config.ca]
    bob = base[: config.cb]

    positions = rng.sample(range(min(config.ca, config.cb)), replacements)
    for pos in positions:
        bob[pos] = next_value()

    rng.shuffle(alice)
    rng.shuffle(bob)
    metadata = {
        "ca": config.ca,
        "cb": config.cb,
        "d": config.d,
        "seed": config.seed,
        "trial": trial,
        "trial_seed": current_trial_seed,
    }
    dataset = Dataset(alice=alice, bob=bob, metadata=metadata)
    validate_dataset(dataset)
    return dataset


def write_dataset(path: Path, dataset: Dataset) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            f"# {DATASET_FORMAT} "
            + " ".join(f"{key}={value}" for key, value in sorted(dataset.metadata.items()))
            + "\n"
        )
        handle.write(f"A {len(dataset.alice)}\n")
        for value in dataset.alice:
            handle.write(f"{value}\n")
        handle.write(f"B {len(dataset.bob)}\n")
        for value in dataset.bob:
            handle.write(f"{value}\n")


def _parse_metadata(header: str) -> dict[str, Any]:
    if not header.startswith(f"# {DATASET_FORMAT}"):
        raise ValueError("unsupported dataset format")
    metadata: dict[str, Any] = {}
    prefix = f"# {DATASET_FORMAT}"
    payload = header[len(prefix):] if header.startswith(prefix) else header
    for item in payload.strip().split():
        key, _, value = item.partition("=")
        if not key or not _:
            raise ValueError(f"invalid metadata item: {item}")
        try:
            metadata[key] = int(value)
        except ValueError:
            metadata[key] = value
    return metadata


def load_dataset(path: Path) -> Dataset:
    with path.open("r", encoding="utf-8") as handle:
        header = handle.readline().rstrip("\n")
        metadata = _parse_metadata(header)
        alice: list[int] = []
        bob: list[int] = []
        current: list[int] | None = None
        expected = -1
        seen = 0
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) == 2 and parts[0] in {"A", "B"}:
                if current is not None and expected != seen:
                    raise ValueError("dataset section length mismatch")
                current = alice if parts[0] == "A" else bob
                expected = int(parts[1])
                seen = 0
                continue
            if current is None:
                raise ValueError("dataset value before section header")
            current.append(int(line))
            seen += 1
        if current is not None and expected != seen:
            raise ValueError("dataset section length mismatch")
    dataset = Dataset(alice=alice, bob=bob, metadata=metadata)
    validate_dataset(dataset)
    return dataset


def prepare_datasets(config: DatasetConfig, trials: int, output_dir: Path) -> list[Path]:
    if trials <= 0:
        raise ValueError("trials must be positive")
    dataset_paths: list[Path] = []
    workload_dir = output_dir / dataset_id(config)
    for trial in range(trials):
        path = workload_dir / f"trial{trial}.sets"
        write_dataset(path, make_dataset(config, trial=trial))
        dataset_paths.append(path)
    return dataset_paths


def write_manifest(path: Path, dataset_paths: list[Path]) -> None:
    rows = []
    for dataset_path in dataset_paths:
        dataset = load_dataset(dataset_path)
        rows.append(
            {
                "dataset_path": str(dataset_path),
                "dataset_id": dataset_path.parent.name,
                **dataset.metadata,
            }
        )
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"format": DATASET_FORMAT, "datasets": rows}, handle, indent=2, sort_keys=True)
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate shared Alice/Bob set-reconciliation datasets.")
    parser.add_argument("--d", type=int, required=True)
    parser.add_argument("--ca", type=int, default=None)
    parser.add_argument("--cb", type=int, default=None)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--seed", type=int, default=114514)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-set-size", type=int, default=100000)
    parser.add_argument("--set-size-scale", type=int, default=10)
    parser.add_argument("--value-modulus", type=int, default=DEFAULT_VALUE_MODULUS)
    parser.add_argument("--min-value", type=int, default=DEFAULT_MIN_VALUE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manifest", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ca = args.ca
    cb = args.cb
    if ca is None or cb is None:
        ca, cb = choose_set_sizes(args.d, max_set_size=args.max_set_size, scale=args.set_size_scale)
    config = DatasetConfig(
        d=args.d,
        ca=int(ca),
        cb=int(cb),
        seed=args.seed,
        value_modulus=args.value_modulus,
        min_value=args.min_value,
    )
    validate_config(config)

    planned = [args.output_dir / dataset_id(config) / f"trial{trial}.sets" for trial in range(args.trials)]
    if args.dry_run:
        for path in planned:
            print(path)
        return

    paths = prepare_datasets(config, args.trials, args.output_dir)
    if args.manifest:
        write_manifest(args.output_dir / "manifest.json", paths)
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
