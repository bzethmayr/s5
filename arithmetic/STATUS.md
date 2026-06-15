# Arithmetic Status

## Pipeline
```
init.s5 → succ.s5 → pred.s5 → pred1.s5 → demo.s5
```

All 24 tests pass (`arithmetic/test_arithmetic.py`).

---

## Components

| File | Slot | Purpose |
|------|------|---------|
| `init.s5` | — | Bootstrap: grow U to 32, set ZERO, ONE, COUNTER (U[2]=32) |
| `succ.s5` | U[6] | 3 subroutines: NORM_SUCC, UGROWTH, NORM |
| `pred.s5` | U[7] | Search-based PRED_MAIN + helpers (scratch in U[8], initialized per call) |
| `pred1.s5` | U[12] build / U[16] data | Builds LUT in U[16] for all 0..COUNTER-1 via PRED_MAIN |
| `demo.s5` | U[13] | Reads Q from stdin, outputs pred(Q) via PRED_MAIN |

### Slot Map
```
U[0]  ZERO          U[1]  ONE            U[2]  COUNTER (=32)
U[3]  IN_A          U[4]  IN_B           U[5]  OUT
U[6]  SUCC subrs    U[7]  PRED subrs     U[8]  pred scratch
U[9]  —             U[10] —              U[11] V (build loop)
U[12] pred1 build   U[13] scratch        U[14] bound
U[15] ∅ source      U[16] LUT data       U[17] —
```

---

## Key Experimental Results

### 1. NORM_SUCC buffer conflict → disproven
**Hypothesis**: NORM_SUCC (U[6][0]) uses IO(1) (fd 0 internal buffer), and this conflicts with remaining stdin data meant for demo.s5.

**Result**: No conflict. IO(1) with `has_depth=True` uses the IOHandler's **separate internal byte buffer**, not `sys.stdin`. NORM_SUCC's write-then-read cycle is self-contained within the IOHandler buffer; `sys.stdin` is untouched. The original pipeline (`init + succ + pred + pred1 + demo`) works correctly with input like `3\n5\n`.

**`norm_succ_fd1` variant (U[6][3], IO(2)/fd 1)**: Added as a safety measure but is unnecessary. Not used.

### 2. Pure-unary pred(V) = V[0] → disproven
**Hypothesis**: In unary encoding, subset-select(0) on value V gives V−1, making pred(V) a cheap O(1) operation.

**Result**: Fails because s5's `set_value` encoding is **mixed unary/binary**, not pure unary:
```
set_value encoding:
  ∅ (empty set) → +1    (unary digit)
  non-∅          → ×2    (binary digit)
```
In this encoding, `subset(0)` on any V≥1 always returns `∅` (the unary digit), which has set_value 0. `set_value(V[0]) = 0` for all V≥1, NOT pred(V).

Values in canonical form:
```
int_to_s5set(0) = {}                              value 0
int_to_s5set(1) = {{}}                            value 1
int_to_s5set(2) = {{}, {{}}}                      value 2
int_to_s5set(3) = {{}, {{}}, {}}                  value 3
int_to_s5set(4) = {{}, {{}}, {{}}}                value 4
```

**Consequence**: There is no cheap unary decrement. Each increment/decrement requires an IO round-trip (`NORM_SUCC`) for normalization. A LUT-based runtime lookup would need `NORM_SUCC` per iteration — no faster than the existing search-based PRED_MAIN.

### 3. LUT build correctness → confirmed
- `pred1.s5` reads COUNTER from U[2] (not stdin)
- Calls PRED_MAIN for each V in 0..COUNTER-1 (32 values)
- Stores results in U[16] as a pure data set (no subroutines)
- All 32 entries verified correct: `pred(V) = max(0, V-1)`

### 4. LUT reusability → confirmed
- U[16] is a clean S5Set of 32 elements, copyable via `union_(dest, U[16], dest)`
- Compile-time lookup via `SUBSET_SELECT(V)` on U[16] gives pred(V) for known V
- Runtime lookup where Q varies still requires PRED_MAIN (no fast decrement exists)
- PRED_MAIN operates independently; it does not read or modify U[16]

---

## What's Left

- **Runtime O(1) pred lookup**: Requires a fast decrement mechanism. Not possible with the current mixed encoding without IO per iteration. Possible future directions: S5B-based code generation, custom IO normalization, or a different encoding strategy.
- **demo.s5**: Still calls PRED_MAIN (U[7][0]) for runtime Q — no change needed.
- **`norm_succ_fd1`**: Can be removed from `_gen_pred1.py` — dead code.
