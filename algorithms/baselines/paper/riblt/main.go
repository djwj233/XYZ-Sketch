package main

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"fmt"
	"os"
	"runtime"
	"sort"
	"strconv"
	"syscall"
	"unsafe"

	"github.com/dchest/siphash"
	"github.com/yangl1996/riblt"
)

const protocol = "figure2-engine-v2"
const hashBits = 49
const hashMask = uint64(1<<hashBits) - 1

var sipK0 uint64
var sipK1 uint64

type item uint32

func (value item) XOR(other item) item { return value ^ other }
func (value item) Hash() uint64 {
	var encoded [4]byte
	binary.BigEndian.PutUint32(encoded[:], uint32(value))
	return siphash.Hash(sipK0, sipK1, encoded[:]) & hashMask
}

type dataset struct {
	full               bool
	d                  uint32
	alice, bob         []uint32
	aliceOnly, bobOnly []uint32
	hashes             [4]string
}

func readU32(data []byte, offset *int) (uint32, error) {
	if *offset+4 > len(data) {
		return 0, fmt.Errorf("truncated u32")
	}
	value := binary.BigEndian.Uint32(data[*offset : *offset+4])
	*offset += 4
	return value, nil
}

func readU64(data []byte, offset *int) (uint64, error) {
	if *offset+8 > len(data) {
		return 0, fmt.Errorf("truncated u64")
	}
	value := binary.BigEndian.Uint64(data[*offset : *offset+8])
	*offset += 8
	return value, nil
}

func vectorHash(values []uint32) string {
	hash := sha256.New()
	var encoded [4]byte
	for _, value := range values {
		binary.BigEndian.PutUint32(encoded[:], value)
		hash.Write(encoded[:])
	}
	return hex.EncodeToString(hash.Sum(nil))
}

func readDataset(path string) (dataset, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return dataset{}, err
	}
	if len(data) < 200 || string(data[:4]) != "F2DS" {
		return dataset{}, fmt.Errorf("invalid dataset")
	}
	offset := 4
	version, _ := readU32(data, &offset)
	flags, _ := readU32(data, &offset)
	difference, _ := readU32(data, &offset)
	if version != 1 {
		return dataset{}, fmt.Errorf("dataset version")
	}
	var sizes [4]uint64
	for index := range sizes {
		sizes[index], err = readU64(data, &offset)
		if err != nil {
			return dataset{}, err
		}
	}
	for index := 0; index < 3; index++ {
		if _, err = readU64(data, &offset); err != nil {
			return dataset{}, err
		}
	}
	var hashes [4]string
	for index := range hashes {
		if offset+32 > len(data) {
			return dataset{}, fmt.Errorf("truncated hashes")
		}
		hashes[index] = hex.EncodeToString(data[offset : offset+32])
		offset += 32
	}
	arrays := make([][]uint32, 4)
	for arrayIndex, size := range sizes {
		if size > uint64((len(data)-offset)/4) {
			return dataset{}, fmt.Errorf("array overflow")
		}
		arrays[arrayIndex] = make([]uint32, int(size))
		for index := range arrays[arrayIndex] {
			arrays[arrayIndex][index], err = readU32(data, &offset)
			if err != nil {
				return dataset{}, err
			}
		}
		if vectorHash(arrays[arrayIndex]) != hashes[arrayIndex] {
			return dataset{}, fmt.Errorf("array hash")
		}
	}
	if offset != len(data) {
		return dataset{}, fmt.Errorf("trailing dataset bytes")
	}
	return dataset{flags == 1, difference, arrays[0], arrays[1], arrays[2], arrays[3], hashes}, nil
}

func threadCPU() float64 {
	var ts syscall.Timespec
	_, _, errno := syscall.Syscall(syscall.SYS_CLOCK_GETTIME, 3, uintptr(unsafe.Pointer(&ts)), 0)
	if errno != 0 {
		panic(errno)
	}
	return float64(ts.Sec) + float64(ts.Nsec)*1e-9
}

type bitWriter struct {
	bytes []byte
	bits  int
}

func (writer *bitWriter) put(value uint64, width int) {
	for shift := width - 1; shift >= 0; shift-- {
		if writer.bits%8 == 0 {
			writer.bytes = append(writer.bytes, 0)
		}
		if (value>>shift)&1 != 0 {
			writer.bytes[len(writer.bytes)-1] |= 1 << (7 - writer.bits%8)
		}
		writer.bits++
	}
}

type bitReader struct {
	bytes []byte
	bits  int
}

func (reader *bitReader) get(width int) (uint64, error) {
	if reader.bits+width > len(reader.bytes)*8 {
		return 0, fmt.Errorf("truncated bits")
	}
	var value uint64
	for index := 0; index < width; index++ {
		value = (value << 1) | uint64((reader.bytes[reader.bits/8]>>(7-reader.bits%8))&1)
		reader.bits++
	}
	return value, nil
}

