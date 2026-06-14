# Arithmetic System Plan

## Slot Allocation

C = working cache / temporary accumulator

| Slot | Name     | Contents                    | Notes                                    |
|------|----------|-----------------------------|------------------------------------------|
| U[0] | ZERO     | `∅` — value 0              | Empty set; ZERO ∪ ONE = {∅} = unary(1)   |
| U[1] | ONE      | `{∅}` — value 1            | Building block for unary growth          |
| U[2] | COUNTER  | `int_to_s5set(N)`          | Universe size after growth (32)          |
| U[3] | IN_A     | scratch / input A          | Used by succ/pred as input               |
| U[4] | IN_B     | scratch                    | Used by pred as IN_A save                |
| U[5] | OUT      | output register            | Result from succ/pred calls              |
| U[6] | SUCC     | successor structure        | [0]=NORM_SUCC, [1]=UGROWTH               |
| U[7] | PRED     | predecessor structure      | [0]=PRED_MAIN, [1]=PRED_ADVANCE, [2]=PRED_STEP |

Slots 3–5, 8 initially hold `∅` from the growth phase.

---

## init.s5 — Bootstrap (9 instrs)

Goal: grow U to 32, install ZERO (=∅), ONE, COUNTER.

### Order

1. **Save ONE before growth**: `C = U ∩ U` → preserves `{∅}`.
2. **Grow U**: self-union ×5 (list-concat semantics: 1→2→4→8→16→32).
3. **Write COUNTER**: `U ∩ U → IO'1` writes `set_value(U)=32` to fd 1 buffer (also prints to stdout).
4. **Read COUNTER**: `IO'1 ∪ U[4] → U[2]` reads 32 from fd 1 buffer into U[2].
5. **ZERO**: U[0] is already `∅` after growth — no change needed.
6. **ONE**: `C ∩ C → U[1]` copies `{∅}` to U[1].

> **ZERO=∅ rationale**: ZERO must be `∅` (empty set) so that `ZERO ∪ ONE = {∅}` (unary value 1).
> A non-empty ZERO like `{{∅}}` would cause `ZERO ∪ ONE = {∅, {∅}}` (unary value 2),
> breaking the successor function.

```

---

## succ.s5 — Successor function under U[6]

### Strategy

U[6] holds a structure whose elements implement successor variants. Accessed via `C = U[6]; C = C[N]`.

Challenges:
- Pure-unary succ (all-`∅` representation) works by appending `∅`, but we need a source of `∅` elements.
- Mixed-unary succ requires I/O normalization unless we can manipulate the encoding directly.

Approaches:

**1. Unary succ via ∅ source** — after init, slots U[3..7] are `∅`. Read one, union with target, store result. This works as long as the slot hasn't been overwritten.

**2. Normalized succ via I/O buffer** — append ONE (×2), then read/write through fd buffer to canonicalize. The buffer round-trip acts as `int_to_s5set(set_value(x))`, converting any non-canonical form to canonical.

**3. LUT-based succ** — precompute `int_to_s5set(1)` through `int_to_s5set(N)` and store as elements of U[6]. Subset-select yields the successor directly.

### Elements

U[6] stores subroutines as elements, accessed via `C = U[6]; C = C[N]`, then called with `Set Sets'`.

| Slot | Name | Body | Effect |
|------|------|------|--------|
| U[6][0] | NORM_SUCC | `OUT = normalize(IN_A ∪ ONE)` | Canonical successor via fd 0 round-trip |
| U[6][1] | UGROWTH | `U = U ∪ ONE; COUNTER = normalize(COUNTER + 1)` | Append ∅ to U, update ∅-count tracker |

Calling convention:
- Before: `IN_A = input_value` (if needed), `C = U[6]; C = C[N]`, `Set Sets'`
- After: result in `OUT` (NORM_SUCC) or `U` grown + `COUNTER` updated (UGROWTH)

### pcode (current implementation)

```
-- U[6][0] = NORM_SUCC: OUT = normalize(IN_A ∪ ONE)
Sets' Sets'
    C = IN_A ∪ ONE                   -- unary increment
    set_value(C) → fd0               -- normalize via I/O
    C = C \ C                        -- zero C (∅ source for read)
    fd0 → C                          -- canonical form
    C ∩ C → OUT                      -- copy to output
Sets'

-- store in U[6]
U[6] = U[6] ∪ {C}

-- U[6][1] = UGROWTH: U = U ∪ ONE; COUNTER = normalize(COUNTER + 1)
Sets' Sets'
    U = U ∪ ONE                      -- append ∅ to universe
    C = COUNTER ∪ ONE                -- increment ∅-count
    set_value(C) → fd0               -- normalize
    C = C \ C                        -- zero C
    fd0 → C                          -- canonical form
    C ∩ C → COUNTER                  -- update tracker
Sets'

-- append to U[6]
U[6] = U[6] ∪ {C}
```

