# Hash input representation and placement

The old formal adapter's `item.Hash()` encodes its uint32 item as **four big-endian bytes**, computes SipHash with the trial's key pair, and masks the result to 49 bits. The fixed-prefix/min-offset supplement preserves this same policy. It is not a default from the official library.

The current reproduction instead follows the official integer example: zero-extend the 30-bit input value into uint64, encode it as **eight little-endian bytes**, and retain the **full 64-bit SipHash result**. The formal trial's two public key values are preserved. The official generic library does not prescribe one universal `Hash()` function; we deliberately use the representation in its integer example. Representative 256-bit tests hash all 32 symbol bytes, with full SipHash64.

Both the byte representation and the 49-to-64-bit restoration change the hash values. Because `encoder.go:addHashedSymbol` initializes `randomMapping` with exactly that hash, both changes also change placement. The full new protocol therefore runs again on every original input. Neither the old cap nor its old measured time is reused as a new result.

`comparison.json` separates the **direct transmitted hash-width cost** (+15 bits per newly transmitted symbol) from the **combined prefix/placement change**. Its algebra is exact, but the latter term is not an isolated causal estimate of restoring the mask or of adopting success-based stopping. No such isolated experiment is claimed.

The symbol's internal uint64 representation does not imply an eight-byte wire symbol in the common experiment. The wire has a four-byte slot holding 30 meaningful bits and two padding bits; the checksum field is eight bytes. Every padding bit is counted, independently of the hash input byte representation.
