# Bitwise Cyclic Tag (BCT) — a runtime interpreter in S5

Status: **done** · fully tested (see `test_bct.py`)

This directory contains a **constant-size, general BCT runtime interpreter**
written in S5.  One fixed program (`bct/bct.s5`, 41 instructions) reads any
BCT machine from stdin, executes it to completion with an *unbounded* data
buffer, and prints the number of ticks.

It complements the `ctag/` showcase.  There, the machine's productions were
compiled into the S5 program (fixed-precision coding).  Here nothing is
compiled: the machine is *data*, read at runtime, and the interpreter grows
its own universe as the BCT data queue grows.

---

## 1. BCT and why it makes S5 Turing-complete

**Definition (Bitwise Cyclic Tag, Cook 2004).**  A BCT machine is a non-empty
finite *program* string of bits `p = p_0 … p_{n-1}` (a cyclic string), plus an
initial *data* string of bits.  One tick:

1. if the data string is empty, halt;
2. read and delete the first data bit `b`;
3. if `b == 1`, append the current program bit `p_m` to the data string;
4. advance the program head `m := (m + 1) mod n`.

**Equivalence with cyclic tag.**  A cyclic-tag machine uses *productions*
`P[0], …, P[n-1]` (bit strings): on seeing a `1` at the data head it *appends
the whole production* `P[m]`, then advances `m` mod `n`; on a `0` it appends
nothing and still advances `m`.

> **Theorem.**  BCT with program `s` has exactly the behaviour of the
> cyclic-tag machine whose productions are the single bits `P[m] = s[m]`.

`P[m]` has length one, so "append the production" *is* "append the current
program bit".  The reference simulators agree on this tick for tick
(verified in `reference.py`, and directly in `test_bct.py`).

Cook's (2004) universality proof for Rule 110 reduces cyclic tag
(a.k.a. *subscripted* cyclic tag / "Cook's cyclic tag") to Rule 110, so any
model that can simulate cyclic tag is Turing-complete:

```
BCT  ≡  cyclic tag (unit productions)  ⊑  Rule 110  ⇒  Turing-complete
```

---

## 2. What the interpreter does

Program (`bct/bct.s5`), with the arithmetic environment
(`arithmetic/init.s5` + `arithmetic/succ.s5`, which grow U to 32 and install
ZERO/ONE at `U[0]`/`U[1]` and `NORM_SUCC` at `U[6][0]`):

    python -m s5 --bufsize 256 bct/bct.s5 < payload

`payload` is a *self-describing* BCT instance on stdin:

    plen                      — one integer line
    program bit 0 .. plen-1   — one '0'/'1' line each
    dlen                      — one integer line
    data bit 0 .. dlen-1      — one '0'/'1' line each

The result (number of ticks) is printed on stdout.  The payload must be
exact: input reads loop until a line arrives, and increment normalisation
re-reads from the fd-0 buffer.  (Empty *data* is legal: dlen = 0 produces a
`0`-tick run.  An empty *program* is undefined — the reference rejects it.)

### Constant size

The program is **independent of the BCT machine**.  The interpreter body is
a fixed structure in the universe,

```
U[29] = [ READ_LOOP, APPEND, STEP, RESET_PP ]
```

and every loop is data-driven (pointer comparisons vs. runtime counts), never
compiled per bit.  The only occurrence of the machine in the program is… none:
machine bits arrive via stdin at runtime.

### Unbounded data buffer

The data is kept in **linear memory** `U[D_BASE], U[D_BASE+1], …` with two
pointers `DH` (head) and `DT` (tail):

* delete head bit   →  ``U[DH]`` then `DH := X+1`;
* read program bit  →  ``U[PP]``;
* append bit        →  grow the universe by one slot, write ``U[DT]``, `DT := X+1`.

growth appends ∅:  `U := U ∪ {∅}` (one fresh slot, `U[3] := U[3] ∪ {∅}`).

Because appends only ever happen at `DT` — the first slot beyond the live
word — growth is monotonic and the buffer is unbounded.  `test_bct.py`
drives a run whose peak word (72 bits) exceeds any fixed layout and checks
the full trace matches the reference, so the growth path is exercised.