> **Bufsize note**: each fd 0 round-trip needs `--bufsize` ≥ `len(str(N)) + 1` bytes
> (largest value N plus newline). `--bufsize 64` is a safe practical default.

---

## pred.s5 — Predecessor function under U[7]

### Slot usage during pred init (U[3..5] scratch)

| Slot | Alias    | Use during pred init                       | After init    |
|------|----------|--------------------------------------------|---------------|
| U[3] | VIRT_A   | Scratch for building pred structure         | Scratch (may be clobbered by pred callers) |
| U[4] | VIRT_B   | Scratch for building pred structure         | Scratch       |
| U[5] | VIRT_D   | Scratch for building pred structure         | Scratch       |

### Pred entry point: U[7][0]

The predecessor function is stored as a subroutine under `U[7][0]`. Called via:

```
C = U[7]         -- load PRED structure
C = C[0]         -- select pred subroutine
Set Sets'        -- invoke it
```

Internally it uses `U[7][1..]` for any helper subroutines (equality test, succ call, loop body).

### Strategy

Predecessor is harder than successor because removing elements changes the encoding in non-trivial ways.

Approaches:

**1. I/O normalization** — decrement via I/O: write value, subtract in integer domain, read back. Requires buffer support.

**2. Search-based** — iterate counter from 0 upward, comparing each value against input via equality test, stop when match found. The predecessor is the previous iteration's value. Very expensive but correct.

**3. LUT-based pred** — for small values, precompute and look up.

### pcode (search-based variant)

```
-- U[7][0] = pred search
-- Given value V in IN_A (U[3]):
--   test = U[0]          (ZERO, value 0)
--   prev = U[0]          (ZERO)
--   while test ≠ V:
--     prev = test
--     test = succ(test)   (call U[6][0] = NORM_SUCC)
--   OUT = prev
```

This requires conditional dispatch (test emptiness after difference), equality test (difference-with-self to get empty when equal), and calling the succ function under U[6][0].

### Subroutines under U[7]

| Slot       | Name      | Purpose                                          |
|------------|-----------|--------------------------------------------------|
| U[7][0]    | PRED_MAIN | Main predecessor entry: search loop               |
| U[7][1]    | PRED_CALL | (if needed) helper to call U[6][0] succ           |

### Building U[7] during init

1. Build PRED_MAIN subroutine in C (via `Sets' Sets' ... Sets'`)
2. Store: `U[7] = U[7] ∪ {C}`
3. Build any helpers under additional entries

---

## S5B for dynamic operations

### exec-style use

S5B input reads a token stream, parses it into a `SubroutineSet` with `io_s5b=True`, then auto-executes when used as a binary operand. This lets us:

- **Load callable code at runtime**: construct S5B bytes externally, pipe into stdin, read via `set sets set's'` in A/B position, union with anything → body executes.
- **Bypass static subset-select limits**: dynamic indices or variable-length sequences are achievable by compiling to S5B externally rather than encoding in s5.

### Extending existing subroutines

The S5B encode path serializes instruction token lists into byte pairs. Appending new instruction tokens before encoding produces an extended token stream. Reading it back yields a `SubroutineSet` with the combined body.

**End-marker note**: naive byte concatenation of two encoded S5B streams won't work — `decode_tokens` stops at the end-of-stream marker (odd token count signaled by bit 7). To extend, combine the *token lists* (e.g., `serialize_body(instrs_a) + serialize_body(instrs_b)`) then `encode_tokens` the result.

### Test: `test_extend_subroutine_via_s5b` — PASSED

In `tests/test_s5b.py::TestWriteS5B`:

```
1. Parse instruction stream X ("double U")
2. Parse instruction stream Y ("double U")
3. Combine: serialize_body(X) + serialize_body(Y)
4. Encode combined tokens → S5B bytes
5. _read_s5b → SubroutineSet with len(body) == 2
6. Execute body → U doubled twice: len(U) == 4
```

---

## Implementation Order

1. ~~Write and verify `test_s5b_extend_subroutine` (prove S5B extension works)~~ — DONE, PASSES
2. ~~Write `init.s5` with documented `--bufsize` requirement~~ — DONE, VERIFIED
3. ~~Write `succ.s5` — start with unary+normalized variants~~ — DONE, VERIFIED
4. Write `pred.s5` — search-based, entry at U[7][0], scratch in U[3..5]
5. Verify end-to-end: init → succ → pred round-trips