func pack(symbols []riblt.CodedSymbol[item]) []byte {
	writer := bitWriter{}
	for _, symbol := range symbols {
		writer.put(uint64(symbol.Symbol), 30)
		writer.put(symbol.Hash, hashBits)
		writer.put(uint64(symbol.Count)&((1<<25)-1), 25)
	}
	return writer.bytes
}

func unpack(data []byte, count int) ([]riblt.CodedSymbol[item], error) {
	reader := bitReader{bytes: data}
	result := make([]riblt.CodedSymbol[item], count)
	for index := range result {
		symbol, err := reader.get(30)
		if err != nil {
			return nil, err
		}
		hash, err := reader.get(hashBits)
		if err != nil {
			return nil, err
		}
		encodedCount, err := reader.get(25)
		if err != nil {
			return nil, err
		}
		countValue := int64(encodedCount)
		if encodedCount&(1<<24) != 0 {
			countValue -= 1 << 25
		}
		result[index] = riblt.CodedSymbol[item]{
			HashedSymbol: riblt.HashedSymbol[item]{Symbol: item(symbol), Hash: hash}, Count: countValue,
		}
	}
	return result, nil
}

func parseState(state []byte, capValue int) ([]riblt.CodedSymbol[item], error) {
	logical := capValue * 104
	stateBytes := (logical + 7) / 8
	if len(state) != stateBytes {
		return nil, fmt.Errorf("RIBLT state length")
	}
	if logical%8 != 0 && stateBytes > 0 {
		unused := 8 - logical%8
		mask := byte((1 << unused) - 1)
		if state[len(state)-1]&mask != 0 {
			return nil, fmt.Errorf("RIBLT state padding bits")
		}
	}
	return unpack(state, capValue)
}

type result struct {
	success                                            bool
	failure                                            string
	logical, state, control, total                     uint64
	updateAlice, updateBob, sender, transfer, receiver float64
	aliceHash, bobHash, residualHash                   string
	required                                           int64
}

func canonical(got []riblt.HashedSymbol[item]) ([]uint32, bool) {
	values := make([]uint32, len(got))
	for i, v := range got {
		values[i] = uint32(v.Symbol)
	}
	sort.Slice(values, func(i, j int) bool { return values[i] < values[j] })
	for i, value := range values {
		if value == 0 || value >= 998244353 || (i > 0 && values[i-1] == value) {
			return values, false
		}
	}
	return values, true
}

func disjoint(left, right []uint32) bool {
	i, j := 0, 0
	for i < len(left) && j < len(right) {
		if left[i] == right[j] {
			return false
		}
		if left[i] < right[j] {
			i++
		} else {
			j++
		}
	}
	return true
}

func compareAfterTimer(got, expected []uint32, timerStopped bool) bool {
	if !timerStopped {
		panic("ground truth comparison is inside receiver timer")
	}
	if len(got) != len(expected) {
		return false
	}
	for i := range got {
		if got[i] != expected[i] {
			return false
		}
	}
	return true
}

func exact(got []riblt.HashedSymbol[item], expected []uint32) bool {
	values, valid := canonical(got)
	return valid && compareAfterTimer(values, expected, true)
}

func run(data dataset, cap int) (result, error) {
	var out result
	out.failure = "process_error"
	out.required = -1
	alice := make(riblt.Sketch[item], cap)
	begin := threadCPU()
	for _, value := range data.alice {
		alice.AddSymbol(item(value))
	}
	out.updateAlice = threadCPU() - begin
	bob := make(riblt.Sketch[item], cap)
	begin = threadCPU()
	for _, value := range data.bob {
		bob.AddSymbol(item(value))
	}
	out.updateBob = threadCPU() - begin
	begin = threadCPU()
	message := pack([]riblt.CodedSymbol[item](alice))
	out.sender = threadCPU() - begin
	begin = threadCPU()
	received := append([]byte(nil), message...)
	out.transfer = threadCPU() - begin
	begin = threadCPU()
	parsed, err := parseState(received, cap)
	if err != nil {
		return out, err
	}
	residual := riblt.Sketch[item](parsed)
	residual.Subtract(bob)
	remote, local, decoded := residual.Decode()
	aliceOnly, aliceValid := canonical(remote)
	bobOnly, bobValid := canonical(local)
	shapeValid := aliceValid && bobValid && disjoint(aliceOnly, bobOnly)
	out.receiver = threadCPU() - begin
	if decoded && shapeValid {
		out.success = compareAfterTimer(aliceOnly, data.aliceOnly, true) && compareAfterTimer(bobOnly, data.bobOnly, true)
		if out.success {
			out.failure = "success"
		} else {
			out.failure = "wrong_output"
		}
	} else if decoded {
		out.failure = "wrong_output"
	} else {
		out.failure = "decode_failed"
	}
	out.aliceHash = vectorHash(aliceOnly)
	out.bobHash = vectorHash(bobOnly)
	hash := sha256.Sum256(pack([]riblt.CodedSymbol[item](residual)))
	out.residualHash = hex.EncodeToString(hash[:])
	out.logical = uint64(cap * 104)
	out.state = uint64((cap*104 + 7) / 8 * 8)
	out.control = 0
	out.total = out.state
	if uint64(len(message))*8 != out.total {
		return out, fmt.Errorf("RIBLT accounting mismatch")
	}
	return out, nil
}

