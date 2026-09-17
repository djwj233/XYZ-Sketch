# Figure 2 Implementation Final Pass Re-audit Report

## 1. Conclusion

**Status: `implementation_audited`.**

No significant implementation or formal-gate issue remains. The prior Go source-tree binding blocker is closed, all previously
closed findings remain closed, and the current implementation artifacts and executables are internally consistent. This report
supersedes the failure dispositions in earlier implementation audit reports.

No formal resource discovery, sealed confirmation, timing trial, or formal plot generation was executed during this audit.

## 2. Final Blocker Closure

### Go source is bound by the formal gate

- `figure2/artifacts.py:73-75` includes `.go` in the source-tree suffix allowlist.
- `go/figure2_riblt_engine/main.go` is therefore included in the audited Figure 2 source-tree hash.
- `tests/test_formal.py:115-188` creates and binds a representative `main.go`, mutates it, and verifies that
  `validate_formal_gate()` rejects the resulting source-tree mismatch.
- The regenerated `build_manifest.json` records the current source-tree SHA-256, and `implementation_summary.json` binds the
  regenerated build manifest.

### Non-circular audit binding remains narrow

- Only root generated implementation audit/reaudit reports and root `implementation_audited.json` are excluded.
- `IMPLEMENTATION_AUDIT_REQUEST.md`, protocol Markdown, tests, CMake, formal-limit JSON, and nested report-like files remain
  covered.
- The exclusion behavior has focused regression coverage in `tests/test_formal.py:95-113`.

## 3. No-regression Review

- The formal gate rehashes all implementation-summary child artifacts.
- The current Figure 2 source tree is recomputed and compared with the build manifest before runner creation or resume.
- Exact executable paths and current SHA-256 hashes are verified.
- The independent audit must bind the exact current implementation-summary SHA-256.
- The verified source hash is recorded in the gate result and run configuration.
- Timing `process_error` remains persistently fatal in live and resumed runs.
- Unconfirmed communication points and incomplete/resource-limited timing points remain ineligible for plotting.
- Curves and confidence bands break across missing registered `d` values.
- Singleton panels and singleton segments remain safe.
- Previously reviewed wire parsing, timing boundaries, retry semantics, worker policy, and external IBLT patch scope show no
  identified regression.

## 4. Verification Record

Executed from `experiment/figure-2/`:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Result:

```text
Ran 40 tests in 2.256s
OK
```

Current and manifest Figure 2 source-tree SHA-256:

```text
fbb7d72b0182945592398f282f1b7cda75a6410a9299b32a9e82097c504f5898
```

Current implementation-summary SHA-256:

```text
3c9e38617ad6d04c5e51f4687e0f0fa39fd1a082494ba2fca9bab9e08ca7ec77
```

All six child-artifact hashes and all seven executable hashes matched their manifests. `formal_trials_executed=false`, and
`git diff --check` passed.

## 5. Disposition

The current implementation is approved for the next gated stage. The accompanying `implementation_audited.json` binds exactly
the implementation-summary SHA-256 shown above. Any subsequent change to covered source, tests, protocol, CMake, or formal limits,
or any replacement of a bound executable, must invalidate the formal gate until the implementation artifacts are regenerated and
independently re-audited.
