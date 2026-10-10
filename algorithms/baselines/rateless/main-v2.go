package main

import (
 "bytes"
 "crypto/sha256"
 "encoding/binary"
 "encoding/hex"
 "encoding/json"
 "fmt"
 "io"
 "os"
 "runtime"
 "sort"
 "strconv"
 "syscall"
 "time"
 "unsafe"
 "github.com/dchest/siphash"
 "github.com/yangl1996/riblt"
)

var key0,key1 uint64
type item uint64
func (v item) XOR(w item) item { return v^w }
func (v item) Hash() uint64 { var b [8]byte;binary.LittleEndian.PutUint64(b[:],uint64(v));return siphash.Hash(key0,key1,b[:]) }
type largeItem [32]byte
func (v largeItem) XOR(w largeItem) largeItem { for i:=range v {v[i]^=w[i]};return v }
func (v largeItem) Hash() uint64 { return siphash.Hash(key0,key1,v[:]) }

// Explicit experiment convention: floor(N*rho(i)) and ZigZag + unsigned LEB128.
// The paper specifies expectation residual and base-128 VLQ, not these details.
func expectation(n uint64,i int) int64 {return int64(2*n/uint64(i+2))}
func encodeCount(dst []byte,c int64,n uint64,i int) []byte {
 x:=c-expectation(n,i);u:=uint64(x)<<1 ^ uint64(x>>63);return binary.AppendUvarint(dst,u)
}
func decodeCount(b []byte,n uint64,i int)(int64,int,error) {
 u,l:=binary.Uvarint(b);if l<=0{return 0,0,fmt.Errorf("invalid VLQ")}
 x:=int64(u>>1)^-int64(u&1);return x+expectation(n,i),l,nil
}
func header(n uint64) []byte {b:=make([]byte,18);b[0]=1;b[1]=30;binary.LittleEndian.PutUint64(b[2:10],key0);binary.LittleEndian.PutUint64(b[10:18],key1);return binary.AppendUvarint(b,n)}
func parseHeader(b []byte)(uint64,error){if len(b)<19||b[0]!=1||b[1]!=30{return 0,fmt.Errorf("header")};if binary.LittleEndian.Uint64(b[2:10])!=key0||binary.LittleEndian.Uint64(b[10:18])!=key1{return 0,fmt.Errorf("keys")};n,l:=binary.Uvarint(b[18:]);if l<=0||18+l!=len(b){return 0,fmt.Errorf("N metadata")};return n,nil}
// Ordered byte frames: 30 meaningful symbol bits in a 32-bit slot (2 zero bits),
// full 64-bit checksum, followed by self-delimiting count VLQ; no symbol indices.
func frame(dst []byte,c riblt.CodedSymbol[item],n uint64,i int) []byte {
 dst=dst[:0];var b [12]byte;binary.LittleEndian.PutUint32(b[:4],uint32(c.Symbol));binary.LittleEndian.PutUint64(b[4:],c.Hash);dst=append(dst,b[:]...);return encodeCount(dst,c.Count,n,i)
}
func unframe(b []byte,n uint64,i int)(riblt.CodedSymbol[item],int,error){
 var c riblt.CodedSymbol[item];if len(b)<13{return c,0,fmt.Errorf("short frame")};v:=binary.LittleEndian.Uint32(b[:4]);if v>>30!=0{return c,0,fmt.Errorf("padding")};c.Symbol=item(v);c.Hash=binary.LittleEndian.Uint64(b[4:12]);x,l,e:=decodeCount(b[12:],n,i);if e!=nil||12+l!=len(b){return c,0,fmt.Errorf("count frame")};c.Count=x;return c,l,nil
}
func cpu() float64 { var ts syscall.Timespec;_,_,e:=syscall.RawSyscall(syscall.SYS_CLOCK_GETTIME,3,uintptr(unsafe.Pointer(&ts)),0);if e!=0{panic(e)};return float64(ts.Sec)+float64(ts.Nsec)/1e9 }
type dataset struct { D int; A,B,AO,BO []item; SHA string }
func readData(path string)(dataset,error){
 var d dataset;f,e:=os.Open(path);if e!=nil{return d,e};defer f.Close();h:=sha256.New();r:=io.TeeReader(f,h);b:=make([]byte,200);if _,e=io.ReadFull(r,b);e!=nil{return d,e};if string(b[:4])!="F2DS"||binary.BigEndian.Uint32(b[4:8])!=1||binary.BigEndian.Uint32(b[8:12])!=1{return d,fmt.Errorf("full F2DS required")};d.D=int(binary.BigEndian.Uint32(b[12:16]));vs:=[]*[]item{&d.A,&d.B,&d.AO,&d.BO}
 for j,p:=range vs {ln:=int(binary.BigEndian.Uint64(b[16+j*8:24+j*8]));raw:=make([]byte,ln*4);if _,e=io.ReadFull(r,raw);e!=nil{return d,e};digest:=sha256.Sum256(raw);if !bytes.Equal(digest[:],b[72+j*32:104+j*32]){return d,fmt.Errorf("vector hash %d",j)};*p=make([]item,ln);for i:=range *p{v:=binary.BigEndian.Uint32(raw[i*4:i*4+4]);if v>>30!=0{return d,fmt.Errorf("input range")};(*p)[i]=item(v)}}
 var extra [1]byte;if k,_:=r.Read(extra[:]);k!=0{return d,fmt.Errorf("trailing data")};d.SHA=hex.EncodeToString(h.Sum(nil));return d,nil
}
func equalItems(a,b []item)bool{if len(a)!=len(b){return false};sort.Slice(a,func(i,j int)bool{return a[i]<a[j]});b=append([]item(nil),b...);sort.Slice(b,func(i,j int)bool{return b[i]<b[j]});for i:=range a{if a[i]!=b[i]{return false}};return true}
type result struct {
 Status string `json:"status"`; D int `json:"d"`; Repetition int `json:"repetition"`; DatasetSHA string `json:"dataset_sha256"`
 Symbols int `json:"symbols"`; Bytes int `json:"bytes"`; SymbolBits int `json:"symbol_bits"`; HashBits int `json:"hash_bits"`; CountBytes int `json:"count_bytes"`; MetadataBytes int `json:"metadata_bytes"`; PaddingBits int `json:"padding_bits"`; AckBytes int `json:"ack_bytes"`
 MeanCountBytes float64 `json:"mean_count_bytes"`; SymbolsPerD float64 `json:"symbols_per_d"`; Ratio float64 `json:"ratio"`
 AliceIngest float64 `json:"alice_ingest_cpu_s"`; BobIngest float64 `json:"bob_ingest_cpu_s"`; Generate float64 `json:"alice_generate_cpu_s"`; Receive float64 `json:"bob_receive_cpu_s"`; WireEncode float64 `json:"wire_encode_cpu_s"`; WireDecode float64 `json:"wire_decode_cpu_s"`; Total float64 `json:"total_cpu_s"`; Wall float64 `json:"wall_s"`
 WireSHA string `json:"wire_sha256"`; Truth bool `json:"truth_verified"`; CountIdentical bool `json:"counts_identical"`; Accounting bool `json:"accounting_exact"`; Checkpoints []int `json:"incomplete_prefix_checkpoints"`
}
func measure(d dataset,reps,maxSymbols int,limit time.Duration)[]result{
 var enc riblt.Encoder[item];var dec riblt.Decoder[item];out:=[]result{}
 for rep:=0;rep<reps;rep++{enc.Reset();dec.Reset();r:=result{Status:"symbol_limit",D:d.D,Repetition:rep,DatasetSHA:d.SHA,CountIdentical:true};wall:=time.Now();whole:=cpu();t:=cpu();for _,v:=range d.A{enc.AddSymbol(v)};r.AliceIngest=cpu()-t;t=cpu();for _,v:=range d.B{dec.AddSymbol(v)};r.BobIngest=cpu()-t
  meta:=header(uint64(len(d.A)));n,e:=parseHeader(meta);if e!=nil{panic(e)};r.MetadataBytes=len(meta);r.Bytes=len(meta);wire:=sha256.New();wire.Write(meta);buf:=make([]byte,0,24)
  for i:=0;i<maxSymbols;i++{
   if time.Since(wall)>limit {r.Status="time_limit";break};t=cpu();c:=enc.ProduceNextCodedSymbol();r.Generate+=cpu()-t;t=cpu();buf=frame(buf,c,n,i);r.WireEncode+=cpu()-t
   t=cpu();received,l,err:=unframe(buf,n,i);r.WireDecode+=cpu()-t;if err!=nil{panic(err)};if received.Count!=c.Count||received.Hash!=c.Hash||received.Symbol!=c.Symbol{panic("wire roundtrip")};r.CountBytes+=l;r.Bytes+=len(buf);wire.Write(buf);r.Symbols++
   t=cpu();dec.AddCodedSymbol(received);dec.TryDecode();r.Receive+=cpu()-t;if dec.Decoded(){r.Status="success";r.AckBytes=1;r.Bytes++;wire.Write([]byte{1});break};if r.Symbols&(r.Symbols-1)==0{r.Checkpoints=append(r.Checkpoints,r.Symbols)}
  }
  r.Total=cpu()-whole;r.Wall=time.Since(wall).Seconds();r.SymbolBits=r.Symbols*30;r.HashBits=r.Symbols*64;r.PaddingBits=r.Symbols*2;r.MeanCountBytes=float64(r.CountBytes)/float64(r.Symbols);if d.D>0{r.SymbolsPerD=float64(r.Symbols)/float64(d.D);r.Ratio=float64(r.Bytes*8)/float64(30*d.D)};r.Accounting=r.Bytes*8==r.SymbolBits+r.HashBits+r.CountBytes*8+r.MetadataBytes*8+r.PaddingBits+r.AckBytes*8;if !r.Accounting{panic("accounting")};r.WireSHA=hex.EncodeToString(wire.Sum(nil))
  // Decoder decides completion first. Truth and sorting are outside every timer.
  if r.Status=="success" {remote:=dec.Remote();local:=dec.Local();aa:=make([]item,len(remote));bb:=make([]item,len(local));for i,v:=range remote{aa[i]=v.Symbol};for i,v:=range local{bb[i]=v.Symbol};r.Truth=equalItems(aa,d.AO)&&equalItems(bb,d.BO);if !r.Truth{r.Status="wrong_recovery"}}
  out=append(out,r)
 };return out
}
func printJSON(x any){e:=json.NewEncoder(os.Stdout);if err:=e.Encode(x);err!=nil{panic(err)}}
func main(){runtime.GOMAXPROCS(1);runtime.LockOSThread();if len(os.Args)<2{panic("run|representative")};if os.Args[1]=="representative"{representative();return};if len(os.Args)!=9{panic("run dataset k0 k1 reps max_symbols wall_limit_seconds expected_sha")};key0,_=strconv.ParseUint(os.Args[3],10,64);key1,_=strconv.ParseUint(os.Args[4],10,64);reps,_:=strconv.Atoi(os.Args[5]);max,_:=strconv.Atoi(os.Args[6]);secs,_:=strconv.Atoi(os.Args[7]);d,e:=readData(os.Args[2]);if e!=nil{panic(e)};if d.SHA!=os.Args[8]{panic("dataset hash")};printJSON(measure(d,reps,max,time.Duration(secs)*time.Second))}
