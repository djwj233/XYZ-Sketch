# Figure 1(a) reduced-cardinality coarse source manifest

- Protocol: `figure1a-reduced-v1`
- Workload: `d=10000`, `|A|=|B|=20000` (`reduced-cardinality revision`)
- Git commit: `99bbe7ae42df1f4bfff92f48bcd78ac1e4e6abaf`
- Figure 1(a) and core source SHA-256: `cbabe480c17bade17e6a539c38169b5f404d0f12de5f1e2d4a79a60dd39b724a`
- Threshold SHA-256: `ef3f0c89d96ab326ed5c33340210b37033e47b033e9f124811cce7c80ef83b87`
- Frozen parameters SHA-256: `a88606627f32f0860afb1369e730c292ea33d30ad29568f0c0e9b4a5ae1336c9`
- Sealed holdout summary SHA-256: `3838a1f6e56faeb0d969490154eb994db4f33aaeeee83932e8d9d03d9a643b21`
- C++ engine SHA-256: `20138df394fa61265767e52828bd45bb6dab131a4377e924a5b43bfa71c09bd4`

The run uses the real XYZ-Sketch encode, wire serialization, subtraction, D-RFR,
rehash verification, and peeling path. The core `XYZ-Sketch/` tree is unmodified.
