# Figure 2 v3 correction protocol

## Scope

Protocol v3 removes every experiment-wrapper byte from Figure 2 communication and timing paths, corrects the timer
boundaries identified after the v2 run, reuses probability evidence whose algorithmic state is unchanged, and reruns all
timing points from new datasets. The v2 source run and its refinement remain immutable parent artifacts.

## Shared configuration

Alice and Bob know the algorithm, `d`, `w=30`, selected `M/cap`, frozen algorithm profile, and public randomness before a
session. No wrapper envelope or parameter copy is transmitted. Wrapper payload is exactly zero bytes.

The counted payload is:

| Algorithm | Counted bytes |
| --- | --- |
| XYZ-Sketch | Packed core sketch state |
| MiniSketch | `minisketch_serialize()` output |
| External IBLT | Canonically serialized upstream cells |
| Project IBLT | Canonically serialized project cells |
| Rateless IBLT | Bit-packed upstream coded symbols |
| CPISync | Complete upstream `CommString` transcript |

CPISync retains 41 upstream control bytes per transcript. Its v3 payload is therefore `state_bits + 328`. The other five
profiles have `control_bits=0`. Figure 2(a) uses `total_payload_bits/(30d)`.

## Timing boundaries

The update timer includes algorithm update work and algorithm-internal allocation. It excludes dataset generation, input
container preparation, CPISync `DataObject` construction, MiniSketch's Bob membership-index construction, serialization,
logging, manifests, and audit work.

The decode timer remains the sum of sender serialization, one immutable payload copy, and receiver parsing/subtraction/
decoding through formation of the directed output. Residual hashes, ground-truth comparisons, and artifact serialization
are outside all timers.

MiniSketch prepares Bob's membership index before the timer and charges only the `d` output membership queries to decode.
Project IBLT moves prepared input vectors through its batch API, while table initialization inside `Encode()` remains timed.
Rateless IBLT uses upstream `Sketch` for the predetermined cap, so source-symbol mappings are applied during update rather
than deferred to the first coded symbol. CPISync times `addElem()` but not caller-owned `DataObject` construction.

## Probability reuse

The core profile hashes remain byte-for-byte equal to v2, preserving dataset seeds, XYZ decoder seeds, and Rateless IBLT
SipHash keys. No core algorithm source is modified.

The v2 probability results and selected operating points are reused only after all of the following checks pass:

1. Parent aggregate, refinement, operating-point, and implementation-profile hashes match their recorded artifacts.
2. All six old and new core profile hashes are identical.
3. New engine golden and full/difference equivalence suites pass.
4. Rateless `Sketch` matches the first `cap` outputs of `Encoder` for 18 combinations of key and cap.
5. The new build manifest asserts `core_algorithm_modified=false`.

The migration manifest binds this evidence, the parent hashes, the payload transform, the v3 source-tree hash, and every v3
executable hash. It reuses status, success count, confidence interval, and selected resource, but no v2 timing value.

## Timing rerun

Every v3-confirmed point collects five successful timing-domain datasets with three measured repetitions per dataset and no
warm-up. Algorithms run serially on CPU 0. Failed decodes use a new dataset and do not enter the estimate. Timeout/OOM stops
that algorithm at the current and all larger `d`; process errors fail the correction run.

The old MiniSketch `d=10000` and CPISync `d=3000` points were probability/resource timeouts, not confirmed operating points.
The v3 changes do not reduce their whole-process wall work, so they are retained as unconfirmed and are not rerun. This avoids
spending the registered timeout again without a change capable of making those points eligible.

Each repetition is written atomically to a checkpoint. The correction runner is resumable, and final aggregation is allowed
only after every confirmed non-resource-limited point reaches five successful datasets.
