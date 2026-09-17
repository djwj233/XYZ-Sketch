# External IBLT experiment adapter

`iblt-canonical-wire.patch` applies to `external/IBLT_Cplusplus` at
`db28fd0fd213b37714e7dfdea3ca2ca67e9f1c09` (the pinned upstream submodule).
It adds `cell_count`, `serialize_canonical` and `deserialize_canonical` for the
Figure 2 wrapper, with the 25-bit count, 30-bit key and 32-bit check wire layout.
The upstream hashing, insertion, subtraction and peeling paths are unchanged.

From the repository root, after initializing the submodule:

```bash
git -C external/IBLT_Cplusplus apply --check ../../patches/iblt-canonical-wire.patch
git -C external/IBLT_Cplusplus apply ../../patches/iblt-canonical-wire.patch
```

The parent repository retains the upstream gitlink. Applying the patch makes
this submodule locally modified by design; no private/unpublished submodule
commit is required to build the experiments.
