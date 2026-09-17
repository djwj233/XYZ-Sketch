import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from figure2.artifacts import sha256_file, source_tree_sha256
from figure2.engine import EngineResult
from figure2.formal import (
    Checkpoints,
    FormalRunner,
    next_timing_trial,
    timing_attempt_record,
    timing_attempt_records,
    validate_audited_executables,
    finalize_timing_run,
    validate_formal_gate,
    validate_machine_affinity,
    validate_worker_policy,
    worker_batches,
)


def _engine_result(
    *, trial: int = 0, success: bool = True, failure_reason: str = "success"
) -> EngineResult:
    return EngineResult(
        algorithm="xyz",
        success=success,
        failure_reason=failure_reason,
        logical_state_bits=64,
        state_bits=64,
        control_bits=192,
        total_payload_bits=256,
        update_alice_cpu=float(trial + 1),
        update_bob_cpu=float(trial + 1),
        sender_cpu=float(trial + 1),
        transfer_cpu=0.0,
        receiver_cpu=0.0,
        alice_output_sha256="a",
        bob_output_sha256="b",
        residual_sha256="r",
        required_symbols=-1,
    )


def _timing_row(repetition: int, failure_reason: str = "success"):
    success = failure_reason == "success"
    row = {
        "algorithm": "xyz",
        "d": 100,
        "trial_index": 0,
        "repetition": repetition,
        "success": success,
        "failure_reason": failure_reason,
    }
    if failure_reason != "timeout":
        value = float(repetition + 1)
        row.update({"update_alice_cpu": value, "update_bob_cpu": value, "decode_cpu": value})
    return row


def _bare_runner(root: Path) -> FormalRunner:
    runner = FormalRunner.__new__(FormalRunner)
    runner.path = root
    runner.checkpoints = Checkpoints(root)
    runner.profiles = {"profiles": {"xyz": {"profile_hash": "test-profile"}}}
    runner.engines = type("FakeEngines", (), {"cpu_affinity": 0})()
    (root / "run_state.json").write_text('{"sequence":0,"status":"confirmation_complete"}\n')
    (root / "operating_points_discovery.json").write_text(json.dumps({
        "operating_points": [{
            "algorithm": "xyz", "d": 100, "status": "selected",
            "resource": 40, "candidate_id": "test-candidate",
        }]
    }))
    (root / "confirmation_summary.json").write_text(json.dumps({
        "points": [{"algorithm": "xyz", "d": 100, "status": "confirmed"}]
    }))
    runner._arguments = lambda algorithm, d, trial, domain, resource: {"trial": trial}
    runner._dataset = lambda engine, path, domain, d, trial, full: (
        {"trial": trial}, {"identity": trial, "alice_order": trial + 1, "bob_order": trial + 2}
    )
    runner.checkpoints.save(runner._result_row(
        stage="sealed_confirmation", domain="sealed_confirmation",
        algorithm="xyz", d=100, trial=0, candidate_id="test-candidate",
        resource=40, dataset={"trial": 0},
        seeds={"identity": 0, "alice_order": 1, "bob_order": 2},
        result=_engine_result(), cpu_affinity=0,
    ))
    return runner


