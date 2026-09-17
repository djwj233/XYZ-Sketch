import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from . import constants as const
from .artifacts import atomic_json, canonical_json_bytes, sha256_file, source_tree_sha256
from .config import candidate_budget, profile_manifest
from .correction import CorrectionRunner
from .engine import Figure2Engines
from .formal import FormalRunner, finalize_timing_run, validate_formal_gate
from .minisketch_extension import MiniSketchTimingExtension
from .plotting import render_figure2
from .refinement import RefinementRunner, build_refinement_plan
from .validation import equivalence_results, golden_results, smoke_results
from .v4 import V4Runner


def implementation_manifest(engines: Figure2Engines) -> Dict[str, Any]:
    commits = {}
    for algorithm, expected in const.SOURCE_COMMITS.items():
        directory = {
            "minisketch": const.REPO_DIR / "external" / "minisketch",
            "external_iblt": const.REPO_DIR / "external" / "IBLT_Cplusplus",
            "riblt": const.REPO_DIR / "external" / "riblt",
            "cpisync": const.REPO_DIR / "external" / "cpisync",
        }[algorithm]
        actual = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(directory), check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ).stdout.strip()
        if actual != expected:
            raise RuntimeError("source commit mismatch: %s" % algorithm)
        commits[algorithm] = actual
    core_diff = subprocess.run(
        ["git", "diff", "--", "XYZ-Sketch", "IBLT"], cwd=str(const.REPO_DIR), check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ).stdout
    if core_diff:
        raise RuntimeError("XYZ-Sketch or project IBLT core was modified")
    external_path = const.REPO_DIR / "external" / "IBLT_Cplusplus"
    patch = subprocess.run(
        ["git", "diff", "--", "iblt.h", "iblt.cpp"], cwd=str(external_path), check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ).stdout.encode()
    return {
        "status": "implemented",
        "protocol_version": const.PROTOCOL_VERSION,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "source_commits": commits,
        "core_algorithm_modified": False,
        "figure2_source_tree_sha256": source_tree_sha256(const.EXPERIMENT_DIR),
        "external_iblt_patch_scope": ["cell_count", "canonical_serialize", "canonical_deserialize"],
        "external_iblt_patch_sha256": __import__("hashlib").sha256(patch).hexdigest(),
        "executables": {
            name: {"path": str(path), "sha256": sha256_file(path)}
            for name, path in engines.executables.items()
        },
        "go": subprocess.run(
            ["/usr/local/go1.21/bin/go", "version"], check=True,
            stdout=subprocess.PIPE, text=True,
        ).stdout.strip(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m figure2")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("profiles", "budget", "golden", "smoke", "equivalence"):
        item = subparsers.add_parser(command)
        item.add_argument("--output", type=Path)
    audit = subparsers.add_parser("implementation-audit-inputs")
    audit.add_argument("--output-dir", type=Path, default=const.EXPERIMENT_DIR / "implementation")
    gate = subparsers.add_parser("formal-gate")
    gate.add_argument("--implementation-dir", type=Path, default=const.EXPERIMENT_DIR / "implementation")
    gate.add_argument("--implementation-audit", type=Path, required=True)
    gate.add_argument("--limits", type=Path, required=True)
    gate.add_argument("--frozen", type=Path, default=const.DEFAULT_FROZEN)
    gate.add_argument("--holdout", type=Path, default=const.DEFAULT_HOLDOUT)
    formal = subparsers.add_parser("formal")
    formal.add_argument("--results-root", type=Path, default=const.EXPERIMENT_DIR / "results")
    formal.add_argument("--implementation-dir", type=Path, default=const.EXPERIMENT_DIR / "implementation")
    formal.add_argument("--implementation-audit", type=Path, required=True)
    formal.add_argument("--limits", type=Path, required=True)
    formal.add_argument("--frozen", type=Path, default=const.DEFAULT_FROZEN)
    formal.add_argument("--holdout", type=Path, default=const.DEFAULT_HOLDOUT)
    formal.add_argument("--resume", type=Path)
    formal.add_argument("--stage", choices=("discovery", "confirmation", "timing", "all"), required=True)

    refine = subparsers.add_parser("refine-operating-points")
    refine.add_argument("--source-run", type=Path, required=True)
    refine.add_argument(
        "--results-root", type=Path,
        default=const.EXPERIMENT_DIR / "results" / "refinement",
    )
    refine.add_argument("--resume", type=Path)
    refine.add_argument("--dry-run", action="store_true")
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--run", type=Path, required=True)
    plot = subparsers.add_parser("plot")
    plot.add_argument("--run", type=Path, required=True)
    plot.add_argument("--presentation", choices=("extended", "main_additional_baseline"))
    correction = subparsers.add_parser("create-v3-correction")
    correction.add_argument("--parent-run", type=Path, required=True)
    correction.add_argument("--operating-source-run", type=Path, required=True)
    correction.add_argument("--implementation-dir", type=Path, required=True)
    correction.add_argument("--limits", type=Path, required=True)
    correction.add_argument("--results-root", type=Path, default=const.EXPERIMENT_DIR / "results" / "correction")
    correction_timing = subparsers.add_parser("run-v3-timing")
    correction_timing.add_argument("--run", type=Path, required=True)
    v4_create = subparsers.add_parser("create-v4-extension")
    v4_create.add_argument("--parent-run", type=Path, required=True)
    v4_create.add_argument(
        "--results-root", type=Path,
        default=const.EXPERIMENT_DIR / "results" / "v4",
    )
    v4_run = subparsers.add_parser("run-v4-extension")
    v4_run.add_argument("--run", type=Path, required=True)
    v4_run.add_argument(
        "--stage", choices=("discovery", "confirmation", "timing", "all"), required=True,
    )
    minisketch_extension = subparsers.add_parser("extend-minisketch-timing")
    minisketch_extension.add_argument("--run", type=Path, required=True)
    return parser


def _emit(value: Dict[str, Any], output: Optional[Path]) -> int:
    if output:
        atomic_json(output, value)
    else:
        sys.stdout.buffer.write(canonical_json_bytes(value))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    profiles = profile_manifest()
    if args.command == "profiles":
        return _emit(profiles, args.output)
    if args.command == "budget":
        return _emit(candidate_budget(), args.output)
    if args.command == "finalize":
        print(finalize_timing_run(args.run))
        return 0
    engines = Figure2Engines()
    if args.command == "golden":
        return _emit(golden_results(engines), args.output)
    if args.command == "smoke":
        return _emit(smoke_results(engines, profiles), args.output)
    if args.command == "equivalence":
        return _emit(equivalence_results(engines, profiles), args.output)
    if args.command == "implementation-audit-inputs":
        args.output_dir.mkdir(parents=True, exist_ok=True)
        artifacts = {
            "profile_manifest.json": profiles,
            "candidate_budget.json": candidate_budget(),
            "wire_golden_results.json": golden_results(engines),
            "smoke_results.json": smoke_results(engines, profiles),
            "equivalence_golden_results.json": equivalence_results(engines, profiles),
            "build_manifest.json": implementation_manifest(engines),
        }
        for name, value in artifacts.items():
            atomic_json(args.output_dir / name, value)
        summary = {
            "status": "implementation_ready_for_audit",
            "protocol_version": const.PROTOCOL_VERSION,
            "formal_trials_executed": False,
            "formal_trials_scope": const.PROTOCOL_VERSION,
            "superseded_run_artifacts_reused": False,
            "artifacts": {
                name: sha256_file(args.output_dir / name) for name in artifacts
            },
        }
        atomic_json(args.output_dir / "implementation_summary.json", summary)
        print(args.output_dir)
        return 0
    if args.command == "formal-gate":
        value = validate_formal_gate(
            args.implementation_dir.resolve(), args.implementation_audit.resolve(),
            args.limits.resolve(), args.frozen.resolve(), args.holdout.resolve(),
        )
        sys.stdout.buffer.write(canonical_json_bytes(value))
        return 0
    if args.command == "formal":
        runner = FormalRunner(
            results_root=args.results_root,
            implementation_dir=args.implementation_dir,
            implementation_audit=args.implementation_audit,
            limits_path=args.limits,
            frozen_path=args.frozen,
            holdout_path=args.holdout,
            resume=args.resume,
        )
        if args.stage == "discovery": result = runner.run_discovery()
        elif args.stage == "confirmation": result = runner.run_confirmation()
        elif args.stage == "timing": result = runner.run_timing()
        else: result = runner.run_all()
        print(result)
        return 0
    if args.command == "refine-operating-points":
        if args.dry_run:
            print(json.dumps(build_refinement_plan(args.source_run), sort_keys=True))
            return 0
        runner = RefinementRunner(
            source_run=args.source_run,
            results_root=args.results_root,
            resume=args.resume,
        )
        print(runner.run())
        return 0
    if args.command == "plot":
        print(json.dumps(render_figure2(args.run, args.presentation), sort_keys=True))
        return 0
    if args.command == "create-v3-correction":
        print(CorrectionRunner.create(
            parent_run=args.parent_run,
            operating_source_run=args.operating_source_run,
            implementation_dir=args.implementation_dir,
            limits_path=args.limits,
            results_root=args.results_root,
        ))
        return 0
    if args.command == "run-v3-timing":
        print(CorrectionRunner(args.run).run_timing())
        return 0
    if args.command == "create-v4-extension":
        print(V4Runner.create(args.parent_run, args.results_root))
        return 0
    if args.command == "run-v4-extension":
        runner = V4Runner(args.run)
        if args.stage == "discovery": result = runner.run_discovery()
        elif args.stage == "confirmation": result = runner.run_confirmation()
        elif args.stage == "timing": result = runner.run_timing()
        else: result = runner.run_all()
        print(result)
        return 0
    if args.command == "extend-minisketch-timing":
        print(MiniSketchTimingExtension(args.run).run_timing())
        return 0
    raise AssertionError("unreachable")
