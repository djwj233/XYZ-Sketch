#pragma once
#include <bits/stdc++.h>
#ifndef XYZ_GF230_BACKEND
#define XYZ_GF230_BACKEND 1
#endif
#define DISABLE_DEFAULT_FIELDS
#define ENABLE_FIELD_30
// Unmodified MiniSketch implementations; only Field30 is instantiated.
#if XYZ_GF230_BACKEND == 0
#include "../vendor/minisketch/src/fields/generic_4bytes.cpp"
using XYZBinaryField=Field30;
#else
#include "../vendor/minisketch/src/fields/clmul_4bytes.cpp"
using XYZBinaryField=FieldTri30;
#endif
inline constexpr unsigned XYZ_FIELD_SIZE=1U<<30;
inline constexpr unsigned XYZ_FIELD_MASK=XYZ_FIELD_SIZE-1;
inline const XYZBinaryField xyz_field{};
using XYZMultiplier=XYZBinaryField::Multiplier;
inline int FieldMultiply(int a,int b){
    if(a==0 || b==0)return 0;
    if(a==1)return b;if(b==1)return a;
    return xyz_field.Mul(a,b);
}
inline int FieldInverse(int x){
    // Match the old helper's zero behavior; valid reciprocal inputs are nonzero.
    return x==0?0:x==1?1:xyz_field.Inv(x);
}
inline std::mt19937 rng(114514);