class FormalParallelismTests(unittest.TestCase):
    def test_source_tree_hash_excludes_only_root_audit_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("protocol-v1\n")
            (root / "IMPLEMENTATION_AUDIT_REQUEST.md").write_text("request-v1\n")
            original = source_tree_sha256(root)

            (root / "IMPLEMENTATION_GATE_REAUDIT_REPORT.md").write_text("generated\n")
            (root / "implementation_audited.json").write_text('{"status":"passed"}\n')
            self.assertEqual(original, source_tree_sha256(root))

            (root / "IMPLEMENTATION_AUDIT_REQUEST.md").write_text("request-v2\n")
            self.assertNotEqual(original, source_tree_sha256(root))

            nested = root / "protocol"
            nested.mkdir()
            before_nested_report = source_tree_sha256(root)
            (nested / "IMPLEMENTATION_REAUDIT_REPORT.md").write_text("not generated here\n")
            self.assertNotEqual(before_nested_report, source_tree_sha256(root))

    def test_formal_gate_rejects_covered_source_tree_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            implementation = root / "implementation"
            holdout = root / "holdout"
            source.mkdir()
            implementation.mkdir()
            holdout.mkdir()
            (source / "README.md").write_text("audited-v1\n")
            go_source = source / "go" / "figure2_riblt_engine" / "main.go"
            go_source.parent.mkdir(parents=True)
            go_source.write_text("package main\n\nfunc main() {}\n")

            build_manifest = {
                "figure2_source_tree_sha256": source_tree_sha256(source),
                "executables": {},
            }
            build_path = implementation / "build_manifest.json"
            build_path.write_text(json.dumps(build_manifest))
            summary = {
                "status": "implementation_ready_for_audit",
                "formal_trials_executed": False,
                "artifacts": {"build_manifest.json": sha256_file(build_path)},
            }
            summary_path = implementation / "implementation_summary.json"
            summary_path.write_text(json.dumps(summary))
            audit_path = root / "implementation_audited.json"
            audit_path.write_text(json.dumps({
                "status": "implementation_audited",
                "implementation_summary_sha256": sha256_file(summary_path),
            }))
            limits_path = root / "limits.json"
            limits_path.write_text(json.dumps({
                "status": "approved",
                "worker_policy": {
                    "resource_discovery": {
                        "workers": 8, "physical_cpu_affinity": list(range(8)),
                    },
                    "sealed_confirmation": {
                        "workers": 8, "physical_cpu_affinity": list(range(8)),
                    },
                    "timing": {"workers": 1, "physical_cpu_affinity": [0]},
                },
                "memory_limit_gib": 1,
                "timeout_seconds": {
                    algorithm: 1 for algorithm in (
                        "xyz", "minisketch", "external_iblt", "project_iblt",
                        "riblt", "cpisync",
                    )
                },
            }))
            frozen_path = root / "frozen.json"
            frozen_path.write_text("{}\n")
            (holdout / "holdout_summary.json").write_text(json.dumps({
                "status": "complete",
                "downstream_experiments_unlocked": True,
                "frozen_parameters_sha256": "frozen-sha",
            }))

            with mock.patch("figure2.formal.const.EXPERIMENT_DIR", source), \
                    mock.patch("figure2.formal.validate_audited_executables", return_value={}), \
                    mock.patch("figure2.formal.validate_machine_affinity"), \
                    mock.patch("figure2.formal.load_frozen", return_value=({}, "frozen-sha")):
                gate = validate_formal_gate(
                    implementation, audit_path, limits_path, frozen_path, holdout,
                )
                self.assertEqual(build_manifest["figure2_source_tree_sha256"],
                                 gate["figure2_source_tree_sha256"])
                go_source.write_text("package main\n\nfunc main() { println(1) }\n")
                with self.assertRaisesRegex(ValueError, "source-tree hash differs"):
                    validate_formal_gate(
                        implementation, audit_path, limits_path, frozen_path, holdout,
                    )

    def test_worker_batches_are_complete_and_disjoint(self):
        batches = worker_batches(tuple(range(100)), tuple(range(8)))
        self.assertEqual(tuple(range(8)), tuple(cpu for cpu, _items in batches))
        flattened = [item for _cpu, items in batches for item in items]
        self.assertEqual(list(range(100)), sorted(flattened))
        self.assertEqual(100, len(set(flattened)))

    def test_timing_must_be_serial(self):
        policy = {
            "resource_discovery": {"workers": 8, "physical_cpu_affinity": list(range(8))},
            "sealed_confirmation": {"workers": 8, "physical_cpu_affinity": list(range(8))},
            "timing": {"workers": 1, "physical_cpu_affinity": [0]},
        }
        self.assertEqual(1, validate_worker_policy({"worker_policy": policy})["timing"]["workers"])
        policy["timing"] = {"workers": 2, "physical_cpu_affinity": [0, 1]}
        with self.assertRaisesRegex(ValueError, "exactly one worker"):
            validate_worker_policy({"worker_policy": policy})

    def test_probability_workers_and_cpu_lists_are_frozen(self):
        policy = {
            "resource_discovery": {"workers": 4, "physical_cpu_affinity": list(range(4))},
            "sealed_confirmation": {"workers": 8, "physical_cpu_affinity": list(range(8))},
            "timing": {"workers": 1, "physical_cpu_affinity": [0]},
        }
        with self.assertRaisesRegex(ValueError, "frozen CPU list"):
            validate_worker_policy({"worker_policy": policy})

    def test_formal_gate_rejects_executable_substitution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executables = {}
            manifest = {"executables": {}}
            for name in ("dataset", "xyz", "minisketch"):
                path = root / name
                path.write_bytes((name + "-v1").encode("ascii"))
                executables[name] = path
                manifest["executables"][name] = {
                    "path": str(path.resolve()),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            self.assertEqual(3, len(validate_audited_executables(manifest, executables)))
            executables["xyz"].write_bytes(b"substituted")
            with self.assertRaisesRegex(ValueError, "hash differs: xyz"):
                validate_audited_executables(manifest, executables)

    def test_candidate_payload_uses_successful_rows_and_checks_consistency(self):
        failed = {"success": False, "failure_reason": "decode_failed"}
        successful = {
            "success": True, "logical_state_bits": 60, "state_bits": 64,
            "control_bits": 320, "total_payload_bits": 384,
        }
        rows = [failed] + [dict(successful) for _ in range(90)] + [failed] * 9
        self.assertEqual(384, FormalRunner._candidate_payload_bits(rows))
        rows[2]["total_payload_bits"] = 392
        with self.assertRaisesRegex(RuntimeError, "differs"):
            FormalRunner._candidate_payload_bits(rows)

    def test_mean_payload_accounting_accepts_variable_wire_sizes(self):
        rows = [
            {
                "success": True, "failure_reason": "success",
                "logical_state_bits": 9024, "state_bits": 9024,
                "control_bits": 584, "total_payload_bits": 9608,
            }
            for _ in range(3)
        ] + [
            {
                "success": True, "failure_reason": "success",
                "logical_state_bits": 9032, "state_bits": 9032,
                "control_bits": 584, "total_payload_bits": 9616,
            }
            for _ in range(97)
        ] + [{"success": False, "failure_reason": "decode_failed"}]
        accounting = FormalRunner._mean_payload_accounting(rows)
        self.assertEqual(9031.76, accounting["state_bits"])
        self.assertEqual(584, accounting["control_bits"])
        self.assertEqual(9615.76, accounting["total_payload_bits"])

        rows[0]["total_payload_bits"] = 9616
        with self.assertRaisesRegex(RuntimeError, "accounting is invalid"):
            FormalRunner._mean_payload_accounting(rows)

    def test_machine_affinity_uses_distinct_physical_cores(self):
        validate_machine_affinity({
            "resource_discovery": {"physical_cpu_affinity": list(range(8))},
            "sealed_confirmation": {"physical_cpu_affinity": list(range(8))},
            "timing": {"physical_cpu_affinity": [0]},
        })
        with self.assertRaisesRegex(ValueError, "sibling threads"):
            validate_machine_affinity({
                "resource_discovery": {"physical_cpu_affinity": [0, 18]},
            })

    def test_confirmation_resource_failure_overrides_ninety_nine_successes(self):
        successful = {"success": True, "failure_reason": "success"}
        for failure_reason in ("timeout", "oom"):
            rows = [dict(successful) for _ in range(99)] + [{
                "success": False, "failure_reason": failure_reason,
            }]
            point = FormalRunner._confirmation_point_summary(rows, "xyz", 100)
            self.assertEqual(failure_reason, point["status"])
            self.assertIsNone(point["success_rate"])
            self.assertIsNone(point["ci_low"])
            self.assertIsNone(point["ci_high"])

    def test_process_error_never_enters_probability_rate_or_confirmation(self):
        rows = [
            {"success": True, "failure_reason": "success"} for _ in range(99)
        ] + [{"success": False, "failure_reason": "process_error"}]
        with self.assertRaisesRegex(RuntimeError, "non-statistical failure"):
            FormalRunner._rate(rows)
        with self.assertRaisesRegex(RuntimeError, "invalidates"):
            FormalRunner._confirmation_point_summary(rows, "xyz", 100)

    def test_process_error_checkpoint_invalidates_formal_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = _bare_runner(root)
            row = {
                "algorithm": "xyz", "d": 100, "trial_index": 7,
                "candidate_id": "candidate", "failure_reason": "process_error",
            }
            with self.assertRaisesRegex(RuntimeError, "process_error"):
                runner._raise_on_process_error([row], "resource_discovery")
            state = json.loads((root / "run_state.json").read_text())
            self.assertEqual("failed", state["status"])
            self.assertEqual("process_error", state["failure_reason"])
            self.assertIn("resource_discovery process_error", (root / "errors.log").read_text())

    def test_confirmation_worker_stops_before_next_trial_after_timeout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = _bare_runner(root)
            (root / "run_state.json").write_text(
                '{"sequence":0,"status":"discovery_complete"}\n'
            )
            calls = []

            def safe_engine(_engine, _algorithm, _path, arguments):
                calls.append(arguments["trial"])
                return None, "timeout"

            runner._safe_engine = safe_engine
            runner._parallel_batches = lambda stage, items, function: function(
                runner.engines, tuple(items)
            )
            with mock.patch("figure2.formal.const.DIFFERENCES", (100,)), \
                    mock.patch("figure2.formal.const.ALGORITHMS", ("xyz",)), \
                    mock.patch("figure2.formal.const.CONFIRMATION_TRIALS", 4):
                runner.run_confirmation()
            self.assertEqual([1], calls)
            point = json.loads((root / "confirmation_summary.json").read_text())["points"][0]
            self.assertEqual("timeout", point["status"])
            self.assertEqual(2, point["trials"])

    def test_confirmation_inherits_discovery_resource_limit_without_engine_call(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = _bare_runner(root)
            runner.checkpoints.path(
                "sealed_confirmation", "xyz", 100, "test-candidate", 0
            ).unlink()
            (root / "run_state.json").write_text(
                '{"sequence":0,"status":"discovery_complete"}\n'
            )
            (root / "operating_points_discovery.json").write_text(json.dumps({
                "operating_points": [{
                    "algorithm": "xyz", "d": 100, "status": "resource_limit",
                    "failure_reason": "timeout",
                }]
            }))

            def must_not_run(*_args, **_kwargs):
                raise AssertionError("discovery resource-limited point entered confirmation")

            runner._safe_engine = must_not_run
            runner._parallel_batches = lambda stage, items, function: function(
                runner.engines, tuple(items)
            )
            with mock.patch("figure2.formal.const.DIFFERENCES", (100,)), \
                    mock.patch("figure2.formal.const.ALGORITHMS", ("xyz",)), \
                    mock.patch("figure2.formal.const.CONFIRMATION_TRIALS", 4):
                runner.run_confirmation()
            point = json.loads((root / "confirmation_summary.json").read_text())["points"][0]
            self.assertEqual("timeout", point["status"])
            self.assertEqual(0, point["trials"])


class FormalTimingTests(unittest.TestCase):
    def test_only_three_successful_repetitions_form_an_arithmetic_mean(self):
        rows = [_timing_row(repetition) for repetition in range(3)]
        record = timing_attempt_record(rows)
        self.assertEqual("successful", record["status"])
        self.assertEqual(200.0, record["update_ns_per_input"])
        self.assertEqual(20_000_000.0, record["decode_ns_per_difference"])
        for failure_reason in ("wrong_output", "decode_failed", "timeout"):
            failed = list(rows)
            failed[2] = _timing_row(2, failure_reason)
            record = timing_attempt_record(failed)
            self.assertEqual("failed", record["status"])
            self.assertNotIn("update_ns_per_input", record)
            self.assertNotIn("decode_ns_per_difference", record)
        self.assertEqual("incomplete", timing_attempt_record(rows[:2])["status"])

    def test_process_error_attempt_is_persistently_fatal_across_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = _bare_runner(root)
            (root / "run_state.json").write_text(
                '{"sequence":1,"status":"timing_running"}\n'
            )
            dataset = {"trial": 0}
            seeds = {"identity": 0, "alice_order": 1, "bob_order": 2}
            for repetition in range(3):
                identity = "test-candidate-rep%d" % repetition
                if repetition == 0:
                    result, terminal = _engine_result(), None
                elif repetition == 1:
                    result, terminal = None, "process_error"
                else:
                    result, terminal = None, "not_run_after_process_error"
                runner.checkpoints.save(runner._result_row(
                    stage="timing", domain="timing", algorithm="xyz", d=100,
                    trial=0, candidate_id=identity, resource=40, dataset=dataset,
                    seeds=seeds, result=result, terminal_status=terminal,
                    repetition=repetition, cpu_affinity=0,
                ))
            rows = runner.checkpoints.rows("timing")
            attempt = timing_attempt_record(rows)
            self.assertEqual("fatal", attempt["status"])
            with self.assertRaisesRegex(RuntimeError, "fatal timing attempt"):
                next_timing_trial([{**attempt, "trial_index": 0}])

            def must_not_run(*_args, **_kwargs):
                raise AssertionError("fatal timing resume executed a later dataset")

            runner._dataset = must_not_run
            runner._safe_engine = must_not_run
            with self.assertRaisesRegex(RuntimeError, "timing process_error"):
                runner.run_timing()
            state = json.loads((root / "run_state.json").read_text())
            self.assertEqual("failed", state["status"])
            self.assertEqual("process_error", state["failure_reason"])
            self.assertEqual("timing", state["failed_stage"])
            self.assertIn("timing process_error", (root / "errors.log").read_text())
            self.assertEqual(3, len(runner.checkpoints.rows("timing")))
            with self.assertRaisesRegex(RuntimeError, "timing state is not active"):
                runner.run_timing()

    def test_live_timing_process_error_persists_failed_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = _bare_runner(root)
            calls = []

            def safe_engine(_engine, _algorithm, _path, arguments):
                calls.append(arguments["trial"])
                if len(calls) == 1:
                    return _engine_result(), None
                return None, "process_error"

            runner._safe_engine = safe_engine
            with mock.patch("figure2.formal.const.DIFFERENCES", (100,)), \
                    mock.patch("figure2.formal.const.ALGORITHMS", ("xyz",)):
                with self.assertRaisesRegex(RuntimeError, "timing process_error"):
                    runner.run_timing()
            self.assertEqual([0, 0], calls)
            state = json.loads((root / "run_state.json").read_text())
            self.assertEqual("failed", state["status"])
            self.assertEqual("timing", state["failed_stage"])
            rows = runner.checkpoints.rows("timing")
            self.assertEqual(3, len(rows))
            self.assertEqual("fatal", timing_attempt_record(rows)["status"])

    def test_retries_until_five_successful_datasets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = _bare_runner(root)
            calls = {}

            def safe_engine(_engine, _algorithm, _path, arguments):
                trial = arguments["trial"]
                call = calls.get(trial, 0)
                calls[trial] = call + 1
                if trial == 0 and call == 2:
                    return _engine_result(
                        trial=trial, success=False, failure_reason="wrong_output"
                    ), None
                return _engine_result(trial=trial), None

            runner._safe_engine = safe_engine
            with mock.patch("figure2.formal.const.DIFFERENCES", (100,)), \
                    mock.patch("figure2.formal.const.ALGORITHMS", ("xyz",)):
                runner.run_timing()

            summary = json.loads((root / "timing_summary.json").read_text())["points"][0]
            self.assertEqual(6, summary["attempted_datasets"])
            self.assertEqual(1, summary["failed_datasets"])
            self.assertEqual(5, summary["successful_datasets"])
            self.assertEqual("complete", summary["timing_status"])
            attempts = [
                row for row in timing_attempt_records(runner.checkpoints.rows("timing"))
                if row["algorithm"] == "xyz" and row["d"] == 100
            ]
            self.assertEqual(6, len(attempts))
            self.assertEqual(5, sum(row["status"] == "successful" for row in attempts))

    def test_resume_completes_three_repetitions_without_warmup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = _bare_runner(root)
            dataset = {"trial": 0}
            seeds = {"identity": 0, "alice_order": 1, "bob_order": 2}
            runner.checkpoints.save(runner._result_row(
                stage="timing", domain="timing", algorithm="xyz", d=100, trial=0,
                candidate_id="test-candidate-rep0", resource=40, dataset=dataset,
                seeds=seeds, result=_engine_result(), repetition=0, cpu_affinity=0,
            ))
            calls = []

            def safe_engine(_engine, _algorithm, _path, arguments):
                calls.append(arguments["trial"])
                return _engine_result(), None

            runner._safe_engine = safe_engine
            with mock.patch("figure2.formal.const.DIFFERENCES", (100,)), \
                    mock.patch("figure2.formal.const.ALGORITHMS", ("xyz",)), \
                    mock.patch("figure2.formal.const.TIMING_DATASETS", 1):
                runner.run_timing()
            self.assertEqual([0, 0], calls)
            self.assertFalse((root / "checkpoints" / "timing_warmups").exists())

    def test_finalize_uses_mean_payload_without_running_trials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "run_state.json").write_text(
                '{"sequence":5,"status":"timing_running"}\n'
            )
            (root / "run_config.json").write_text(json.dumps({
                "protocol_version": "figure2-v4",
                "timing_successful_datasets_target": 5,
                "timing_repetitions": 3,
                "timing_warmups": 0,
            }))
            (root / "confirmation_summary.json").write_text(json.dumps({
                "points": [{
                    "algorithm": "cpisync", "d": 300, "status": "confirmed",
                    "trials": 2, "successes": 2, "success_rate": 1.0,
                    "ci_low": 0.0, "ci_high": 1.0,
                }]
            }))
            timing_point = {
                "algorithm": "cpisync", "d": 300, "timing_status": "complete",
                "attempted_datasets": 5, "failed_datasets": 0,
                "successful_datasets": 5, "successful_datasets_target": 5,
                "estimand": "conditional_mean_given_decode_success",
                "update_ns_per_input_conditional_mean": 1.0,
                "update_ci_low": 1.0, "update_ci_high": 1.0,
                "decode_ns_per_difference_conditional_mean": 1.0,
                "decode_ci_low": 1.0, "decode_ci_high": 1.0,
            }
            (root / "timing_summary.json").write_text(json.dumps({
                "points": [timing_point]
            }))
            checkpoints = Checkpoints(root)
            for trial, state in enumerate((9024, 9032)):
                checkpoints.save({
                    "stage": "sealed_confirmation", "algorithm": "cpisync", "d": 300,
                    "candidate_id": "mbar-d", "trial_index": trial,
                    "success": True, "failure_reason": "success",
                    "logical_state_bits": state, "state_bits": state,
                    "control_bits": 584, "total_payload_bits": state + 584,
                })

            self.assertEqual(root.resolve(), finalize_timing_run(root))
            aggregate = json.loads((root / "aggregate.json").read_text())
            self.assertEqual(
                "arithmetic_mean_over_successful_confirmation_trials",
                aggregate["payload_aggregation"],
            )
            self.assertEqual(9612, aggregate["points"][0]["total_payload_bits"])
            self.assertEqual("complete", json.loads(
                (root / "run_state.json").read_text()
            )["status"])
            manifest = json.loads((root / "finalization_manifest.json").read_text())
            self.assertFalse(manifest["engine_trials_executed"])

    def test_timeout_stops_resource_instead_of_entering_statistical_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = _bare_runner(root)
            calls = []

            def safe_engine(_engine, _algorithm, _path, arguments):
                calls.append(arguments["trial"])
                if len(calls) == 1:
                    return _engine_result(), None
                return None, "timeout"

            runner._safe_engine = safe_engine
            with mock.patch("figure2.formal.const.DIFFERENCES", (100,)), \
                    mock.patch("figure2.formal.const.ALGORITHMS", ("xyz",)):
                runner.run_timing()
            summary = json.loads((root / "timing_summary.json").read_text())["points"][0]
            self.assertEqual("timeout", summary["timing_status"])
            self.assertEqual(1, summary["attempted_datasets"])
            self.assertEqual(1, summary["failed_datasets"])
            self.assertEqual(0, summary["successful_datasets"])
            self.assertEqual([0, 0], calls)

    def test_prior_successes_are_not_plottable_after_resource_limit(self):
        for resource_failure in ("timeout", "oom"):
            with self.subTest(resource_failure=resource_failure), \
                    tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                runner = _bare_runner(root)
                calls = {}

                def safe_engine(_engine, _algorithm, _path, arguments):
                    trial = arguments["trial"]
                    call = calls.get(trial, 0)
                    calls[trial] = call + 1
                    if trial == 2 and call == 1:
                        return None, resource_failure
                    return _engine_result(trial=trial), None

                runner._safe_engine = safe_engine
                with mock.patch("figure2.formal.const.DIFFERENCES", (100,)), \
                        mock.patch("figure2.formal.const.ALGORITHMS", ("xyz",)):
                    runner.run_timing()
                summary = json.loads((root / "timing_summary.json").read_text())["points"][0]
                self.assertEqual(resource_failure, summary["timing_status"])
                self.assertEqual(3, summary["attempted_datasets"])
                self.assertEqual(1, summary["failed_datasets"])
                self.assertEqual(2, summary["successful_datasets"])
                for field in (
                    "update_ns_per_input_conditional_mean", "update_ci_low", "update_ci_high",
                    "decode_ns_per_difference_conditional_mean", "decode_ci_low", "decode_ci_high",
                ):
                    self.assertIsNone(summary[field])

    def test_resume_completes_partial_timeout_attempt_without_running_engine(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = _bare_runner(root)
            runner.checkpoints.save(runner._result_row(
                stage="timing", domain="timing", algorithm="xyz", d=100, trial=0,
                candidate_id="test-candidate-rep0", resource=40, dataset={"trial": 0},
                seeds={"identity": 0, "alice_order": 1, "bob_order": 2}, result=None,
                terminal_status="timeout", repetition=0, cpu_affinity=0,
            ))

            def must_not_run(*_args, **_kwargs):
                raise AssertionError("resource-limited resume ran the engine")

            runner._safe_engine = must_not_run
            with mock.patch("figure2.formal.const.DIFFERENCES", (100,)), \
                    mock.patch("figure2.formal.const.ALGORITHMS", ("xyz",)):
                runner.run_timing()
            rows = runner.checkpoints.rows("timing")
            self.assertEqual(3, len(rows))
            self.assertEqual("failed", timing_attempt_record(rows)["status"])
            summary = json.loads((root / "timing_summary.json").read_text())["points"][0]
            self.assertEqual("timeout", summary["timing_status"])
            self.assertEqual(1, summary["attempted_datasets"])

    def test_confirmation_failed_payload_is_null_in_aggregate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = _bare_runner(root)
            (root / "confirmation_summary.json").write_text(json.dumps({
                "points": [{
                    "algorithm": "xyz", "d": 100, "status": "confirmation_failed"
                }]
            }))
            runner.checkpoints.save(runner._result_row(
                stage="sealed_confirmation", domain="sealed_confirmation",
                algorithm="xyz", d=100, trial=0, candidate_id="test-candidate",
                resource=40, dataset={"trial": 0},
                seeds={"identity": 0, "alice_order": 1, "bob_order": 2},
                result=_engine_result(), cpu_affinity=0,
            ))

            def must_not_run(*_args, **_kwargs):
                raise AssertionError("unconfirmed point entered timing")

            runner._safe_engine = must_not_run
            with mock.patch("figure2.formal.const.DIFFERENCES", (100,)), \
                    mock.patch("figure2.formal.const.ALGORITHMS", ("xyz",)):
                runner.run_timing()
            aggregate = json.loads((root / "aggregate.json").read_text())["points"][0]
            self.assertEqual("confirmation_failed", aggregate["status"])
            for field in ("state_bits", "control_bits", "total_payload_bits", "R_w30"):
                self.assertIsNone(aggregate[field])

    def test_confirmation_resource_limit_suppresses_larger_timing_points(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = _bare_runner(root)
            (root / "operating_points_discovery.json").write_text(json.dumps({
                "operating_points": [
                    {"algorithm": "xyz", "d": d, "status": "selected",
                     "resource": 40, "candidate_id": "test-candidate"}
                    for d in (100, 300)
                ]
            }))
            (root / "confirmation_summary.json").write_text(json.dumps({
                "points": [
                    {"algorithm": "xyz", "d": 100, "status": "timeout"},
                    {"algorithm": "xyz", "d": 300, "status": "confirmed"},
                ]
            }))
            runner.checkpoints.save(runner._result_row(
                stage="sealed_confirmation", domain="sealed_confirmation",
                algorithm="xyz", d=300, trial=0, candidate_id="test-candidate",
                resource=40, dataset={"trial": 0},
                seeds={"identity": 0, "alice_order": 1, "bob_order": 2},
                result=_engine_result(), cpu_affinity=0,
            ))

            def must_not_run(*_args, **_kwargs):
                raise AssertionError("confirmation resource limit did not propagate")

            runner._safe_engine = must_not_run
            with mock.patch("figure2.formal.const.DIFFERENCES", (100, 300)), \
                    mock.patch("figure2.formal.const.ALGORITHMS", ("xyz",)):
                runner.run_timing()
            points = {
                row["d"]: row
                for row in json.loads((root / "timing_summary.json").read_text())["points"]
            }
            self.assertEqual("timeout", points[100]["timing_status"])
            self.assertEqual("not_run_after_resource_limit", points[300]["timing_status"])
            self.assertEqual(0, points[300]["successful_datasets"])


if __name__ == "__main__":
    unittest.main()
