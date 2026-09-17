# Threshold validation record

## Environment

- Date: `2026-07-15`
- Python: `3.8.10`
- Dependencies: Python standard library only

## Commands

```bash
python3 -m unittest -v test_thresholds.py
python3 thresholds.py --appendix-grid --format json \
  --output validated_thresholds.json
python3 thresholds.py --pairs 2:3,2:6,3:4 --format table
python3 -m py_compile thresholds.py test_thresholds.py
```

## Test result

```text
Ran 6 tests in 0.036s
OK
```

The six tests cover:

- Poisson tail against direct finite lower-tail summation;
- the Poisson tail recurrence identity;
- all 48 `c^peel/c^orient` entries in Appendix Table 3;
- the `(k,ell)=(2,1)` special case;
- `c^peel <= c^orient <= ell` and critical-equation residual bounds;
- the three principal Figure 1(a) operating points to nine decimal places.

## Generated result audit

- Entries in `validated_thresholds.json`: `48`
- Maximum absolute peel-equation residual: `2.4313884239290928e-14`
- Maximum absolute orient-equation residual: `1.3500311979441904e-13`
- SHA-256: `ef3f0c89d96ab326ed5c33340210b37033e47b033e9f124811cce7c80ef83b87`

Principal operating points:

| `(k,ell)` | `peel_xi` | `c^peel` | `orient_xi` | `c^orient` |
| ---: | ---: | ---: | ---: | ---: |
| `(2,3)` | `3.3836342829` | `2.5747013735` | `5.0714697082` | `2.8774628058` |
| `(2,6)` | `7.7245836004` | `4.9376453624` | `11.6220108348` | `5.9644362395` |
| `(3,4)` | `6.5155918261` | `2.7467258764` | `11.9332406302` | `3.9970126256` |