func discover(data dataset, maximum int) (result, error) {
	var out result
	out.failure = "resource_out_of_grid"
	out.required = int64(maximum + 1)
	var encoder riblt.Encoder[item]
	for _, v := range data.alice {
		encoder.AddSymbol(item(v))
	}
	var decoder riblt.Decoder[item]
	for _, v := range data.bob {
		decoder.AddSymbol(item(v))
	}
	for index := 1; index <= maximum; index++ {
		decoder.AddCodedSymbol(encoder.ProduceNextCodedSymbol())
		decoder.TryDecode()
		if decoder.Decoded() && exact(decoder.Remote(), data.aliceOnly) && exact(decoder.Local(), data.bobOnly) {
			out.success = true
			out.failure = "success"
			out.required = int64(index)
			break
		}
	}
	return out, nil
}

func printResult(out result) {
	fmt.Printf("%s\triblt\t%d\t%s\t%d\t%d\t%d\t%d\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g\t%s\t%s\t%s\t%d\n", protocol, map[bool]int{true: 1}[out.success], out.failure, out.logical, out.state, out.control, out.total, out.updateAlice, out.updateBob, out.sender, out.transfer, out.receiver, out.aliceHash, out.bobHash, out.residualHash, out.required)
}

func golden() dataset {
	return dataset{full: true, d: 2, alice: []uint32{1, 2}, bob: []uint32{2, 3}, aliceOnly: []uint32{1}, bobOnly: []uint32{3}}
}

func encoderSketchEquivalence() (bool, int) {
	keys := [][2]uint64{{123, 456}, {0, 0}, {0x0123456789abcdef, 0xfedcba9876543210}}
	caps := []int{1, 2, 3, 10, 100, 300}
	values := make([]item, 257)
	for index := range values {
		values[index] = item((uint64(index+1)*2654435761)%998244352 + 1)
	}
	cases := 0
	for _, key := range keys {
		sipK0, sipK1 = key[0], key[1]
		for _, capValue := range caps {
			var encoder riblt.Encoder[item]
			sketch := make(riblt.Sketch[item], capValue)
			for _, value := range values {
				encoder.AddSymbol(value)
				sketch.AddSymbol(value)
			}
			for index := range sketch {
				if sketch[index] != encoder.ProduceNextCodedSymbol() {
					return false, cases
				}
			}
			cases++
		}
	}
	return true, cases
}

func main() {
	runtime.LockOSThread()
	if len(os.Args) == 2 && os.Args[1] == "--self-test" {
		equivalent, equivalenceCases := encoderSketchEquivalence()
		sipK0 = 123
		sipK1 = 456
		out, err := run(golden(), 3)
		sketch := make(riblt.Sketch[item], 3)
		for _, value := range golden().alice {
			sketch.AddSymbol(item(value))
		}
		message := pack([]riblt.CodedSymbol[item](sketch))
		_, malformedErr := parseState(message[:len(message)-1], 3)
		malformedRejected := malformedErr != nil
		passed := err == nil && out.success && out.total == 312 && out.state == 312 && out.control == 0 && equivalent && equivalenceCases == 18 && malformedRejected
		fmt.Printf("{\"protocol\":\"%s\",\"algorithm\":\"riblt\",\"golden_total_bits\":%d,\"encoder_sketch_equivalent\":%v,\"encoder_sketch_equivalence_cases\":%d,\"malformed_state_rejected\":%v,\"passed\":%v}\n", protocol, out.total, equivalent, equivalenceCases, malformedRejected, passed)
		if !passed {
			os.Exit(2)
		}
		return
	}
	if len(os.Args) != 7 || (os.Args[1] != "--run" && os.Args[1] != "--discover") {
		fmt.Fprintln(os.Stderr, "usage: engine --run|--discover DATASET cap k0 k1")
		os.Exit(1)
	}
	data, err := readDataset(os.Args[2])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	capValue, err := strconv.Atoi(os.Args[3])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	sipK0, err = strconv.ParseUint(os.Args[4], 10, 64)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	sipK1, err = strconv.ParseUint(os.Args[5], 10, 64)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	_ = os.Args[6] // reserved profile-seed binding, recorded by the Python runner.
	var out result
	if os.Args[1] == "--run" {
		out, err = run(data, capValue)
	} else {
		out, err = discover(data, capValue)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	printResult(out)
}