## 3. Implementation notes

### Registers (U slots 17..30)

| slot | name   | purpose                                   |
|-----:|--------|-------------------------------------------|
|  17  | PP     | program pointer (absolute slot index)     |
|  18  | PLEN   | loop bound (program length, then data length) |
|  19  | I      | loop counter                              |
|  20  | W      | write pointer during the two load loops   |
|  21  | DH     | data head pointer                         |
|  22  | DT     | data tail pointer                         |
|  23  | BIT    | data-head bit                             |
|  24  | SC     | tick counter (the result)                 |
|  25  | CONT   | non-empty ⇔ `DH ≠ DT` (keep running)      |
|  26  | EQN    | equality/wrap scratch                     |
|  27  | TMP    | `succ(PP)` scratch                        |
|  28  | PBOUND | program wrap bound = `P_BASE + plen`      |
|  29  | STR    | interpreter structure                     |
|  30  | PBC    | canonical `P_BASE` (= 32)                 |

Program bits live at `U[32 … 31+plen]`, data begins at `U[32+plen]`.

`EQN`/`CONT`/`BIT` are used as *guards*: a value is truthy iff it is a
non-empty set.  Equality of pointers is tested with the canonical-WRAP
idiom (a singleton `{⟨value⟩}` is never empty):

```
a == b   ⇔   WRAP(a) ∖ WRAP(b) = ∅        (difference empty)
a == b   ⇔   WRAP(a) ∩ WRAP(b) ≠ ∅        (intersection non-empty)
```

### The four routines

* **READ_LOOP** (17 instrs): `C := stdin bit` (raw IO), grow U, `U[W] := C`,
  `W := X+1`, `I := X+1`, then recurse while `I ≠ PLEN`.
* **APPEND** (8): `C := U[PP]` (depth-2), grow U, `U[DT] := C`, `DT := X+1`.
* **STEP** (28): `BIT := U[DH]`, `DH := X+1`; if `BIT` call APPEND; `TMP := X+1`
  of PP; advance `PP := TMP`, wrapping to PBC if `TMP == PBOUND` (RESET_PP,
  1 instr); `SC := X+1`; recurse while `DH ≠ DT`.
* **RESET_PP** (1): `PP := PBC`.

### I/O discipline (the subtle bit)

`NORM_SUCC` is a pure-in-S5 routine that canonicalises a successor via a
round trip through the **fd-0 buffer** (it needs `--bufsize`).  NORM is
triggered by *every* increment.  If the BCT input were also read through the
fd-0 buffer, the two streams would interleave and NORM would swallow input
lines.  Therefore **input uses raw (non-fd) IO addresses**, which read
`sys.stdin` directly and never touch the fd-0 buffer, keeping the two
streams disjoint:

```
input bit   →   IO (raw)
result out  →   IO :: 1  (fd 1)
```

This is precisely why the interpreter works both in-process and under
`python -m s5 < bct/bct.s5`.

---

## 4. Repository layout

```
arithmetic/init.s5   environment: grow U to 32, ZERO/ONE
arithmetic/succ.s5   environment: NORM_SUCC at U[6][0]
bct/reference.py     definitional BCT simulator (pure Python)
bct/_gen_bct.py      generates the constant-size interpreter (41 instrs)
bct/bct.s5           generated interpreter (committed, run from the CLI)
bct/test_bct.py      17 tests: reference equivalence, edges, randomized
                     battery, structure, unbounded-buffer growth, CLI run
```

## 5. Validation summary

* 11 hand-picked machines: `ticks(S5) == ticks(reference)` (and `DH == DT`).
* 120 random small machines (filtered to halting ones): all match.
* Edge cases: empty data → 0 ticks; all-zero program / data; single bits.
* Unbounded-buffer run (peak word 72) reproduces the reference trace.
* The committed `bct.s5` runs unchanged through `python -m s5`
  (`test_cli_subprocess`).

**Consequence.**  S5 can run an interpreter for the BCT system, which in turn
simulates Cook's cyclic-tag system, which is Turing-complete.  Hence S5 is
Turing-complete: *one fixed program* reads the machine, the data, and the
count out — nothing about the simulated machine is baked into the code.