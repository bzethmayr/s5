# Arithmetic
We haven't got any. If you want any, you'll have to make some.
This document describes how to construct arithmetic operations on top of S₅'s primitives, since none are provided by the language itself.

## Primitives
See [README.md](./README.md) and note:
1. `union` is concatenation.
2. `difference` is removal of structural duplicates between sets.
3. `comparison` is empty vs non-empty, which means that the only trivial comparison is for structural equality.

### Memory
You can grow U either by self-union (U ∪ U) to double its length, by union with `{∅}` (wrapped empty set) to append a single element, or by subset-select union to duplicate an existing element. 

## Numbers
There are multiple representations for any given positive integer:
* up to one canonical unary representation 
* exactly one canonical mixed representation
* an increasing number of non-canonical mixed representations with integer value

Comparison is therefore only reliable between canonical forms.
Mixed-representation is a-priori more performant than pure unary for anything but very small sizes.

### ZERO
The integer 0 has two useful representations:
- `{}` (the empty set) — the canonical value-0 set, but empty (so it reads as false/falsy in conditional dispatch).
- `{{∅}}` (a set containing exactly one non-empty set) — also value 0, but non-empty. Keeping this in a dedicated U slot may be helpful as a "working zero."

Note that appending a ×2 element ("adding a zero" in mixed-unary) as a suffix multiplies the set's value by two.

### ONE
Is represented by (a set containing) exactly one empty set - keeping this in U0 or U1 may be helpful.

## Successor
Without at least one non-zero I/O buffer (see [I/O with indirection](./README.md#io-with-indirection-file-descriptor-io)), the successor function can only be implemented for the unary representation — by appending `ONE`. With an I/O buffer, the incremented unary form can be normalized to the canonical mixed form by writing it to a buffered fd and reading it back.

### Addition
Requires successor - requires LUTs to improve over O(n).

### Multiplication
Requires addition and benefits from optimized addition.

## Predecessor
Requires successor and benefits immediately from LUTs

### Subtraction
Requires predecessor, benefits from optimized predecessor, and benefits from own LUTs.

### Division
Requires subtraction, practically requires optimized subtraction

## Tips & Tricks

### 1. Subroutine values

Every subroutine's integer value equals its instruction count. Each `LineSet` element is empty, so `set_value` adds 1 per instruction. For example, a 3-instruction subroutine has value 3.

Unioning a subroutine with `ONE` (the set `{∅}`) increments its value by 1. Round-tripping through integer I/O normalizes the result to canonical form, converting the instruction count into a plain set. This is useful as a counter source or for initialization.

### 2. Wrap-in-union semantics

The wrap address `Sets sets' X` resolves to `{value_of_X}` — a singleton set whose sole
element is `X`'s value. But **union concatenates items**, so `U ∪ {X}` adds `value_of_X`
itself as an element, not `{value_of_X}` as a wrapped unit. For example, if `C = {∅}` (ONE),
then `U ∪ {C}` appends `{∅}` (not `{{∅}}`). To append `{{∅}}` (ZERO), double-wrap:
`U ∪ {{C}}` = `Sets sets' Sets sets' C`, whose sole item is `{C}` = `{{∅}}`.

This applies to all binary ops (union, intersection, difference) — they all operate
at the **item** level of their resolved operands.

### 3. Universe size during flat growth

Before any subroutine definitions, every element of U is `∅`, so `set_value(U) == len(U)`. This is a natural allocation counter after initial bootstrapping doublings — no separate tracking needed.

### 4. Cross-format I/O (when all else fails)

The three I/O forms (integer, byte, s5b) each produce different normalized shapes from the same value. You are not required to read in the same format you wrote — if the transforms between the three forms appeal to you, cross-format reads and writes are valid. Predicting the outcome is very, very difficult, but when sanity has betrayed you it can produce useful effects.

### 5. Universe normalization (when all else fails)

Normalizing the universe via I/O generally won't halt the program — the transformation preserves the set's value, and halting only occurs when `len(U) == 0`. You can even normalize U to S5B form if you want. Again, predicting the output is very, very difficult.

### 6. Extending subroutines via union

Since 0.4.3, SubroutineSets in binary-op A/B positions are no longer auto-normalized to their instruction-count value. They retain their `LineSet` items through union, intersection, and difference. This enables appending S5B-read instructions to an existing static subroutine:

```python
U[4] = U[4] ∪ S5B_input   # concatenates LineSets from both
```

The union result is an `S5Set` (not `SubroutineSet`), so it is not directly callable. To restore the callable type, write the result as S5B to a buffer and read it back via `set's'` (not a binary op):

```
1. set's'  C = {S5B extension}       # read extension → SubroutineSet, no auto-exec
2. sets'  U[4] = U[4] ∪ C            # union: auto-executes C's body (side effect)
3. sets'   fd = U[4]                 # write extended set as S5B to fd buffer
4. set's'  C = {fd}                  # read back via ENCODE → fresh SubroutineSet, no auto-exec
5. sets'  U[4] = C                   # overwrite with callable subroutine
```

The type-restoring read-back via `set's'` (step 4) does **not** trigger auto-execution — `_io_s5b` auto-exec only fires in the binary-op A/B resolution path (lines 601-602).

**Caveats:**
- `_io_s5b` auto-execution on the extension SubroutineSet (step 2) is an unavoidable side effect when it appears in the union's B position.
- Intersection/difference of SubroutineSets compares `LineSet` elements structurally (instruction-by-instruction).
