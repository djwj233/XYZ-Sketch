# Figure 2 implementation audit request

## Scope

Audit the implementation under `experiment/figure-2/` against `README.md` and
`PROTOCOL_PROFILES.md`. Do not run formal discovery, confirmation, or timing.

The stopped `figure2-v1` run under
`results/figure2-20260717T100942Z-a3758992b92c/` is a superseded record whose
`run_state.json` is `status=abandoned`. Its checkpoints must not be copied into or resumed
by `figure2-v2`. In the regenerated summary, `formal_trials_executed=false` is scoped to
`formal_trials_scope=figure2-v2` and `superseded_run_artifacts_reused=false`.

## Required checks

1. Verify `implementation/implementation_summary.json` has
   `status=implementation_ready_for_audit`, `protocol_version=formal_trials_scope=figure2-v2`,
   `formal_trials_executed=false`, and `superseded_run_artifacts_reused=false`. Verify the
   superseded v1 run is marked abandoned and cannot satisfy a v2 resume configuration.
2. Recompute every hash recorded by that summary.
3. Verify all six wire golden totals and the CPISync state/control split.
4. Verify all 120 equivalence configuration rows compare full-set and
   difference-only residual/output bytes without requiring both runs to succeed.
5. Verify the six smoke outputs exactly match the shared dataset's directed hashes.
6. Verify the candidate grids, fine interval construction, actual external-IBLT cell
   de-duplication, globally smallest expected-entry representative for each actual table,
   maximum candidate counts, and global update budgets.
7. Verify `XYZ-Sketch/` and `IBLT/` are unmodified. Verify the external IBLT patch only
   adds `cell_count()` and canonical serialization/deserialization interfaces.
8. Review `formal.py` for seed-domain isolation, one-time confirmation, checkpoint
   recovery, q[90], timer boundaries, timeout/OOM propagation, prohibition of
   statistical retries in discovery/confirmation, unlimited fresh-dataset retries until
   5 successful timing datasets, eight-physical-core probability execution, and strict
   single-core timing execution after all probability workers have joined. Verify
   subprocess memory limits use `prlimit`, not thread-unsafe `preexec_fn`.
9. Verify timing estimates `E[runtime | decode success]`: every included dataset has
   exactly three successful measured repetitions and no warm-up; failed attempts are retained
   but excluded from means and bootstrap intervals; attempted/failed/successful counts reconcile;
   each dataset observation is the arithmetic mean of its three repetitions.
10. Verify Figure 2(a) independently filters for `status=confirmed`, and timing panels
   independently filter for `timing_status=complete` and `successful_datasets=5`; all
   corresponding aggregate values are null for excluded points.
11. Verify one timeout/OOM forces confirmation status `timeout/oom`, propagates to larger
   `d`, and stops new worker trials. Verify one `process_error` invalidates the whole formal
   run and never enters a discovery/confirmation rate.
12. Verify timing measured `process_error` checkpoints persistently set failed run
   state and prohibit resume, including a complete three-row attempt with
   `not_run_after_process_error` rows.
13. Verify every plotted algorithm is segmented against the complete ordered registered
   `d` grid: missing space/timing points break both lines and confidence bands; singleton
   segments render only markers; singleton panels use a nonzero x span.
14. Verify Figure 2(a) averages actual `state_bits`, `control_bits`, and `total_payload_bits`
   over successful confirmation trials, while every raw row still satisfies exact wire
   accounting. In particular, variable-length CPISync transcripts must not be rejected or
   silently padded.
15. Verify no formal command can start without an audit artifact binding the exact
   implementation-summary SHA-256 and an approved resource-limit file.
16. Verify the formal gate recomputes the current Figure 2 source-tree SHA-256, rejects
   any mismatch with the audited build manifest before creating or resuming a runner,
   and records the verified hash in both `formal_gate.json` and `run_config.json`.
17. Verify source-tree hashing excludes only root-level generated implementation audit
   reports and `implementation_audited.json`; implementation source including Go, tests, CMake,
   `README.md`, `PROTOCOL_PROFILES.md`, this audit request, and formal limits remain
   covered.

## Passing artifact

The independent reviewer should create `implementation_audited.json` in the Figure 2
experiment root, outside `implementation/`,
with exactly these binding fields plus its findings metadata:

```json
{
  "status": "implementation_audited",
  "implementation_summary_sha256": "<exact SHA-256>"
}
```

Do not modify `implementation_summary.json` in place.
