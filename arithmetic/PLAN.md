# Arithmetic System Plan

## Slot Allocation

C = working cache / temporary accumulator

| Slot | Name     | Contents                    | Notes                                    |
|------|----------|-----------------------------|------------------------------------------|
| U[0] | ZERO     | `{{∅}}` — value 0, truthy  | Working zero; non-empty so it passes conditional dispatch |
| U[1] | ONE      | `{∅}` — value 1            | Building block for unary growth          |
| U[2] | COUNTER  | `int_to_s5set(N)`          | Sampled before creating non-empty elements, so value == len(U) at that point |
| U[3] | IN_A     | scratch / input A          |                                          |
| U[4] | IN_B     | scratch / input B          |                                          |
| U[5] | OUT      | output register            |                                          |
| U[6] | SUCC     | successor structure        | Accessed via subset-select under U[6]    |
| U[7] | PRED     | predecessor structure      | Accessed via subset-select under U[7]    |

Slots 3–7 initially hold `∅` from the growth phase (usable as empty-set element sources until overwritten).

---

## init.s5 — Bootstrap

Goal: grow U to ≥8, install ZERO, ONE, COUNTER in their slots.

### Order

1. **Save ONE before growth**: `C = U ∩ U` → preserves `{∅}`.
2. **Grow U**: self-union until len ≥ 8 (three doublings: 1→2→4→8).
3. **Sample COUNTER**: with `--bufsize 1` or larger, write `set_value(U)` as integer to fd 0 buffer, read back into U[2]. All elements are still `∅` at this point, so `set_value(U) == len(U)`.
4. **Build ZERO** (`{{∅}}`): union U with `{{C}}` (double-wrapped ONE) → appends `{{∅}}` at U[len]. Copy to U[0] via `U[0] = U[len] ∩ U[len]`.
5. **Install ONE**: `U[1] = C ∩ C`.

> **Wrap-in-union semantics**: The S5 wrap address `Sets sets' X` resolves to `{value_of_X}`.
> Union concatenates items of both operands, so `U ∪ {X}` adds `value_of_X` itself as an
> element (e.g., `U ∪ {C}` adds `{∅}` = ONE). To add `{{∅}}` = ZERO, double-wrap:
> `{{C}}` = `Sets sets' Sets sets' C`, whose sole item is `{C}` = `{{∅}}`.

### pcode

```
-- 1. save ONE before growth
C = U ∩ U

-- 2. grow U to 8
U = U ∪ U   -- len 2
U = U ∪ U   -- len 4
U = U ∪ U   -- len 8

-- 3. counter → U[2]  (requires --bufsize 1+)
write set_value(U) as int to fd0 buffer   -- prints nothing, buffers internally
read int from fd0 buffer → U[2]           -- reads "8\n" → int_to_s5set(8)

-- 4. ZERO → U[0]
U = U ∪ {{C}}                   -- double-wrap: append {{∅}} at U[8]
U[0] = U[8] ∩ U[8]              -- copy {{∅}} to U[0]

-- 5. ONE → U[1]
U[1] = C ∩ C

-- 6. (optional) zero U[3..7] via self-difference if needed
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
