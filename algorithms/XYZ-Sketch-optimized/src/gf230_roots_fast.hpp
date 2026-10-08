#pragma once
// Derived from MiniSketch src/sketch_impl.h, commit
// d1bd01e189e745cd1828707e0a7004b6a6909650; MIT license retained in vendor.
// Only the trace operation below is specialized; recursion and its failure
// checks are structurally identical to the upstream algorithm.

// Polynomial GCD is defined only up to a nonzero scalar. Native remainder
// elimination can postpone all normalization until the final factor.
template<typename F>void XYZGCD(std::vector<typename F::Elem>& a,std::vector<typename F::Elem>& b,const F& field){
#if XYZ_GF230_BACKEND != 0 && !defined(XYZ_MONIC_GCD)
 if(a.size()<b.size())std::swap(a,b);
 while(!b.empty()){
  if(b.size()==1){a.assign(1,1);return;}
  if(b.back()==1){PolyMod(b,a,field);}
  else{
   typename F::Multiplier leading(field,b.back());
   while(a.size()>=b.size()){
    auto term=a.back();a.pop_back();
    if(term){
     for(auto& coefficient:a)coefficient=leading(coefficient);
     typename F::Multiplier eliminate(field,term);
     size_t shift=a.size()+1-b.size();
     for(size_t j=0;j+1<b.size();++j)a[shift+j]^=eliminate(b[j]);
    }
   }
   while(!a.empty()&&!a.back())a.pop_back();
  }
  std::swap(a,b);
 }
#else
 GCD(a,b,field);
#endif
}

