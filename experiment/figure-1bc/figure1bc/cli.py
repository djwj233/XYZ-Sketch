"""Command-line entry points for build verification, calibration, and holdout."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .artifacts import atomic_write_json, canonical_json_bytes
from .calibration import CalibrationRunner
from .config import SmokeConfig, dry_run_budget
from .engine import CppEngine
from .evaluation import evaluate_point
from .figure3 import Figure3Runner
from .figure3_plotting import render_figure3
from .figure3_wide import Figure3WideRunner
from .figure3_wide_plotting import render_wide_figure3
from .holdout import HoldoutRunner
from .model import CalibrationCandidate
from .plotting import render_holdout
from .threshold import load_threshold


def _default_experiment_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_repo() -> Path:
    return _default_experiment_dir().parent.parent


def _default_engine() -> Path:
    return _default_experiment_dir() / "build" / "figure1bc_engine"


def _default_results() -> Path:
    return _default_experiment_dir() / "results"


def _smoke(engine_path: Path) -> int:
    config = SmokeConfig()
    config.validate()
    threshold = load_threshold()
    specs = (
        CalibrationCandidate(100, 650).placement(config.M, threshold),
        CalibrationCandidate(125, 650).placement(config.M, threshold),
        CalibrationCandidate(100, 150).placement(config.M, threshold),
    )
    arguments = {
        "run_id": "figure1bc-smoke",
        "stage": "smoke",
        "domain": config.domain,
        "d": config.d,
        "M": config.M,
        "specs": specs,
        "trials": config.trials,
        "threshold_sha256": threshold.sha256,
        "m_grid_phase": "smoke",
    }
    reference = evaluate_point(**arguments)
    accelerated = evaluate_point(**arguments, engine=CppEngine(engine_path))
    if reference != accelerated:
        raise RuntimeError("C++ engine differs from the independent Python reference")
    sys.stdout.buffer.write(
        canonical_json_bytes(
            {
                "status": "passed",
                "formal_data": False,
                "d": config.d,
                "M": config.M,
                "trials": config.trials,
                "candidate_count": len(specs),
                "distinct_trial_rows": len(reference.trial_rows),
                "classification": reference.classification,
            }
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m figure1bc")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dry = subparsers.add_parser("dry-run", help="write or print a no-trial budget manifest")
    dry.add_argument("--output", type=Path)

    smoke = subparsers.add_parser("smoke", help="compare C++ and Python on a tiny nonformal fixture")
    smoke.add_argument("--engine", type=Path, default=_default_engine())

    calibrate = subparsers.add_parser("calibrate", help="run the audited formal calibration")
    calibrate.add_argument("--repo", type=Path, default=_default_repo())
    calibrate.add_argument("--results-root", type=Path, default=_default_results())
    calibrate.add_argument("--engine", type=Path, default=_default_engine())
    calibrate.add_argument("--resume", type=Path)

    holdout = subparsers.add_parser("holdout", help="run the sealed Figure 1(b)(c) data experiment")
    holdout.add_argument("--repo", type=Path, default=_default_repo())
    holdout.add_argument("--results-root", type=Path, default=_default_results())
    holdout.add_argument("--engine", type=Path, default=_default_engine())
    holdout.add_argument("--frozen", type=Path, required=True)

    plot = subparsers.add_parser("plot", help="render completed holdout heatmaps")
    plot.add_argument("--holdout-run", type=Path, required=True)

    figure3 = subparsers.add_parser(
        "figure3-run", help="run the post-freeze 12-panel Appendix Figure 3 experiment"
    )
    figure3.add_argument("--repo", type=Path, default=_default_repo())
    figure3.add_argument("--results-root", type=Path, default=_default_results())
    figure3.add_argument("--engine", type=Path, default=_default_engine())
    figure3.add_argument("--frozen", type=Path, required=True)
    figure3.add_argument("--reference-holdout", type=Path, required=True)
    figure3.add_argument("--resume", type=Path)

    figure3_plot = subparsers.add_parser(
        "figure3-plot", help="render a completed 12-panel Appendix Figure 3 artifact"
    )
    figure3_plot.add_argument("--figure3-run", type=Path, required=True)

    figure3_wide = subparsers.add_parser(
        "figure3-wide-run", help="run one objective wide-axis Figure 3 exploration round"
    )
    figure3_wide.add_argument("--repo", type=Path, default=_default_repo())
    figure3_wide.add_argument("--results-root", type=Path, default=_default_results())
    figure3_wide.add_argument("--engine", type=Path, default=_default_engine())
    figure3_wide.add_argument("--frozen", type=Path, required=True)
    figure3_wide.add_argument("--reference-holdout", type=Path, required=True)
    figure3_wide.add_argument("--round", type=int, choices=(1, 2, 3, 4), required=True)
    figure3_wide.add_argument("--resume", type=Path)

    figure3_wide_plot = subparsers.add_parser(
        "figure3-wide-plot", help="render a completed wide-axis Figure 3 round"
    )
    figure3_wide_plot.add_argument("--figure3-run", type=Path, required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "dry-run":
        budget = dry_run_budget()
        if args.output:
            atomic_write_json(args.output, budget)
        else:
            sys.stdout.buffer.write(canonical_json_bytes(budget))
        return 0
    if args.command == "smoke":
        return _smoke(args.engine)
    if args.command == "calibrate":
        runner = CalibrationRunner(
            repo=args.repo,
            results_root=args.results_root,
            engine_executable=args.engine,
            resume=args.resume,
        )
        print(runner.run_formal())
        return 0
    if args.command == "holdout":
        runner = HoldoutRunner(
            repo=args.repo,
            results_root=args.results_root,
            frozen_parameters=args.frozen,
            engine_executable=args.engine,
        )
        print(runner.run_formal())
        return 0
    if args.command == "plot":
        manifest = render_holdout(args.holdout_run)
        print(json.dumps(manifest, sort_keys=True))
        return 0
    if args.command == "figure3-run":
        runner = Figure3Runner(
            repo=args.repo,
            results_root=args.results_root,
            frozen_parameters=args.frozen,
            reference_holdout=args.reference_holdout,
            engine_executable=args.engine,
            resume=args.resume,
        )
        print(runner.run_formal())
        return 0
    if args.command == "figure3-plot":
        manifest = render_figure3(args.figure3_run)
        print(json.dumps(manifest, sort_keys=True))
        return 0
    if args.command == "figure3-wide-run":
        runner = Figure3WideRunner(
            repo=args.repo,
            results_root=args.results_root,
            frozen_parameters=args.frozen,
            reference_holdout=args.reference_holdout,
            engine_executable=args.engine,
            expansion_round=args.round,
            resume=args.resume,
        )
        print(runner.run_formal())
        return 0
    if args.command == "figure3-wide-plot":
        manifest = render_wide_figure3(args.figure3_run)
        print(json.dumps(manifest, sort_keys=True))
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
