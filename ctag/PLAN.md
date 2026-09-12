# Cyclic Tag Interpreter Plan (in-S5)

Proves S5 is Turing-complete by implementing a bounded **Cyclic Tag** machine —
the smallest known Turing-complete system (Minsky 1961) — entirely as an S5
program. The implementation is a **straight-line generator** of fixed machines:
`_gen_ctag.py` emits `ctag.s5`, one instruction list per (productions, data).

## Slot Allocation

C = working cache / temporary accumulator.  Registers, structures and the bit
buffer live in U slots *above* the arithmetic area (0..16), in the region
U[32..111] reached after the generated code doubles U twice (32→64→128).

| Slot | Name      | Contents                                                        |
|------|-----------|-----------------------------------------------------------------|
| U[0] | ZERO      | `∅` — value 0 (from arithmetic init)                            |
| U[1] | ONE       | `{∅}` — value 1 (from arithmetic init)                          |
| U[3] | IN_A      | NORM_SUCC input register (from arithmetic succ)                 |
| U[6] | SUCC      | successor structure, [0] = NORM_SUCC (from arithmetic succ)     |
| U[32]| CTAG      | structure: [0]=STEP, [1]=DISPATCH_APPEND, [2]=RESET_PM          |
| U[33]| PROD      | structure: [k] = routine that appends production P[k]           |
| U[34]| BIT       | current head bit (∅ or {∅})                                     |
| U[35]| CONT      | non-empty iff PH != PT (word non-empty)                         |
| U[36]| EQN       | non-empty iff succ(PM) == n (production wrap)                   |
| U[37]| TMP       | scratch: succ(PM)                                               |
| U[38]| PH        | head pointer — canonical value `bias + h`                       |
| U[39]| PT        | tail pointer — canonical value `bias + t`                       |
| U[40]| PM        | production index — canonical 0..n-1                             |
| U[41]| N_CANON   | canonical n (number of productions)                             |
| U[42]| BIAS_CANON| canonical bias (first buffer slot index)                        |
| U[44]| SC        | tick counter (result register)                                  |
| U[64..111] | buffer | bit-buffer: U[bias + k] holds the k-th bit ever written         |

`bias` defaults to 64, capacity `n` to 48 slots.

> **Growth contamination (lesson learned).** Growing U by self-union
> (`U = U ∪ U`) copies the *entire current universe*, not just the original
> cells: after 32→64→128, slots 32..63 hold copies of the arithmetic slots
> (in particular U[33] was a copy of ONE = `{∅}`).  `ctag.s5` therefore
> *explicitly clears* the two accumulating structure slots
> (`U[CTAG] = ∅`, `U[PROD] = ∅`) before building.  Every register is also
> written before use; buffer slots are written on load or on append before
> they are ever read (the live window is `[PH, PT)`).

## Representation

* **Bits** are stored as elements of the buffer set: bit 0 = `∅` (a ZERO
  element), bit 1 = `{∅}` (a ONE element).  Writing `U[PT] = {bit}` uses
  `inters(UD(b), UD(b), DEPTH2(UD(PT)))`.
* **Integers** are canonical mixed-unary sets: `int_to_s5set(v)`.  Pointers
  PH/PT hold `set_value` values directly, so set-theoretic comparison works on
  them via wrapped diff (see equality notes below).
* **Runtime-indexed buffer access.**  Dispatch depth 2 turns a U-address into
  *"U indexed by the value held in slot X"*: `DEPTH2(UD(PH))` resolves to
  `U[set_value(U[38])]`.  This is how the buffer is read/written at the
  current head/tail.
* **Equality tests.** Two canonical sets `a`, `b` are equal iff
  `diff(WRAP(a), WRAP(b))` is empty; `inters(WRAP(a), WRAP(b))` is a nonempty
  singleton `{a}` iff equal.  `WRAP` is mandatory — a bare set operand to
  diff/inters would treat its *elements* as the operands.
* **Conditional call.** `Set Sets'` with a *condition address*
  (`subr_call(cond=…)` in the generator) skips the call when the resolved
  condition is empty.  `diff(WRAP(PH), WRAP(PT), CONT)` yields a non-empty
  CONT iff PH != PT, i.e. the word is non-empty.

## Machine Model

