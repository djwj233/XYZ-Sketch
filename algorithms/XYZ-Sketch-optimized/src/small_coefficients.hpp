#pragma once
class SmallCoefficients {
    #ifndef XYZ_INLINE_COEFFICIENTS
#define XYZ_INLINE_COEFFICIENTS 8
#endif
    static constexpr size_t Capacity=XYZ_INLINE_COEFFICIENTS;
    std::array<int,Capacity> small_;
    std::vector<int> large_;
    size_t n_=0;
public:
    SmallCoefficients()=default;
    explicit SmallCoefficients(size_t n){resize(n);}
    SmallCoefficients(const SmallCoefficients& x){resize(x.n_);std::copy(x.begin(),x.end(),begin());}
    SmallCoefficients(SmallCoefficients&& x) noexcept:n_(x.n_){
        if(n_>Capacity)large_=std::move(x.large_);else std::copy(x.begin(),x.end(),small_.begin());x.n_=0;
    }
    SmallCoefficients& operator=(const SmallCoefficients& x){
        if(this!=&x){resize(x.n_);std::copy(x.begin(),x.end(),begin());}return *this;
    }
    SmallCoefficients& operator=(SmallCoefficients&& x) noexcept {
        if(this!=&x){n_=x.n_;if(n_>Capacity)large_=std::move(x.large_);else std::copy(x.begin(),x.end(),small_.begin());x.n_=0;}return *this;
    }
    SmallCoefficients& operator=(const std::vector<int>& x){resize(x.size());std::copy(x.begin(),x.end(),begin());return *this;}
    operator std::vector<int>()const{return std::vector<int>(begin(),end());}
    size_t size()const{return n_;}bool empty()const{return n_==0;}
    int* data(){return n_>Capacity?large_.data():small_.data();}
    const int* data()const{return n_>Capacity?large_.data():small_.data();}
    int* begin(){return data();}int* end(){return data()+n_;}
    const int* begin()const{return data();}const int* end()const{return data()+n_;}
    int& operator[](size_t i){return data()[i];}const int& operator[](size_t i)const{return data()[i];}
    int& back(){return data()[n_-1];}const int& back()const{return data()[n_-1];}
    void resize(size_t n){
        if(n>Capacity){
            if(n_<=Capacity){large_.resize(n);std::copy(small_.begin(),small_.begin()+n_,large_.begin());std::fill(large_.begin()+n_,large_.end(),0);}
            else large_.resize(n);
        }else{
            if(n_>Capacity)std::copy(large_.begin(),large_.begin()+std::min(n,n_),small_.begin());
            else if(n>n_)std::fill(small_.begin()+n_,small_.begin()+n,0);
        }
        n_=n;
    }
    void pop_back(){resize(n_-1);}void push_back(int x){resize(n_+1);back()=x;}
    void clear(){n_=0;}
};
