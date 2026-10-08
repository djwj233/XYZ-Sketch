#pragma once
#define XYZ_OPT_POLY 1
namespace tool {
using namespace std;
    struct polyMat {
        poly a00, a01, a10, a11;
        polyMat operator*(const polyMat &t) const {
            polyMat res;
            res.a00 = a00 * t.a00 + a01 * t.a10, res.a01 = a00 * t.a01 + a01 * t.a11;
            res.a10 = a10 * t.a00 + a11 * t.a10, res.a11 = a10 * t.a01 + a11 * t.a11;
            res.a00.PopZero(), res.a01.PopZero(), res.a10.PopZero(), res.a11.PopZero();
            return res;
        }
    } ;
    inline polyMat gen(poly Q) {
        return {plv({0}), plv({1}), plv({1}), 1 * Q};
    }
    inline void Mul(polyMat M, poly &A, poly &B) {
        poly tA = A, tB = B;
        A = M.a00 * tA + M.a01 * tB, B = M.a10 * tA + M.a11 * tB;
        A.PopZero(), B.PopZero(); 
    }
    inline pair<poly, poly> Mul(polyMat M, pair<poly, poly> u) {
        Mul(M, u.first, u.second); return u;
    }
    polyMat HalfGCD(poly A, poly B) {
        if(B.deg() == 0) return {plv({1}), plv({0}), plv({0}), plv({1})};
        if(A.deg() == 0) return {plv({0}), plv({1}), plv({1}), plv({0})};
        int len = A.deg(), m = (len + 1) / 2;
        if(B.deg() < m) return {plv({1}), plv({0}), plv({0}), plv({1})};
        poly A1 = A.Shift(-m), B1 = B.Shift(-m); auto M = HalfGCD(A1, B1);
        Mul(M, A, B); if(B.deg() < m) return M;

        auto tmp = div(A, B); A = B, B = tmp.second;
        M = gen(tmp.first) * M; if(B.deg() < m) return M;

        int k = 2 * m - A.deg(); A1 = A.Shift(-k), B1 = B.Shift(-k);
        return HalfGCD(A1, B1) * M;
    }
    polyMat coGCD(poly A, poly B) {
        auto M = HalfGCD(A, B); Mul(M, A, B);
        if(B.size() == 0) return M;
        auto tmp = div(A, B); A = B, B = tmp.second;
        M = gen(tmp.first) * M; if(B.size() == 0) return M;
        return coGCD(A, B) * M;
    }
    inline poly GCD(poly A, poly B) {
        if(B == plv({0})) return A;
        if(A == plv({0})) return B;
        #if XYZ_OPT_POLY
        if(A.size()<=17 && B.size()<=17){
            A.PopZero();B.PopZero();while(!B.a.empty()) {
                // As in MiniSketch's Euclidean loop, a nonzero constant ends GCD.
                if(B.size()==1)return plv({1});
                int iv=B.a.back()==1?1:qpow(B.a.back());RemainderInPlace(A,B,iv);std::swap(A,B);
            }A.monic();return A;
        }
#endif
        auto M = coGCD(A, B); auto res = M.a00 * A + M.a01 * B;
        res.PopZero(), res.monic();
        return res;
    }
    // deg A < 2 * n + 1, deg p <= n, deg q <= n
    pair<poly, poly> Recon(poly A, int n) {
        poly M(2 * n + 2); M[2 * n + 1] = 1; A.rs(2 * n + 1);
        auto Mat = HalfGCD(A, M);
        auto X = Mat.a00 * A + Mat.a01 * M;
        X.PopZero(), Mat.a00.PopZero();
        if(X.deg() <= n && Mat.a00.deg() <= n)
            return make_pair(X, Mat.a00);
        auto Y = Mat.a10 * A + Mat.a11 * M;
        Y.PopZero(), Mat.a10.PopZero();
        if(Y.deg() <= n && Mat.a10.deg() <= n)
            return make_pair(Y, Mat.a10);
        assert(0);
    }
    // find (p, q) s.t.
    // p / q mod x^n = A, deg p + deg q < n, deg p - deg q = m <= 0, [x^0]p = [x^0]q = 1
    // false for no solution
    inline variant<pair<poly, poly>, bool> Reconstruct(poly A, int n, int m) {
        int pdeg = (n - 1 + m) / 2, qdeg = (n - 1 - m) / 2;
        assert(pdeg <= qdeg); int delta = qdeg - pdeg;
        A.ShiftSelf(delta); auto res = Recon(A, qdeg);
        bool fl = (res.first.deg() >= delta);
        for(int i = 0; fl && i < delta; i++)
            fl = (res.first[i] == 0);
        if(!fl) return false;
        return make_pair(res.first.Shift(-delta), res.second);
    }
    // find (p, q) s.t.
    // p / q mod x^n = A; deg p + deg q <= n; deg p - deg q = m; p, q monic
    // A invertible
    inline variant<pair<poly, poly>, bool> RFuncReconstructReference(poly A, int n, int m) {
        if(A == plv({1})) {
            if(m != 0) return false;
            return make_pair(plv({1}), plv({1}));
        }
        A.rs(n); auto rec = A;
        variant<pair<poly, poly>, bool> Res;
        if(m < 0) {
            A = A.Inv(), A = A - plv({1}).Shift(-m);
            Res = Reconstruct(A.Inv(), n, m + 1);
        } else if(m == 0) {
            A = A - plv({1});
            Res = Reconstruct(A, n, -1);
        } else {
            A = A - plv({1}).Shift(m);
            Res = Reconstruct(A.Inv(), n, -m + 1);
        }
        if(Res.index() == 1) return false;
        auto res = get<pair<poly, poly> >(Res); poly P = res.first, Q = res.second;
        if(m < 0) {
            Q = Q + P.Shift(-m);
        } else if(m == 0) {
            P = P + Q;
        } else {
            swap(P, Q), P = P + Q.Shift(m);
        }
        P.rs(n + 1), Q.rs(n + 1);
        auto now = TruncatedProduct(P, Q.Inv(), n);
        P.PopZero(), Q.PopZero();
        if(now == rec) return make_pair(P, Q);
        return false;
    }