Cyclic tag (Minsky's definition):

```
given productions P[0..n-1] (bit strings) and a data word (bit string),
m = 0
repeat until word empty:
    b = delete first bit of word
    if b == 1: append P[m]
    m = (m + 1) mod n
```

The number of ticks is the number of heads read (the loop iterations);
`SC` counts them and is the machine's output.  The word survives as the
interval `[PH, PT)` in the linear buffer; pointers equal ⇔ word empty.

## The Emitted Program

### Setup (instructions 0..~50)

1. `U = U ∪ U ; U = U ∪ U` — grow universe 32 → 128.
2. `C = ONE ∩ ONE` — pin C to a defined non-subroutine value.
3. `U[CTAG] = ZERO ∩ ZERO; U[PROD] = ZERO ∩ ZERO` — clear structure slots
   (they hold doubles of the arithmetic universe; see growth note).
4. `emit_const` for PH = 64, PT = 67 (data "101"), N_CANON = 2,
   BIAS_CANON = 64; PM = 0; SC = 0.
5. load the initial data word "101" into U[64], U[65], U[66].
6. build the structures **CTAG** = [STEP, DISPATCH_APPEND, RESET_PM] and
   **PROD** = [APPEND_0, APPEND_1] by declaring each body in C then
   `U = U ∪ {C}` with a WRAP.
7. entry block: compute CONT (word non-empty?), select STEP, conditionally
   call it; then (in the showcase) write `set_value(SC)` to the fd 0 buffer
   to print the tick count.

### STEP (U[32][0]) — one tick

```
emit_incr(SC, SC)                          # ticks += 1
BIT = U[PH]                                # read head bit
emit_incr(PH, PH)                          # delete head bit
C = CTAG; C = C[1]; call DISPATCH_APPEND iff BIT     # append P[PM] iff head bit 1
TMP = succ(PM); EQN = (TMP == n)           # wrapped equality with N_CANON
PM = TMP
C = CTAG; C = C[2]; call RESET_PM iff EQN  # if PM == n: PM = 0
CONT = diff(WRAP(PH), WRAP(PT))
C = CTAG; C = C[0]; call STEP iff CONT     # loop while word non-empty
```

`emit_incr` is a 5-instruction canonical increment: copy to IN_A, select
NORM_SUCC (U[6][0]), call it (it normalizes `IN_A ∪ ONE` via an fd-0
round-trip and leaves the result in C/OUT), copy back to the target slot.
This requires `arithmetic/init.s5` + `arithmetic/succ.s5` to have run first,
and a `--bufsize` large enough for the largest value (≥ 128) plus newline.

### DISPATCH_APPEND (U[32][1])

```
C = PROD; C = C[value(PM)]; call          # run APPEND_P[PM]
```

The runtime *indirected subset-select* (`SUBSET_SELECT` with an address)
chooses the production by the current PM value — the same mechanism
`pred1.s5` uses for O(1) LUT lookup.

### RESET_PM (U[32][2]) / APPEND_P[k] (U[33][k])

```
U[PM] = ZERO                          # RESET_PM: production index wraps to 0
U[PT] = bit; PT = succ(PT)            # APPEND_P[k]: per bit, write then advance tail
```

Appending never rewrites earlier slots: the tail pointer only moves forward.

## Turing Completeness

Cyclic tag is Turing-complete (Minsky 1961): every program of an arbitrary
tag system can be *weakly simulated* by a cyclic tag machine over a finite
production list when the simulation is run on the right initial data; and
tag systems themselves simulate arbitrary Turing machines (via a shift-reduce
encoding — the classic `0^A 1^B` counting construction).  Because every *finite*
cyclic tag machine that halts within the buffer capacity is realized here as
an S5 program that runs to completion producing exactly the same tick count as
the definitional simulator (`reference.py`), this gives a bounded model of a
Turing-universal system, i.e. a formal demonstration that S5 can encode
universal computation step-for-step.

Scope: this showcase instantiates a *fixed, single* machine per generated
program (buffer is fixed-size 48, no wrapping — the generator refuses machines
whose run would exceed it).  The universe itself is unbounded, so any finite
tag computation fits in a large-enough generated buffer; U grows to 128 here,
which accommodates the showcase machine with room to spare.

## Files

* `reference.py` — definitional simulator (`simulate`, `steps`, `buffer_usage`)
  giving expected results and the overflow guard's bound.
* `_gen_ctag.py` — the generator; keeps the slot map, emits `ctag.s5`.
* `ctag.s5` — committed showcase: `P = ["0", ""]`, data `"101"`, prints `5`.
* `test_ctag.py` — 14 tests running the *actual* S5 executor
  (structure shapes, dispatch appends, PM wrap, overflow refusal, and step
  counts matching the reference).

## Implementation Order

1. ~~Reference simulator + generator skeleton~~ — DONE
2. ~~Canonical constants with WRAP; depth-2 read/write; runtime indexed
   subset-select; wrapped equality; conditional calls~~ — DONE (experiments pass)
3. ~~Fix structure build after universe doubling (clear CTAG/PROD)~~ — DONE
4. ~~Regenerate showcase; committed file runs and prints 5~~ — DONE
5. ~~Full suite: 235 tests pass (14 in ctag)~~ — DONE