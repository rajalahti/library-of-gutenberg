# The Babel Cipher — A Line-Level Feistel Permutation

## Overview

The Library of Babel requires a bijective mapping between **addresses** (where a line lives in the library) and **content** (the 80-character text on that line). Every possible 80-character string must appear exactly once, and every address must produce exactly one string. The mapping must be deterministic, reversible, and fast.

This is accomplished with an 8-round Feistel cipher operating over the space of 29^80 possible lines.

## Prior Art

The Feistel cipher is a well-established cryptographic construction, introduced by Horst Feistel at IBM in the early 1970s and famously used in DES. The technique of using a Feistel network as a format-preserving permutation over an arbitrary domain was formalized by Black and Rogaway (2002).

Jonathan Basile's [libraryofbabel.info](https://libraryofbabel.info) is the landmark digital Library of Babel. His algorithm uses a different technique: a Linear Congruential Generator (LCG) with modular multiplicative inverses and additional bit-shifting for pseudorandomness — not a Feistel cipher. Both approaches solve the same core problem (a reversible bijective mapping between addresses and content) but through different mathematical constructions.

This implementation uses a Feistel network rather than an LCG, operating at line-level (29^80) rather than page-level granularity. The underlying idea — using a bijective cipher to make a complete, navigable library — is the same.

## The Address Space

The library is structured hierarchically:

```
Hexagonal Room → Wall (4) → Shelf (5) → Volume (32) → Page (410) → Line (40)
```

Each line's address is a single BigInt:

```
address = hexId × LINES_PER_HEX
        + wall × LINES_PER_WALL
        + shelf × LINES_PER_SHELF
        + volume × LINES_PER_VOL
        + page × LINES_PER_PAGE
        + line
```

Where `LINES_PER_HEX = 4 × 5 × 32 × 410 × 40 = 10,496,000`.

The content space uses 29 symbols: `' ,.abcdefghijklmnopqrstuvwxyz'` (space, comma, period, then a–z). An 80-character line is a number in base-29 ranging from 0 to 29^80 − 1, which is approximately 10^117 — a 117-digit number, or about 390 bits.

## The Feistel Structure

A Feistel cipher splits the input into two halves and applies rounds of mixing:

```
HALF = 29^40  (the split point, ~58 digits)
TOTAL = 29^80 = HALF × HALF

encrypt(input):
    left  = input / HALF      (upper half)
    right = input % HALF      (lower half)

    for round i = 0 to 7:
        f = roundFunction(right, KEYS[i])
        newLeft  = right
        newRight = (left + f) mod HALF
        left = newLeft
        right = newRight

    return left × HALF + right
```

Decryption reverses the rounds:

```
decrypt(input):
    left  = input / HALF
    right = input % HALF

    for round i = 7 down to 0:
        f = roundFunction(left, KEYS[i])
        newLeft  = (right − f) mod HALF
        newRight = left
        left = newLeft
        right = newRight

    return left × HALF + right
```

The Feistel structure guarantees bijectivity: every input maps to a unique output, regardless of the round function used. This is the key insight — we get a permutation of the entire 29^80 space "for free."

## The Round Function

Each round applies a quadratic polynomial modulo HALF:

```
roundFunction(value, key) = (key.a × value² + key.b × value + key.c) mod HALF
```

The quadratic polynomial provides strong mixing: it's nonlinear (unlike a linear function, which would produce exploitable patterns), yet fast to compute with BigInt arithmetic. Each round uses different coefficients (a, b, c), derived from the round keys.

## Key Derivation

The 8 round keys are derived from digits of mathematical constants, ensuring reproducibility without randomness:

```
MASTER_SEEDS = [
    314159265358979323846264338327950288419    (π)
    271828182845904523536028747135266249775    (e)
    161803398874989484820458683436563811772    (φ, golden ratio)
    141421356237309504880168872420969807856    (√2)
    173205080756887729352744634150587236694    (√3)
    223606797749978969640917366873127623544    (√5)
    244948974278317809819728407470589139196    (√6)
    264575131106459059050161575363926042571    (√7)
]
```

Each seed generates three sub-keys via multiplication with large primes (Knuth's constants):

```
key.a = (seed × 2654435761) mod HALF
key.b = (seed × 2246822519) mod HALF
key.c = (seed × 3266489917) mod HALF
```

## Forward Operation: Address → Content

Given library coordinates (hexagon, wall, shelf, volume, page, line):

1. Compute the line address as a BigInt
2. Apply `encrypt(address)` → content number
3. Convert content number to base-29 → 80-character string

```
"Address 0" → encrypt → some 117-digit number → "qmx.rvtb kznpoa,w..."
```

## Reverse Operation: Search Text → Address

Given any 80-character text:

1. Pad/truncate to 80 characters, normalize to allowed symbols
2. Convert to base-29 BigInt → content number
3. Apply `decrypt(contentNumber)` → address
4. Decompose address into (hexagon, wall, shelf, volume, page, line)

```
"hello world" (padded to 80 chars) → base-29 number → decrypt → address → Hex 7a3f..., Wall 2, Shelf 4, Vol 17, Page 233, Line 12
```

Navigating to those coordinates and reading that line will produce exactly "hello world" followed by spaces.

## Why This Works

1. **Bijectivity**: The Feistel structure guarantees a 1-to-1 mapping regardless of the round function. No two addresses produce the same content, and no content appears at two addresses.

2. **Reversibility**: Decryption is the encrypt rounds run backwards with left/right swapped. No information is lost.

3. **Determinism**: Fixed keys derived from mathematical constants mean the same address always produces the same content, across all browsers and sessions.

4. **Completeness**: Since the cipher is a permutation of {0, 1, ..., 29^80 − 1}, every possible 80-character string exists at exactly one address. The library truly contains everything.

5. **Pseudorandomness**: 8 rounds of quadratic mixing produce output that appears random — most pages look like gibberish, exactly as Borges described.

## Performance

BigInt arithmetic on ~58-digit numbers (HALF ≈ 10^58) is fast in modern JavaScript engines:

- Single line generation: ~0.05ms
- Full page (40 lines): ~2ms
- This is fast enough for real-time page rendering without a Web Worker

## Comparison to Page-Level Approach

An alternative design would operate on entire pages (3,200 characters = 29^3200 ≈ 10^4677). This would require BigInt arithmetic on ~15,500-bit numbers, making each multiplication take hundreds of milliseconds. The line-level approach (29^80, ~390 bits) is orders of magnitude faster while still providing the core Library of Babel properties: completeness, determinism, and reversibility.

The trade-off: lines within the same page are independently generated, so there's no page-level coherence (a meaningful line won't be followed by a continuation of the same thought). This actually matches Borges's description — coherent passages are vanishingly rare miracles in the library.