template<int D,typename F>
void XYZSmallTraceMod(const std::vector<typename F::Elem>& mod,
 std::vector<typename F::Elem>& out,typename F::Elem param,const F& field){
 using E=typename F::Elem;
 constexpr int FIRST=(D+1)/2, HIGH=D-FIRST;
 E reduction[HIGH][D]{};
 // Compute each x^(2j) modulo the fixed monic polynomial once. All 29
 // Frobenius steps then reuse these remainders, avoiding repeated division.
 for(int j=FIRST;j<D;++j){
  E work[2*D-1]{};work[2*j]=1;
  for(int n=2*j;n>=D;--n){
   E term=work[n];
   if(term)for(int i=0;i<D;++i)work[n-D+i]^=field.Mul(term,mod[i]);
  }
  for(int i=0;i<D;++i)reduction[j-FIRST][i]=work[i];
 }
 E value[D]{};value[1]=param;
 for(int round=0;round<field.Bits()-1;++round){
  E square[D];
#if XYZ_GF230_BACKEND != 0 && !defined(XYZ_TABLE_SQUARES)
  // In characteristic two, squaring packed 32-bit coefficients has no
  // cross terms: one 64x64 CLMUL gives two independent 30-bit squares.
  int j=0;
  for(;j+1<D;j+=2){
   __m128i packed=_mm_loadl_epi64(reinterpret_cast<const __m128i*>(value+j));
   __m128i product=_mm_clmulepi64_si128(packed,packed,0);
   __m128i high=_mm_srli_epi64(product,30);
   __m128i reduced=_mm_and_si128(_mm_xor_si128(product,_mm_xor_si128(high,_mm_slli_epi64(high,1))),_mm_set1_epi64x(XYZ_FIELD_MASK));
   __m128i output=_mm_shuffle_epi32(reduced,_MM_SHUFFLE(2,0,2,0));
   _mm_storel_epi64(reinterpret_cast<__m128i*>(square+j),output);
  }
  if(j<D)square[j]=field.Mul(value[j],value[j]);
#else
  for(int j=0;j<D;++j)square[j]=field.Sqr(value[j]);
#endif
  for(int i=0;i<D;++i){
   E next=(i%2==0)?square[i/2]:0;
#if XYZ_GF230_BACKEND != 0
   // GF reduction is linear: XOR unreduced carry-less products and reduce
   // their sum once. This is precisely the same field dot product.
   __m128i product=_mm_setzero_si128();
   for(int j=FIRST;j<D;++j)product=_mm_xor_si128(product,
    _mm_clmulepi64_si128(_mm_cvtsi64_si128(square[j]),
     _mm_cvtsi64_si128(reduction[j-FIRST][i]),0));
   __m128i high=_mm_srli_epi64(product,30);
   __m128i reduced=_mm_xor_si128(product,_mm_xor_si128(high,_mm_slli_epi64(high,1)));
   next^=uint32_t(_mm_cvtsi128_si64(reduced))&XYZ_FIELD_MASK;
#else
   for(int j=FIRST;j<D;++j)next^=field.Mul(square[j],reduction[j-FIRST][i]);
#endif
   value[i]=next;
  }
  value[1]^=param;
 }
 out.assign(value,value+D);
 while(!out.empty()&&!out.back())out.pop_back();
}
template<typename F>
void XYZTraceMod(const std::vector<typename F::Elem>& mod,
 std::vector<typename F::Elem>& out,typename F::Elem param,const F& field){
 switch(mod.size()){
  case 4:return XYZSmallTraceMod<3>(mod,out,param,field);
  case 5:return XYZSmallTraceMod<4>(mod,out,param,field);
  case 6:return XYZSmallTraceMod<5>(mod,out,param,field);
  case 7:return XYZSmallTraceMod<6>(mod,out,param,field);
  case 8:return XYZSmallTraceMod<7>(mod,out,param,field);
  case 9:return XYZSmallTraceMod<8>(mod,out,param,field);
  default:return TraceMod(mod,out,param,field);
 }
}
template<typename F>
bool XYZRecFindRoots(std::vector<std::vector<typename F::Elem>>& stack, size_t pos, std::vector<typename F::Elem>& roots, bool fully_factorizable, int depth, typename F::Elem randv, const F& field) {
    auto& ppoly = stack[pos];
    // We assert ppoly.size() > 1 (instead of just ppoly.size() > 0) to additionally exclude
    // constants polynomials because
    //  - ppoly is not constant initially (this is ensured by FindRoots()), and
    //  - we never recurse on a constant polynomial.
    CHECK_SAFE(ppoly.size() > 1 && ppoly.back() == 1);
    /* 1st degree input: constant term is the root. */
    if (ppoly.size() == 2) {
        roots.push_back(ppoly[0]);
        return true;
    }
    /* 2nd degree input: use direct quadratic solver. */
    if (ppoly.size() == 3) {
        CHECK_RETURN(ppoly[1] != 0, false); // Equations of the form (x^2 + a) have two identical solutions; contradicts square-free assumption. */
        auto input = field.Mul(ppoly[0], field.Sqr(field.Inv(ppoly[1])));
        auto root = field.Qrt(input);
        if ((field.Sqr(root) ^ root) != input) {
            CHECK_SAFE(!fully_factorizable);
            return false; // No root found.
        }
        auto sol = field.Mul(root, ppoly[1]);
        roots.push_back(sol);
        roots.push_back(sol ^ ppoly[1]);
        return true;
    }
    /* 3rd degree input and more: recurse further. */
    if (pos + 3 > stack.size()) {
        // Allocate memory if necessary.
        stack.resize((pos + 3) * 2);
    }
    auto& poly = stack[pos];
    auto& tmp = stack[pos + 1];
    auto& trace = stack[pos + 2];
    trace.clear();
    tmp.clear();
    for (int iter = 0;; ++iter) {
        // Compute the polynomial (trace(x*randv) mod poly(x)) symbolically,
        // and put the result in `trace`.
        XYZTraceMod(poly, trace, randv, field);

        if (iter >= 1 && !fully_factorizable) {
            // If the polynomial cannot be factorized completely (it has an
            // irreducible factor of degree higher than 1), we want to avoid
            // the case where this is only detected after trying all BITS
            // independent split attempts fail (see the assert below).
            //
            // Observe that if we call y = randv*x, it is true that:
            //
            //   trace = y + y^2 + y^4 + y^8 + ... y^(FIELDSIZE/2) mod poly
            //
            // Due to the Frobenius endomorphism, this means:
            //
            //   trace^2 = y^2 + y^4 + y^8 + ... + y^FIELDSIZE mod poly
            //
            // Or, adding them up:
            //
            //   trace + trace^2 = y + y^FIELDSIZE mod poly.
            //                   = randv*x + randv^FIELDSIZE*x^FIELDSIZE
            //                   = randv*x + randv*x^FIELDSIZE
            //                   = randv*(x + x^FIELDSIZE).
            //     (all mod poly)
            //
            // x + x^FIELDSIZE is the polynomial which has every field element
            // as root once. Whenever x + x^FIELDSIZE is multiple of poly,
            // this means it only has unique first degree factors. The same
            // holds for its constant multiple randv*(x + x^FIELDSIZE) =
            // trace + trace^2.
            //
            // We use this test to quickly verify whether the polynomial is
            // fully factorizable after already having computed a trace.
            // We don't invoke it immediately; only when splitting has failed
            // at least once, which avoids it for most polynomials that are
            // fully factorizable (or at least pushes the test down the
            // recursion to factors which are smaller and thus faster).
            tmp = trace;
            Sqr(tmp, field);
            for (size_t i = 0; i < trace.size(); ++i) {
                tmp[i] ^= trace[i];
            }
            while (tmp.size() && tmp.back() == 0) tmp.pop_back();
            PolyMod(poly, tmp, field);

            // Whenever the test fails, we can immediately abort the root
            // finding. Whenever it succeeds, we can remember and pass down
            // the information that it is in fact fully factorizable, avoiding
            // the need to run the test again.
            if (tmp.size() != 0) return false;
            fully_factorizable = true;
        }

        if (fully_factorizable) {
            // Every successful iteration of this algorithm splits the input
            // polynomial further into buckets, each corresponding to a subset
            // of 2^(BITS-depth) roots. If after depth splits the degree of
            // the polynomial is >= 2^(BITS-depth), something is wrong.
            CHECK_RETURN(field.Bits() - depth >= std::numeric_limits<decltype(poly.size())>::digits ||
                (poly.size() - 2) >> (field.Bits() - depth) == 0, false);
        }

        depth++;
        // In every iteration we multiply randv by 2. As a result, the set
        // of randv values forms a GF(2)-linearly independent basis of splits.
        randv = field.Mul2(randv);
        tmp = poly;
        XYZGCD(trace, tmp, field);
        if (trace.size() != poly.size() && trace.size() > 1) break;
    }
    MakeMonic(trace, field);
    DivMod(trace, poly, tmp, field);
    // At this point, the stack looks like [... (poly) tmp trace], and we want to recursively
    // find roots of trace and tmp (= poly/trace). As we don't care about poly anymore, move
    // trace into its position first.
    std::swap(poly, trace);
    // Now the stack is [... (trace) tmp ...]. First we factor tmp (at pos = pos+1), and then
    // we factor trace (at pos = pos).
    if (!XYZRecFindRoots(stack, pos + 1, roots, fully_factorizable, depth, randv, field)) return false;
    // The stack position pos contains trace, the polynomial with all of poly's roots which (after
    // multiplication with randv) have trace 0. This is never the case for irreducible factors
    // (which always end up in tmp), so we can set fully_factorizable to true when recursing.
    bool ret = XYZRecFindRoots(stack, pos, roots, true, depth, randv, field);
    // Because of the above, recursion can never fail here.
    CHECK_SAFE(ret);
    return ret;
}

