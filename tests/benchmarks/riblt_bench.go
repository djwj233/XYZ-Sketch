package main

import (
	"bufio"
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/dchest/siphash"
	"github.com/yangl1996/riblt"
)

type item uint64

func (t item) XOR(t2 item) item {
	return t ^ t2
}

func (t item) Hash() uint64 {
	buf := [8]byte{}
	binary.LittleEndian.PutUint64(buf[:], uint64(t))
	return siphash.Hash(123, 456, buf[:])
}

type resultRow struct {
	Algorithm          string  `json:"algorithm"`
	Variant            string  `json:"variant"`
	Implementation     string  `json:"implementation"`
	D                  int     `json:"d"`
	Trials             int     `json:"trials"`
	Successes          int     `json:"successes"`
	SuccessRate        float64 `json:"success_rate"`
	EncodeAvgS         float64 `json:"encode_avg_s"`
	DecodeAvgS         float64 `json:"decode_avg_s"`
	EncodeMedianS      float64 `json:"encode_median_s"`
	DecodeMedianS      float64 `json:"decode_median_s"`
	Bits               int     `json:"bits"`
	COverD             float64 `json:"C_over_d"`
	SymbolFactor       float64 `json:"symbol_factor"`
	SymbolsSent        int     `json:"symbols_sent"`
	MaxSymbols         int     `json:"max_symbols"`
	SymbolBits         int     `json:"symbol_bits"`
	FieldBits          int     `json:"field_bits"`
	CommunicationModel string  `json:"communication_model"`
	Seed               uint    `json:"seed"`
	CA                 int     `json:"ca"`
	CB                 int     `json:"cb"`
	Status             string  `json:"status"`
	UnavailableReason  string  `json:"unavailable_reason"`
	Error              string  `json:"error"`
}

type dataset struct {
	alice []item
	bob   []item
}

func loadDataset(path string) (dataset, error) {
	file, err := os.Open(path)
	if err != nil {
		return dataset{}, err
	}
	defer file.Close()

	var data dataset
	var current *[]item
	expected := -1
	seen := 0
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.Fields(line)
		if len(parts) == 2 && (parts[0] == "A" || parts[0] == "B") {
			if current != nil && expected >= 0 && seen != expected {
				return dataset{}, fmt.Errorf("dataset section length mismatch")
			}
			n, err := strconv.Atoi(parts[1])
			if err != nil {
				return dataset{}, err
			}
			expected = n
			seen = 0
			if parts[0] == "A" {
				data.alice = data.alice[:0]
				current = &data.alice
			} else {
				data.bob = data.bob[:0]
				current = &data.bob
			}
			continue
		}
		if current == nil {
			return dataset{}, fmt.Errorf("dataset value before section")
		}
		value, err := strconv.ParseUint(parts[0], 10, 64)
		if err != nil {
			return dataset{}, err
		}
		*current = append(*current, item(value))
		seen++
	}
	if err := scanner.Err(); err != nil {
		return dataset{}, err
	}
	if current != nil && expected >= 0 && seen != expected {
		return dataset{}, fmt.Errorf("dataset section length mismatch")
	}
	return data, nil
}

func setMap(values []item) map[item]struct{} {
	out := make(map[item]struct{}, len(values))
	for _, value := range values {
		out[value] = struct{}{}
	}
	return out
}

func difference(left, right []item) []item {
	rightSet := setMap(right)
	out := make([]item, 0)
	for _, value := range left {
		if _, ok := rightSet[value]; !ok {
			out = append(out, value)
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i] < out[j] })
	return out
}

func symbolsEqual(actual []riblt.HashedSymbol[item], expected []item) bool {
	values := make([]item, 0, len(actual))
	for _, symbol := range actual {
		values = append(values, symbol.Symbol)
	}
	sort.Slice(values, func(i, j int) bool { return values[i] < values[j] })
	if len(values) != len(expected) {
		return false
	}
	for i := range values {
		if values[i] != expected[i] {
			return false
		}
	}
	return true
}

