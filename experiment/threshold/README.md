# Peelability 与 Orientability 阈值计算

本目录只负责计算论文 Appendix A.2 定义的 `c^peel` 和 `c^orient`，不包含或运行
Figure 1(a) 的集合生成、XYZ-Sketch benchmark、参数扫描或绘图代码。

## 文件

| 文件 | 用途 |
| --- | --- |
| `thresholds.py` | Poisson tail、临界方程求根、阈值计算和 CLI 输出 |
| `test_thresholds.py` | Appendix Table 3 全部 48 项及数学不变量校验 |
| `validated_thresholds.json` | 通过校验后生成的 Appendix Table 3 全表计算结果 |
| `VALIDATION.md` | 本次校验环境、命令、结果、残差和结果文件哈希 |

## 公式

定义：

\[
Q(\xi,r)=\Pr[\operatorname{Pois}(\xi)\ge r].
\]

除 `(k,ell)=(2,1)` 外，`c^peel` 在以下方程的正根处取得：

\[
Q(\xi,\ell)=(k-1)\xi\Pr[\operatorname{Pois}(\xi)=\ell-1],
\]

\[
c^{peel}_{k,\ell}=\frac{\xi}{kQ(\xi,\ell)^{k-1}}.
\]

`c^orient` 使用：

\[
k\ell=\xi^*\frac{Q(\xi^*,\ell)}{Q(\xi^*,\ell+1)},
\]

\[
c^{orient}_{k,\ell}=\frac{\xi^*}{kQ(\xi^*,\ell)^{k-1}}.
\]

特殊情况固定为 `c^peel_{2,1}=0`、`c^orient_{2,1}=1/2`。

## 使用

计算 Figure 1(a) 的三组参数：

```bash
python3 thresholds.py --pairs 2:3,2:6,3:4 --format table
```

计算 Appendix Table 3 全表并写入 JSON：

```bash
python3 thresholds.py --appendix-grid --format json \
  --output validated_thresholds.json
```

运行完整校验：

```bash
python3 -m unittest -v test_thresholds.py
```

校验通过要求：

- Appendix Table 3 的 48 组 `c^peel/c^orient` 全部匹配到四位小数；
- `(2,1)` 特殊情况正确；
- `c^peel <= c^orient <= ell`；
- 两个临界方程的数值残差满足测试上限；
- Figure 1(a) 三组 operating point 匹配到小数点后 9 位。
