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
| U[6] | SUCC     | successor structure        | [0]=NORM_SUCC, [1]=UGROWTH, [2]=NORM     |
| U[7] | PRED     | predecessor structure      | [0]=PRED_MAIN, [1]=PRED_ADVANCE, [2]=PRED_STEP |
| U[8] | pred scratch | scratch for pred search | Used internally by PRED_MAIN            |
| U[11]| V        | build loop counter         | Iterates 0..COUNTER-1 during LUT build   |
| U[12]| PRED1    | pred1 build subroutines    | [0]=PRED1_BUILD, [1]=LUT_BUILD_LOOP      |
| U[13]| scratch  | scratch (COND)             | Conditional temp during LUT build        |
| U[14]| bound    | loop bound                 | Copy of COUNTER for loop termination     |
| U[15]| ∅ source | empty source               | Zeros C via diff                         |
| U[16]| LUT      | pred LUT data              | pred(0)..pred(COUNTER-1), pure S5Set     |

Slots 3–5, 8, 9–15 initially hold `∅` from the growth phase.

---

## init.s5 — Bootstrap (9 instrs)

Goal: grow U to 32, install ZERO (=∅), ONE, COUNTER.

### Order

1. **Save ONE before growth**: `C = U ∩ U` → preserves `{∅}`.
2. **Grow U**: self-union ×5 (list-concat semantics: 1→2→4→8→16→32).
3. **Write COUNTER**: `U ∩ U → IO'1` writes `set_value(U)=32` to the fd 0 buffer (normalize, no stdout side effect).
4. **Read COUNTER**: `IO'1 ∪ U[4] → U[2]` reads 32 from the fd 0 buffer into U[2].
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

### Pred entry points

**O(1) LUT path (recommended, after pred1.s5 runs):**

```
C = U[16]        -- load LUT data
C = C[value(addr)]  -- indirected subset-select: addr = runtime query
```

**Search-based fallback (pred.s5, U[7][0]):**

```
C = U[7]         -- load PRED structure
C = C[0]         -- select PRED_MAIN subroutine
Set Sets'        -- invoke it
```

Internally U[7][0] uses `U[7][1..]` for helper subroutines (equality test, succ call, loop body).

### Strategy

Predecessor is harder than successor because removing elements changes the encoding in non-trivial ways.

Approaches:

**1. I/O normalization** — decrement via I/O: write value, subtract in integer domain, read back. Requires buffer support.

**2. Search-based** — iterate counter from 0 upward, comparing each value against input via equality test, stop when match found. The predecessor is the previous iteration's value. Very expensive but correct.

**3. LUT-based pred** — for small values, precompute and look up.

### LUT-based O(1) variant via indirected subset-select

Once the LUT is built in U[16] (by `pred1.s5`), runtime predecessor is O(1):

```
-- Load LUT, index with IN_A, result in C
C = U[16]
C = C[value(IN_A)]       -- indirected subset-select → pred(IN_A)
```

This requires no subroutine call, no loop, no I/O — just two instructions.

### pcode (search-based variant, fallback for unbuilt LUT)

| Slot       | Name      | Purpose                                          |
|------------|-----------|--------------------------------------------------|
| U[7][0]    | PRED_MAIN | Main predecessor entry: search loop               |
| U[7][1]    | PRED_CALL | (if needed) helper to call U[6][0] succ           |

### Building U[7] during init

1. Build PRED_MAIN subroutine in C (via `Sets' Sets' ... Sets'`)
2. Store: `U[7] = U[7] ∪ {C}`
3. Build any helpers under additional entries

---

## Indirected subset-select (0.5.x)

Version 0.5.x added **indirected (dynamic) subset-select**: `C = C[value(<address>)]`.

```
Set Sets set sets' <address>
```

The index is computed at runtime by resolving `<address>` and taking `set_value()` of the result.
This eliminates the need for S5B I/O to construct dynamic indices — any runtime value can be used
as a subset-select index directly.

### Impact on LUT construction

For `pred1.s5`, this means:

- **Build phase**: fill U[16] with `pred(0)` through `pred(COUNTER-1)` (same iterative process,
  calling PRED_MAIN for each V).
- **Runtime O(1) access** (new): once the LUT is built, any runtime query Q resolves in a single
  indirected subset-select:

```
C = U[16]              -- load LUT
C = C[value(IN_A)]     -- indirected subset-select → O(1) pred(Q)
```

This replaces calling PRED_MAIN (search-based, O(n)) for each runtime query. The LUT at U[16] is a
pure data set (no subroutines) and can be copied to any other U slot for reuse.

### Slot impact

No new slots needed — U[16] already holds the LUT data, and the indirected subset-select uses
existing registers (IN_A for query, C for LUT load + select).

---

## Implementation Order

1. ~~Write and verify `test_s5b_extend_subroutine` (prove S5B extension works)~~ — DONE, PASSES
2. ~~Write `init.s5` with documented `--bufsize` requirement~~ — DONE, VERIFIED
3. ~~Write `succ.s5` — start with unary+normalized variants~~ — DONE, VERIFIED
4. ~~Write `pred.s5` — search-based, entry at U[7][0], scratch in U[3..5]~~ — DONE, VERIFIED
5. ~~Write `pred1.s5` — build LUT in U[16] for O(1) runtime access via indirected subset-select~~ — DONE, VERIFIED
6. Verify end-to-end: init → succ → pred → pred1 → demo round-trips — DONE, ALL 24 TESTS PASS