func runRIBLT(data dataset, maxSymbols int) (success bool, symbolsSent int, encodeS float64, decodeS float64, errText string) {
	expectedRemote := difference(data.alice, data.bob)
	expectedLocal := difference(data.bob, data.alice)

	encodeStart := time.Now()
	enc := riblt.Encoder[item]{}
	for _, value := range data.alice {
		enc.AddSymbol(value)
	}
	dec := riblt.Decoder[item]{}
	for _, value := range data.bob {
		dec.AddSymbol(value)
	}
	encodeS = time.Since(encodeStart).Seconds()

	decodeStart := time.Now()
	for symbolsSent = 0; symbolsSent < maxSymbols; symbolsSent++ {
		symbol := enc.ProduceNextCodedSymbol()
		dec.AddCodedSymbol(symbol)
		dec.TryDecode()
		if dec.Decoded() {
			symbolsSent++
			break
		}
	}
	decodeS = time.Since(decodeStart).Seconds()

	if !dec.Decoded() {
		return false, symbolsSent, encodeS, decodeS, "decoder did not finish before max_symbols"
	}
	if !symbolsEqual(dec.Remote(), expectedRemote) || !symbolsEqual(dec.Local(), expectedLocal) {
		return false, symbolsSent, encodeS, decodeS, "decoded difference mismatch"
	}
	return true, symbolsSent, encodeS, decodeS, ""
}

func main() {
	d := flag.Int("d", -1, "symmetric difference")
	trials := flag.Int("trials", -1, "trial count")
	seed := flag.Uint("seed", 114514, "seed")
	ca := flag.Int("ca", 10000000, "Alice set size")
	cb := flag.Int("cb", 10000000, "Bob set size")
	symbolFactor := flag.Float64("symbol-factor", 1.5, "symbol factor")
	symbolBits := flag.Int("symbol-bits", 64, "symbol bits")
	fieldBits := flag.Int("field-bits", 30, "field bits")
	dataset := flag.String("dataset", "", "dataset path")
	format := flag.String("format", "jsonl", "output format")
	flag.Parse()

	if *d <= 0 || *trials <= 0 || *dataset == "" || *format != "jsonl" {
		fmt.Fprintln(os.Stderr, "invalid arguments")
		os.Exit(2)
	}
	data, err := loadDataset(*dataset)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	maxSymbols := int(math.Ceil(float64(*d) * *symbolFactor))
	if maxSymbols < 1 {
		maxSymbols = 1
	}
	success, symbolsSent, encodeS, decodeS, errText := runRIBLT(data, maxSymbols)
	status := "ok"
	if !success {
		status = "failed_decode"
	}

	row := resultRow{
		Algorithm:          "riblt",
		Variant:            fmt.Sprintf("symbol_factor=%g", *symbolFactor),
		Implementation:     "external/riblt",
		D:                  *d,
		Trials:             *trials,
		Successes:          map[bool]int{true: 1, false: 0}[success],
		SuccessRate:        map[bool]float64{true: 1.0, false: 0.0}[success],
		EncodeAvgS:         encodeS,
		DecodeAvgS:         decodeS,
		EncodeMedianS:      encodeS,
		DecodeMedianS:      decodeS,
		Bits:               symbolsSent * *symbolBits,
		COverD:             float64(symbolsSent**symbolBits) / (32.0 * float64(*d)),
		SymbolFactor:       *symbolFactor,
		SymbolsSent:        symbolsSent,
		MaxSymbols:         maxSymbols,
		SymbolBits:         *symbolBits,
		FieldBits:          *fieldBits,
		CommunicationModel: "rateless",
		Seed:               *seed,
		CA:                 *ca,
		CB:                 *cb,
		Status:             status,
		Error:              errText,
	}
	encoded, err := json.Marshal(row)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println(string(encoded))
}
