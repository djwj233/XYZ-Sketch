# XYZ-Sketch optimization overview

The original implementation is preserved in `algorithms/XYZ-Sketch-unoptimized/`.
The optimized implementation is in `algorithms/XYZ-Sketch-optimized/`.

1. **Binary-field arithmetic.** Replace the prime field with GF(2^30), using XOR,
   carry-less multiplication, and fast squaring. Reuse MiniSketch's field techniques
   and lookup constants rather than repeatedly applying prime-field reductions.
2. **Small-degree polynomial routines.** Use compact inline storage and specialized
   operations for the small cell capacities used in the experiments. Reduce allocation,
   copying, normalization, and unnecessary work in rational reconstruction.
3. **Faster root finding.** Use characteristic-two trace methods, lookup tables, and
   shortcuts for small polynomials. Retain root, square-free, and placement checks.
4. **Cheaper updates.** Compute an element's coefficient contribution once, reuse it
   across its cells, and specialize the common capacities. Improve the memory layout
   and reduce repeated hashing and indexing work.
5. **Cheaper recovery.** Batch inversions, use forward elimination and delayed GCD
   normalization, and avoid redundant sorting and temporary containers. Use equivalent
   paths for common recoverable cells.

The binary-field version changes the arithmetic field; the shared 30-bit inputs remain
unchanged. Structural peeling simulations are independent of these arithmetic routines.
Validation checks signed output, wire accounting, native/generic arithmetic, and the
optimized recovery paths. The timing data uses the optimized implementation.