    // For small cells solve the same degree-aware rational reconstruction problem
    // directly. With r=floor((n+m)/2), s=floor((n-m)/2), choose G(0)=1 and
    // impose [Z^r](RG)=[Z^s]G, [Z^i](RG)=0 for r<i<n.
    // The leading-coefficient condition cancels a potential degree-n term in
    // the cross product, so any solutions describe the same rational function.
    inline variant<pair<poly, poly>, bool> RFuncReconstructSmallV11(const poly& A, int n, int m) {
        if(n<1 || n>8 || m < -n || m > n || !A.v(0)) return false;
        if(A == plv({1})) {
            if(m != 0) return false;
            return make_pair(plv({1}),plv({1}));
        }
        const int r=(n+m)/2,s=(n-m)/2,rows=n-r;
        int mat[8][9]{};int pivot[8]{};int rank=0;
        for(int i=0;i<rows;++i){
            const int k=r+i;
            for(int j=1;j<=s;++j) mat[i][j-1]=A.v(k-j) ^ ((k==r && j==s)?1:0);
            mat[i][s]=A.v(k) ^ ((k==r && s==0)?1:0);
        }
        for(int col=0;col<s && rank<rows;++col){
            int row=rank;while(row<rows && !mat[row][col])++row;
            if(row==rows)continue;
            if(row!=rank)for(int j=col;j<=s;++j)std::swap(mat[row][j],mat[rank][j]);
            XYZMultiplier normalize(xyz_field,FieldInverse(mat[rank][col]));
            for(int j=col+1;j<=s;++j)mat[rank][j]=normalize(mat[rank][j]);
            mat[rank][col]=1;
            for(int i=0;i<rows;++i)if(i!=rank && mat[i][col]){
                XYZMultiplier eliminate(xyz_field,mat[i][col]);
                for(int j=col+1;j<=s;++j)mat[i][j]^=eliminate(mat[rank][j]);
                mat[i][col]=0;
            }
            pivot[rank++]=col;
        }
        for(int i=rank;i<rows;++i)if(mat[i][s])return false;
        poly G(s+1);G[0]=1;
        for(int i=0;i<rank;++i)G[pivot[i]+1]=mat[i][s];
        poly F=TruncatedProduct(A,G,std::min(n,r+1));
        if(r==n){F.rs(n+1);F[n]=1;}
        F.PopZero();G.PopZero();
        // A full-column-rank system has a unique normalized denominator. A
        // nonconstant common factor would let that factor vary (with fixed
        // constant coefficient), producing another solution to the same system.
        // Only rank-deficient systems can therefore need common-factor removal.
        if(rank<s){
            auto common=GCD(F,G);
            if(common.size()>1){F=div(F,common).first;G=div(G,common).first;}
        }
        return make_pair(std::move(F),std::move(G));
    }
    inline variant<pair<poly, poly>, bool> RFuncReconstructSmallForward(const poly& A, int n, int m) {
        if(n<1 || n>8 || m < -n || m > n || !A.v(0)) return false;
        if(A == plv({1})) {
            if(m != 0) return false;
            return make_pair(plv({1}),plv({1}));
        }
        const int r=(n+m)/2,s=(n-m)/2,rows=n-r;
        int mat[8][9]{};int pivot[8]{};int rank=0;
        for(int i=0;i<rows;++i){
            const int k=r+i;
            for(int j=1;j<=s;++j) mat[i][j-1]=A.v(k-j) ^ ((k==r && j==s)?1:0);
            mat[i][s]=A.v(k) ^ ((k==r && s==0)?1:0);
        }
        // Row echelon form without pivot inversions. Multiplying a row by
        // a nonzero pivot preserves exactly the same solution set.
        for(int col=0;col<s && rank<rows;++col){
            int row=rank;while(row<rows && !mat[row][col])++row;
            if(row==rows)continue;
            if(row!=rank)for(int j=col;j<=s;++j)std::swap(mat[row][j],mat[rank][j]);
            XYZMultiplier pivot_multiply(xyz_field,mat[rank][col]);
            for(int i=rank+1;i<rows;++i)if(mat[i][col]){
                XYZMultiplier eliminate(xyz_field,mat[i][col]);
                for(int j=col+1;j<=s;++j)mat[i][j]=pivot_multiply(mat[i][j])^eliminate(mat[rank][j]);
                mat[i][col]=0;
            }
            pivot[rank++]=col;
        }
        for(int i=rank;i<rows;++i)if(mat[i][s])return false;
        // Batch inversion of the nonzero diagonal, followed by back
        // substitution with all free variables zero, as in the v11 solver.
        int inverses[8]{},product=1;
        for(int i=0;i<rank;++i){inverses[i]=product;product=FieldMultiply(product,mat[i][pivot[i]]);}
        int inverse_product=FieldInverse(product);
        for(int i=rank-1;i>=0;--i){int preceding=inverses[i];inverses[i]=FieldMultiply(preceding,inverse_product);inverse_product=FieldMultiply(inverse_product,mat[i][pivot[i]]);}
        poly G(s+1);G[0]=1;
        for(int i=rank-1;i>=0;--i){int rhs=mat[i][s];
            for(int j=pivot[i]+1;j<s;++j)rhs^=FieldMultiply(mat[i][j],G[j+1]);
            G[pivot[i]+1]=FieldMultiply(rhs,inverses[i]);
        }
        poly F=TruncatedProduct(A,G,std::min(n,r+1));
        if(r==n){F.rs(n+1);F[n]=1;}
        F.PopZero();G.PopZero();
        // A full-column-rank system has a unique normalized denominator. A
        // nonconstant common factor would let that factor vary (with fixed
        // constant coefficient), producing another solution to the same system.
        // Only rank-deficient systems can therefore need common-factor removal.
        if(rank<s){
            auto common=GCD(F,G);
            if(common.size()>1){F=div(F,common).first;G=div(G,common).first;}
        }
        return make_pair(std::move(F),std::move(G));
    }
    template<int N,int Difference>inline variant<pair<poly, poly>, bool> RFuncReconstructSix(const poly& A) {
        constexpr int n=N,m=Difference;
        if(n<1 || n>8 || m < -n || m > n || !A.v(0)) return false;
        if(A == plv({1})) {
            if(m != 0) return false;
            return make_pair(plv({1}),plv({1}));
        }
        constexpr int r=(n+m)/2,s=(n-m)/2,rows=n-r;
        int mat[rows?rows:1][s+1]{};int pivot[rows?rows:1]{};int rank=0;
        for(int i=0;i<rows;++i){
            const int k=r+i;
            for(int j=1;j<=s;++j) mat[i][j-1]=A.v(k-j) ^ ((k==r && j==s)?1:0);
            mat[i][s]=A.v(k) ^ ((k==r && s==0)?1:0);
        }
        // Row echelon form without pivot inversions. Multiplying a row by
        // a nonzero pivot preserves exactly the same solution set.
        for(int col=0;col<s && rank<rows;++col){
            int row=rank;while(row<rows && !mat[row][col])++row;
            if(row==rows)continue;
            if(row!=rank)for(int j=col;j<=s;++j)std::swap(mat[row][j],mat[rank][j]);
            XYZMultiplier pivot_multiply(xyz_field,mat[rank][col]);
            for(int i=rank+1;i<rows;++i)if(mat[i][col]){
                XYZMultiplier eliminate(xyz_field,mat[i][col]);
                for(int j=col+1;j<=s;++j)mat[i][j]=pivot_multiply(mat[i][j])^eliminate(mat[rank][j]);
                mat[i][col]=0;
            }
            pivot[rank++]=col;
        }
        for(int i=rank;i<rows;++i)if(mat[i][s])return false;
        // Batch inversion of the nonzero diagonal, followed by back
        // substitution with all free variables zero, as in the v11 solver.
        int inverses[8]{},product=1;
        for(int i=0;i<rank;++i){inverses[i]=product;product=FieldMultiply(product,mat[i][pivot[i]]);}
        int inverse_product=FieldInverse(product);
        for(int i=rank-1;i>=0;--i){int preceding=inverses[i];inverses[i]=FieldMultiply(preceding,inverse_product);inverse_product=FieldMultiply(inverse_product,mat[i][pivot[i]]);}
        poly G(s+1);G[0]=1;
        for(int i=rank-1;i>=0;--i){int rhs=mat[i][s];
            for(int j=pivot[i]+1;j<s;++j)rhs^=FieldMultiply(mat[i][j],G[j+1]);
            G[pivot[i]+1]=FieldMultiply(rhs,inverses[i]);
        }
        poly F=TruncatedProduct(A,G,std::min(n,r+1));
        if(r==n){F.rs(n+1);F[n]=1;}
        F.PopZero();G.PopZero();
        // A full-column-rank system has a unique normalized denominator. A
        // nonconstant common factor would let that factor vary (with fixed
        // constant coefficient), producing another solution to the same system.
        // Only rank-deficient systems can therefore need common-factor removal.
        if(rank<s){
            auto common=GCD(F,G);
            if(common.size()>1){F=div(F,common).first;G=div(G,common).first;}
        }
        return make_pair(std::move(F),std::move(G));
    }
    inline variant<pair<poly, poly>, bool> RFuncReconstructSmall(const poly& A,int n,int m){
#ifdef XYZ_GAUSS_JORDAN_RECON
        return RFuncReconstructSmallV11(A,n,m);
#else
#ifndef XYZ_DYNAMIC_RECON
        if(n==6)switch(m){
            case -6:return RFuncReconstructSix<6,-6>(A);
            case -5:return RFuncReconstructSix<6,-5>(A);
            case -4:return RFuncReconstructSix<6,-4>(A);
            case -3:return RFuncReconstructSix<6,-3>(A);
            case -2:return RFuncReconstructSix<6,-2>(A);
            case -1:return RFuncReconstructSix<6,-1>(A);
            case 0:return RFuncReconstructSix<6,0>(A);
            case 1:return RFuncReconstructSix<6,1>(A);
            case 2:return RFuncReconstructSix<6,2>(A);
            case 3:return RFuncReconstructSix<6,3>(A);
            case 4:return RFuncReconstructSix<6,4>(A);
            case 5:return RFuncReconstructSix<6,5>(A);
            case 6:return RFuncReconstructSix<6,6>(A);
        }
#endif
        return RFuncReconstructSmallForward(A,n,m);
#endif
    }
    inline variant<pair<poly, poly>, bool> RFuncReconstruct(const poly& A, int n, int m) {
        if(n<=8)return RFuncReconstructSmall(A,n,m);
        return RFuncReconstructReference(A,n,m);
    }
} // namespace tool
