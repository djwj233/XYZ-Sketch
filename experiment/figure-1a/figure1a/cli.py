"""Figure 1(a) build validation and formal coarse-scan commands."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import constants as const
from .artifacts import atomic_write_json, canonical_json_bytes, sha256_file
from .config import PanelParameters, build_initial_manifest, load_frozen, load_thresholds, make_spec
from .dense import BOUNDARY_STRATEGIES, DenseRunner, build_dense_config
from .engine import CppEngine
from .plotting import (
    render_figure1a,
    render_figure1a_wilson95,
    render_figure1a_wilson95_clean,
)
from .runner import CoarseRunner, recover_failed_coarse, validate_formal_inputs


def _default_engine() -> Path:
    return const.EXPERIMENT_DIR / "build" / "figure1a_engine"


def _default_results() -> Path:
    return const.EXPERIMENT_DIR / "results"


def smoke(engine_path: Path) -> int:
    frozen, frozen_sha256 = load_frozen(const.DEFAULT_FROZEN_PATH)
    thresholds = load_thresholds()
    engine = CppEngine(engine_path)
    panels = []
    for k, ell in const.PANELS:
        parameters = PanelParameters.create(k, ell, thresholds, frozen)
        specs = [make_spec(parameters, mode, 160) for mode in const.MODES]
        evaluated = engine.evaluate(
            phase="smoke", k=k, ell=ell, trial_index=0, specs=specs,
            set_size=40, difference=20, workers=3,
        )
        results = {
            spec.mode: evaluated.results[spec.config_id]["failure_reason"]
            for spec in specs
        }
        if any(reason != "success" for reason in results.values()):
            raise RuntimeError("smoke decode failed for panel (%d,%d)" % (k, ell))
        panels.append({"k": k, "ell": ell, "modes": results})
    output = {
        "status": "passed",
        "formal_data": False,
        "protocol_version": const.PROTOCOL_VERSION,
        "workload": {"difference": 20, "set_size_A": 40, "set_size_B": 40},
        "frozen_parameters_sha256": frozen_sha256,
        "engine_self_test": json.loads(engine.self_test()),
        "panels": panels,
    }
    sys.stdout.buffer.write(canonical_json_bytes(output))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m figure1a")
    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke_parser = subparsers.add_parser("smoke", help="run nonformal real-core fixtures")
    smoke_parser.add_argument("--engine", type=Path, default=_default_engine())

    dry = subparsers.add_parser("dry-run", help="create the no-trial initial scan manifest")
    dry.add_argument("--frozen", type=Path, default=const.DEFAULT_FROZEN_PATH)
    dry.add_argument("--output", type=Path)

    gates = subparsers.add_parser("gates", help="validate formal-run prerequisites")
    gates.add_argument("--repo", type=Path, default=const.REPO_DIR)
    gates.add_argument("--frozen", type=Path, default=const.DEFAULT_FROZEN_PATH)
    gates.add_argument("--holdout", type=Path, default=const.DEFAULT_HOLDOUT_PATH)
    gates.add_argument("--engine", type=Path, default=_default_engine())

    coarse = subparsers.add_parser("coarse", help="run or resume the formal 20-trial coarse scan")
    coarse.add_argument("--repo", type=Path, default=const.REPO_DIR)
    coarse.add_argument("--results-root", type=Path, default=_default_results())
    coarse.add_argument("--frozen", type=Path, default=const.DEFAULT_FROZEN_PATH)
    coarse.add_argument("--holdout", type=Path, default=const.DEFAULT_HOLDOUT_PATH)
    coarse.add_argument("--engine", type=Path, default=_default_engine())
    coarse.add_argument("--resume", type=Path)

    recover = subparsers.add_parser(
        "recover-coarse", help="finalize the reviewed canonical-JSON failed run without trials"
    )
    recover.add_argument("--parent", type=Path, required=True)
    recover.add_argument("--frozen", type=Path, default=const.DEFAULT_FROZEN_PATH)

    dense_dry = subparsers.add_parser("dense-dry-run", help="print the no-trial dense manifest")
    dense_dry.add_argument("--coarse-artifact", type=Path, required=True)
    dense_dry.add_argument("--frozen", type=Path, default=const.DEFAULT_FROZEN_PATH)
    dense_dry.add_argument("--engine", type=Path, default=_default_engine())
    dense_dry.add_argument("--boundary-strategy", choices=BOUNDARY_STRATEGIES, required=True)

    dense = subparsers.add_parser("dense", help="run or resume the formal 100-trial dense scan")
    dense.add_argument("--repo", type=Path, default=const.REPO_DIR)
    dense.add_argument("--results-root", type=Path, default=_default_results())
    dense.add_argument("--frozen", type=Path, default=const.DEFAULT_FROZEN_PATH)
    dense.add_argument("--holdout", type=Path, default=const.DEFAULT_HOLDOUT_PATH)
    dense.add_argument("--coarse-artifact", type=Path, required=True)
    dense.add_argument("--engine", type=Path, default=_default_engine())
    dense.add_argument("--boundary-strategy", choices=BOUNDARY_STRATEGIES, required=True)
    dense.add_argument("--import-dense-run", type=Path)
    dense.add_argument("--resume", type=Path)

    complete = subparsers.add_parser(
        "complete-platforms", help="extend only dense curve edges lacking 0/1 platforms"
    )
    complete.add_argument("--dense-run", type=Path, required=True)
    complete.add_argument("--repo", type=Path, default=const.REPO_DIR)
    complete.add_argument("--results-root", type=Path, default=_default_results())
    complete.add_argument("--frozen", type=Path, default=const.DEFAULT_FROZEN_PATH)
    complete.add_argument("--holdout", type=Path, default=const.DEFAULT_HOLDOUT_PATH)
    complete.add_argument("--engine", type=Path, default=_default_engine())
    complete.add_argument("--resume", type=Path)

    plot = subparsers.add_parser("plot", help="render a completed dense Figure 1(a) run")
    plot.add_argument("--dense-run", type=Path, required=True)

    plot_wilson95 = subparsers.add_parser(
        "plot-wilson95",
        help="render an additional Figure 1(a) with light Wilson 95%% CI bands",
    )
    plot_wilson95.add_argument("--dense-run", type=Path, required=True)

    plot_wilson95_clean = subparsers.add_parser(
        "plot-wilson95-clean",
        help="render a compact grid-free Figure 1(a) with light Wilson 95%% CI bands",
    )
    plot_wilson95_clean.add_argument("--dense-run", type=Path, required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "smoke":
        return smoke(args.engine)
    if args.command == "dry-run":
        frozen, frozen_sha256 = load_frozen(args.frozen)
        manifest = build_initial_manifest(frozen, frozen_sha256)
        if args.output:
            atomic_write_json(args.output, manifest)
        else:
            sys.stdout.buffer.write(canonical_json_bytes(manifest))
        return 0
    if args.command == "gates":
        result = validate_formal_inputs(
            args.repo.resolve(), args.frozen.resolve(), args.holdout.resolve(), CppEngine(args.engine)
        )
        sys.stdout.buffer.write(canonical_json_bytes(result))
        return 0
    if args.command == "coarse":
        runner = CoarseRunner(
            repo=args.repo,
            results_root=args.results_root,
            frozen_path=args.frozen,
            holdout_path=args.holdout,
            engine_path=args.engine,
            resume=args.resume,
        )
        print(runner.run_formal())
        return 0
    if args.command == "recover-coarse":
        print(recover_failed_coarse(args.parent, args.frozen))
        return 0
    if args.command == "dense-dry-run":
        frozen, frozen_sha256 = load_frozen(args.frozen)
        config = build_dense_config(
            args.coarse_artifact.resolve(), frozen, frozen_sha256,
            sha256_file(args.engine.resolve()),
            args.boundary_strategy,
        )
        sys.stdout.buffer.write(canonical_json_bytes(config))
        return 0
    if args.command == "dense":
        runner = DenseRunner(
            repo=args.repo,
            results_root=args.results_root,
            frozen_path=args.frozen,
            holdout_path=args.holdout,
            coarse_artifact=args.coarse_artifact,
            engine_path=args.engine,
            boundary_strategy=args.boundary_strategy,
            import_dense_run=args.import_dense_run,
            resume=args.resume,
        )
        print(runner.run_formal())
        return 0
    if args.command == "complete-platforms":
        source_config = json.loads((args.dense_run.resolve() / "run_config.json").read_text())
        runner = DenseRunner(
            repo=args.repo,
            results_root=args.results_root,
            frozen_path=args.frozen,
            holdout_path=args.holdout,
            coarse_artifact=Path(source_config["coarse_artifact_path"]),
            engine_path=args.engine,
            boundary_strategy="platform_completion",
            import_dense_run=args.dense_run,
            resume=args.resume,
        )
        print(runner.run_formal())
        return 0
    if args.command == "plot":
        print(json.dumps(render_figure1a(args.dense_run), sort_keys=True))
        return 0
    if args.command == "plot-wilson95":
        print(json.dumps(render_figure1a_wilson95(args.dense_run), sort_keys=True))
        return 0
    if args.command == "plot-wilson95-clean":
        print(json.dumps(render_figure1a_wilson95_clean(args.dense_run), sort_keys=True))
        return 0
    raise AssertionError("unreachable")
