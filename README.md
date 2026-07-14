# XYZ-Sketch

## Repository Structure

```text
XYZ-Sketch/          XYZ-Sketch implementation and end-to-end sample
IBLT/                Conventional IBLT implementation and sample
docs/                Complete usage guides for XYZ-Sketch and IBLT
external/            Third-party reconciliation implementations (submodules)
```

External submodules:

- [MiniSketch](https://github.com/bitcoin-core/minisketch)
- [Rateless IBLT](https://github.com/yangl1996/riblt)
- [IBLT C++](https://github.com/gavinandresen/IBLT_Cplusplus)
- [CPISync](https://github.com/Bowenislandsong/cpisync)
- [Negentropy](https://github.com/hoytech/negentropy)

## XYZ-Sketch Sample

Run from the repository root:

```bash
g++ -std=c++17 -O2 XYZ-Sketch/sample.cpp -o /tmp/xyz_sketch_sample \
  && /tmp/xyz_sketch_sample
```

## IBLT Sample

Run from the repository root:

```bash
g++ -std=c++17 -O2 IBLT/iblttest.cpp -o /tmp/iblt_sample \
  && /tmp/iblt_sample
```
