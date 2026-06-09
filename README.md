# S₅ — The Set-Only Language

Every token is a form of `"set"`. All computation is over ordered sets of sets. Thus, we combine the clarity of the word "set" with the practicality of number theory.

## Tokens

| Token     | Kind                                        |
|-----------|---------------------------------------------|
| `Set`     | instruction prefix                          |
| `set`     | difference opcode / integer **+1** / binary separator |
| `sets`    | union opcode / integer **×2** / U-address suffix |
| `Set's`   | intersection opcode / base-address prefix   |
| `sets'`   | integer suffix / subset-select suffix / dispatch-depth prefix |
| `Sets`    | derived-address / wrap-address / subset-select opcode prefix |
| `Sets'`   | declaration / end / subroutine delimiter    |
| `set's'`  | integer I/O address                          |
| `sets set's'` | byte I/O address (2 tokens - "0I" or "0O") |
| `sets sets set's'` | s5b I/O address (3 tokens) |

## Initial state

```
U = {∅}        Universe: a set containing exactly the empty set
C = undefined  Cache: unbound until first assignment
H = false      Halted: set when len(U) reaches 0 after an instruction
```

## Grammar

```
<program>        ::= <instruction>*

<instruction>    ::= "Set" <opcode> [<operands>]

<opcode>         ::= "Sets" "set"         -- subset-select
                   | "sets"               -- union
                   | "Set's"              -- intersection
                   | "set"                -- difference
                   | "Sets'"              -- subroutine call

<operands>       ::= <subset_operands>
                   | <binary_operands>
                   | <subr_operands>

<subset_operands> ::= "sets'" <integer>

<binary_operands> ::= <address> <address> "set" <address>

<subr_operands>   ::= [<address>]
                   | "set" <address> [<address>]

<address>        ::= <base_addr>
                    | <derived_addr>
                    | <ud_addr>
                    | <wrap_addr>
                    | <io_addr>
                    | <byte_io_addr>
                    | <s5b_io_addr>

<base_addr>      ::= "Set's" "sets"       -- Universe U
                   | "Set's" "set"        -- Cache C

<derived_addr>   ::= "Sets" "set" "sets'" <integer>

<ud_addr>        ::= "Sets" "sets" "sets'" <integer>

<wrap_addr>      ::= "Sets" "sets'" <address>

<io_addr>        ::= "set's'"             -- integer I/O
<byte_io_addr>   ::= "sets" "set's'"      -- byte I/O
<s5b_io_addr>    ::= "sets" "sets" "set's'"   -- s5b I/O

<integer>        ::= ("set" | "sets")*    -- mixed-unary: set=+1, sets=×2
```

### Dispatch depth

Any address may carry an optional **dispatch depth** suffix encoded as `sets'` followed by a
mixed-unary integer. The integer encodes the number of extra resolution steps (default 0):

```
<dispatched_addr> ::= <address> ["sets'" <integer>]
```

Actual depth = `1 + integer_value`, so `sets' set` = depth 2, `sets' set sets` = depth 3, etc.
The suffix is backward-compatible: no suffix means depth 1 (static/single dispatch).

For **non-I/O** addresses (U, C, C[N], U[N], wrap) the dispatch depth controls the number of
U-indirection steps as described below.

For **I/O** addresses (`set's'`, `sets set's'`, and `sets sets set's'`), the dispatch depth has a different meaning —
it specifies a **file descriptor** (see *I/O with indirection* below).

| Address                          | Meaning      | Depth |
|----------------------------------|--------------|-------|
| `Set's sets`                     | U            | 1     |
| `Set's sets sets' set`           | U            | 2     |
| `Set's set sets' set sets`       | C            | 3     |
| `Sets set sets' set sets' set`   | C[1]         | 2     |
| `Sets sets sets' set sets' set` | U[1]         | 3     |

**R-value (read)**: resolve the address to a set V₁, then for each extra step use
`set_value(Vᵢ)` as an index into U, yielding the next Vᵢ₊₁.

```
resolve(addr) → V₁
for _ in range(depth - 1):
    idx = set_value(Vᵢ)
    Vᵢ₊₁ = U[idx]
return Vᴅ
```

**L-value (write)**: resolve through `depth - 1` levels to find the target U-index,
then store the value into `U[final_idx]`.

```
v = resolve_base(addr)
for _ in range(depth - 2):
    idx = set_value(v); v = U[idx]
final_idx = set_value(v)
U[final_idx] = value
```

This enables indirect subroutine dispatch (store a U-index in C, then call with
`Set Sets' Set's set sets' set` to follow the chain) and indirect storage into U
from any addressable location.

In the **second** address of a binary instruction, the final `"set"` of an integer
also serves as the instruction's separator token. Parsing uses a one-token
lookahead: if the next token after a `"set"` would start a new address
(`"Set's"` or `"Sets"`), the integer stops.

```
<bounded_integer> ::= <bit> <bounded_integer>
                    | <final_bit>
<bit>             ::= "set" | "sets"
<final_bit>       ::= "set"      -- consumed, then expect separator
```

### Values

Every set has a numerical value.  For an ordered set S = (e₁, ..., eₙ),
start with r = 0 and process each element left-to-right:

- **∅** (empty set): `r ← r + 1`
- **nonempty** set:  `r ← r × 2`

| Set             | Computation          | Value |
|-----------------|----------------------|-------|
| `{}`            | 0                    | **0** |
| `{∅}`           | 0→+1                 | **1** |
| `{{∅}}`         | 0→×2                 | **0** |
| `{∅, {∅}}`     | 0→+1=1→×2           | **2** |
| `{∅, {∅}, ∅}`  | 0→+1=1→×2=2→+1     | **3** |
| `{∅, {∅}, ∅, ∅}` | 0→+1=1→×2=2→+1=3→+1 | **4** |

The same scheme defines integer values for token sequences in the grammar.
Each token maps to an operation:

- `"set"`  → `+1`
- `"sets"` → `×2`

| Token sequence   | Computation            | Value |
|------------------|------------------------|-------|
| `sets`           | 0→×2                   | 0     |
| `set`            | 0→+1                   | 1     |
| `set sets`       | 0→+1=1→×2             | 2     |
| `set set`        | 0→+1=1→+1             | 2     |
| `set sets sets`  | 0→+1=1→×2=2→×2       | 4     |
| `set sets set`   | 0→+1=1→×2=2→+1       | 3     |

## Evaluation model

### Instructions

```
for each instruction:
    1. parse          — "Set" <opcode> <operands>
    2. resolve(A, B)  — addresses → S5Set values
    3. compute        — A <op> B  (union / intersection / difference)
     4. assign(D)      — result → destination address (WRAP rejected as dest)
    5. halt check     — if len(U) == 0: H = true, stop
```

- **Subset-select**: `C = C[N]`, 0-indexed. Fails if C is undefined or N out of bounds.
- **U-element**: `U[N]` (via `Sets sets sets' <n>`) — resolves to the N-th element of U, 0-indexed. Fails if N out of bounds. Can be assigned to (via subroutine definition) or used in A/B position.
- **Union** (`"sets"`): concatenation (duplicates preserved).
- **Intersection** (`"Set's"`): elements of A that also appear in B (preserves A order).
- **Difference** (`"set"`): elements of A not in B (preserves A order).
- **Wrap** (`"Sets sets'"`): wraps the resolved inner address into a singleton set `{value}`. Read-only — cannot be used as destination.
- **Integer I/O** (`"set's'"`): in A/B position, reads a decimal integer line from stdin and converts it to an S5Set; in D position, prints the set's numerical value as a decimal string to stdout.
- **Byte I/O** (`"sets" "set's'"`): in A/B position, reads a single raw byte (0–255) from stdin; in D position, writes the set's numerical value as one or more little-endian raw bytes to stdout (divides by 256 until zero, always emits at least one byte).
- **S5B I/O** (`"sets" "sets" "set's'"`): in A/B position, reads a binary .s5b token stream from stdin, parses it as a program, and wraps the result in a `SubroutineSet`; in D position, serializes the set's value back to .s5b binary and writes it to stdout. R-value operands in binary opcodes auto-execute before computation, making .s5b subroutines callable at instruction granularity.
- **Subroutine call** (`"Set" "Sets'"`): executes the subroutine stored at the given address (or C if omitted). Subroutine values are created via definition (see below).
- **Conditional call** (`"Set" "Sets'" "set" <cond> [<subr>]`): resolves `cond`. If non-empty, resolves `subr` (defaults to C) and calls the subroutine. If empty (`∅`), the instruction is a no-op. This is the only branching mechanism — use difference with itself to produce an empty condition, or union with a non-empty set to ensure a call.

### Subroutine definitions

A subroutine definition is a top-level construct (not an instruction):

```
<definition>     ::= "Sets'" "Sets'" [<address>] <instruction>+ "Sets'"
```

It creates a `SubroutineSet` whose elements are `LineSet` wrappers around each instruction's tokens. The subroutine is assigned to the given address (or C if omitted). The address can be any assignable target — `Set's sets` (U), `Set's set` (C), or `Sets sets sets' <n>` (U[n]). This enables first-class subroutines that can be stored at specific slots, passed around, and called.

```
Sets' Sets' Sets sets sets' set  -- assign to U[1]
    Set sets Set's sets Set's sets set Set's set
Sets'
Set Sets' Sets sets sets' set     -- call the subroutine at U[1]
```

## Simple cases
See [tests](tests) for more cases.

### Empty program

```
⟨no input⟩
```

```
U = {∅}   (no instructions run)
→ finished
```

### Difference: U \ U  (halts)

```
Set set Set's sets Set's sets set Set's sets
│   │   │      │   │      │   │   │      │
│   │   │      │   │      │   │   └──────┴── D = U
│   │   │      │   │      │   └───── separator
│   │   │      │   └──────┴───────── B = U
│   │   └──────┴──────────────────── A = U
│   └──────────────────────────────── opcode = "set" (difference)
└──────────────────────────────────── instruction start
```

```
resolve(A) = U = {∅}
resolve(B) = U = {∅}
result = {∅} \ {∅} = {}
assign(D=U): U = {}
len(U) == 0 → halt
```

### Union: U ∪ U

```
Set sets Set's sets Set's sets set Set's sets
│   │    │      │   │      │   │   │      │
│   │    │      │   │      │   │   └──────┴── D = U
│   │    │      │   │      │   └───── separator
│   │    │      │   └──────┴───────── B = U
│   │    └──────┴──────────────────── A = U
│   └──────────────────────────────── opcode = "sets" (union)
└──────────────────────────────────── instruction start
```

```
resolve(A) = U = {∅}
resolve(B) = U = {∅}
result = {∅} ∪ {∅} = {∅, ∅}
assign(D=U): U = {∅, ∅}
len(U) == 2 ≠ 0 → finished
```

### Intersection: U ∩ U

```
Set Set's Set's sets Set's sets set Set's sets
│   │    │      │   │      │   │   │      │
│   │    │      │   │      │   │   └──────┴── D = U
│   │    │      │   │      │   └───── separator
│   │    │      │   └──────┴───────── B = U
│   │    └──────┴──────────────────── A = U
│   └──────────────────────────────── opcode = "Set's" (intersection)
└──────────────────────────────────── instruction start
```

```
resolve(A) = U = {∅}
resolve(B) = U = {∅}
result = {∅} ∩ {∅} = {∅}
assign(D=U): U = {∅}
len(U) == 1 ≠ 0 → finished
```

### Write to C, then use it

```
Set sets Set's sets Set's sets set Set's set    -- C = U ∪ U = {∅, ∅}
Set Sets set sets' sets                          -- C = C[1] = ∅
Set set Set's sets Set's set set Set's sets      -- U = U \ C = {∅} \ {∅} → halt
```

#### Step-by-step

**Instr 1**: `Set` | `sets` (union) | `Set's sets`(A=U) | `Set's sets`(B=U) | `set` | `Set's set`(D=C)
```
resolve(A)=U={∅}, resolve(B)=U={∅}
result = {∅} ∪ {∅} = {∅, ∅}
assign(D=C): C = {∅, ∅}
len(U)=1 → no halt
```

**Instr 2**: `Set` | `Sets set` (subset-select) | `sets'` | `sets`(N=0)
```
C = C[0] = ∅
len(U)=1 → no halt
```

**Instr 3**: `Set` | `set` (difference) | `Set's sets`(A=U) | `Set's set`(B=C) | `set` | `Set's sets`(D=U)
```
resolve(A)=U={∅}, resolve(B)=C={∅}
result = {∅} \ {∅} = {}
assign(D=U): U = {}
len(U)==0 → halt
```

### Derived address: C[N] in A position

```
Set sets Set's sets Set's sets set Set's set        -- C = U ∪ U = {∅, ∅}
Set sets Sets set sets' sets Set's sets set Set's sets  -- U = C[0] ∪ U
```

**Instr 2** breakdown:
`Set` | `sets` (union) | `Sets set sets' sets`(A=C[0]) | `Set's sets`(B=U) | `set` | `Set's sets`(D=U)

1. `C[0]` is resolved: `C = {∅, ∅}`, so `C[0] = ∅` = S5Set() = `{}`
2. `U = U ∪ C[0]` adds another copy of ∅ to U

### Bounded integer: C[2] in B position

```
Set sets Set's sets Set's sets set Set's set     -- C = U ∪ U = {∅, ∅}
Set set Set's sets Sets set sets' set sets set Set's sets  -- U = U \ C[2]
```

Tokens: `Sets` `set` `sets'` `set` `sets` `set`

After `Sets set sets'`: start integer parsing. `set` = +1 → value=1. Next is `sets` = ×2 → value=2. Next is `set` — bounded lookahead: after this `set` would `"Set's"` or `"Sets"` follow? Next token is `Set's sets` (D address). So `Set's` follows → yes, address follows → stop at the `set` without consuming. Return integer = 2.

B = C[2]. C has length 2 (indices 0,1) → runtime error: "out of bounds".

### Wrap address: {U} and {C[N]}

```
Set sets Set's sets Sets sets' Set's sets set Set's sets
```

Binary operands: A=`Set's sets`(U) | B=`Sets sets' Set's sets`(={U}) | separator `set` | D=`Set's sets`(U)

B resolves as: `Sets sets' <inner>` → inner = `Set's sets` = U → wrap → `{U}`.

```
resolve(A) = U = {∅}
resolve(B) = {U} = {{∅}}
result = {∅} ∪ {{∅}} = {∅, {∅}}
assign(D=U): U has 2 distinct elements
```

With wrap + derived address:

```
Set sets Set's sets Sets sets' Sets set sets' set set Set's sets
```

B = `Sets sets'`(wrap) `Sets set sets' set`(derived addr C[1]) → `{C[1]}`.

If C = {∅, {∅}} beforehand, then C[1] = {∅}, and B = {{∅}}.
U = U ∪ {{∅}} produces a set with 3 elements.

### I/O: output and input

Output the value of U ∪ U (which has value 2) to stdout:

```
Set sets Set's sets Set's sets set set's'
```

| Token        | Role               |
|--------------|--------------------|
| `Set`        | instruction start  |
| `sets`       | union opcode       |
| `Set's sets` | A = U              |
| `Set's sets` | B = U              |
| `set`        | separator          |
| `set's'`     | D = output         |

```
resolve(A) = U = {∅}
resolve(B) = U = {∅}
result = {∅} ∪ {∅} = {∅, ∅}
assign(D=set's'): prints "2" (set_value = 2)
```

Read an integer from stdin and make it the new value of C:

```
Set sets set's' Set's sets set Set's set
```

| Token        | Role               |
|--------------|--------------------|
| `Set`        | instruction start  |
| `sets`       | union opcode       |
| `set's'`     | A = stdin → S5Set  |
| `Set's sets` | B = U              |
| `set`        | separator          |
| `Set's set`  | D = C              |

Input `7\n` → `int_to_s5set(7)` = `{∅, {∅}, ∅, {∅}, ∅}`.
C = input ∪ U = 5-element set prepended to {∅}.

### Byte I/O: raw byte input and output

Output the value 2 as a raw byte (0x02) to stdout:

```
Set sets Set's sets Set's sets set sets set's'
```

| Token          | Role               |
|----------------|--------------------|
| `Set`          | instruction start  |
| `sets`         | union opcode       |
| `Set's sets`   | A = U              |
| `Set's sets`   | B = U              |
| `set`          | separator          |
| `sets set's'`  | D = byte output    |

```
resolve(A) = U = {∅}
resolve(B) = U = {∅}
result = {∅} ∪ {∅} = {∅, ∅}
set_value({∅, ∅}) = 2
assign(D=sets set's'): writes b'\x02'
```

Read a single raw byte from stdin and store it in C:

```
Set sets sets set's' Set's sets set Set's set
```

| Token          | Role               |
|----------------|--------------------|
| `Set`          | instruction start  |
| `sets`         | union opcode       |
| `sets set's'`  | A = byte stdin     |
| `Set's sets`   | B = U              |
| `set`          | separator          |
| `Set's set`    | D = C              |

Input `\x2A` → `int_to_s5set(42)` = `{∅, {∅}, {∅}, ∅, {∅}, {∅}, ∅, {∅}}`.
C = input ∪ U = 8-element set prepended to {∅}.

Multi-byte output uses little-endian division: a set with value 256 emits `\x00\x01`,
value 0 emits `\x00`.

### S5B I/O: binary token stream input and output

The `sets sets set's'` address performs I/O on binary-encoded s5 token sequences
(the `.s5b` format). Tokens are encoded in 3-bit codes, LSB-first, packed into bytes.

**Write path** (`sets sets set's'` as destination):

| Value type | Serialization |
|---|---|
| `SubroutineSet` | Each instruction's body is serialized via `serialize_body()` (token type list → 3-bit codes → bytes), then all instructions are concatenated |
| Plain `S5Set` | The set's numerical value is decomposed into 3-bit token codes (LSB first: `n & 7`, `n >>= 3`), each mapped through `CODE_TO_TOKEN`, then encoded via `encode_tokens()` |

Example: write subroutine body `Set sets sets' sets' Set's set` (tokens: `Set`, `sets`, `sets'`,
`sets'`, `Set's`, `set`) to stdout:

```
Set sets Set's sets Set's sets set sets sets set's'
```

| Token | Role |
|---|---|
| `Set` | instruction start |
| `sets` | union opcode |
| `Set's sets` | A = U |
| `Set's sets` | B = U |
| `set` | separator |
| `sets sets set's'` | D = s5b output |

**Read path** (`sets sets set's'` as A or B operand):

The binary stream is decoded via `decode_tokens()`, then parsed as a program. Each
instruction becomes a `LineSet` element of a `SubroutineSet`. The resulting
`SubroutineSet` has no side effects during resolution — execution only happens when
the value is used as an R-value operand in a binary opcode (see evaluation model above).

Example: read .s5b binary from stdin and store the parsed subroutine in C:

```
Set sets sets sets set's' Set's sets set Set's set
```

| Token | Role |
|---|---|
| `Set` | instruction start |
| `sets` | union opcode |
| `sets sets set's'` | A = s5b stdin |
| `Set's sets` | B = U |
| `set` | separator |
| `Set's set` | D = C |

**Auto-execution**: When a `SubroutineSet` loaded via S5B I/O appears as an A or B
operand of a binary opcode (`sets`, `Set's`, or `set`), it is automatically executed
before the opcode's computation. This makes it possible to load and call subroutines
at instruction granularity. Subroutines declared via `Set Sets'` (SUBR) are *not*
auto-executed — only S5B-loaded `SubroutineSet` values carry the internal flag to
trigger this behavior, preventing infinite recursion.

### I/O with indirection (file descriptor I/O)

When a dispatch depth suffix is present on an I/O address, the depth value selects a
**file descriptor** instead of triggering U-indirection:

| Dispatch depth | File descriptor | Meaning           |
|----------------|-----------------|-------------------|
| 1 (`sets' sets`)  | 0               | stdin (buffered)  |
| 2 (`sets' set`)   | 1               | stdout (buffered) |
| 3 (`sets' set sets`) | 2            | stderr (buffered) |

Dispatch depth 1 with the suffix `sets' sets` (integer value 0) is backward-compatible
with the no-suffix case, except that buffered I/O rules apply.

**Buffers**: each file descriptor has an associated byte buffer whose size defaults to 0
(no buffering) and is configurable via the `--bufsize` / `-b` CLI flags. Buffer content
is kept as a **tail** — only the last N bytes written to the descriptor are retained.

| fd | Write behavior | Read behavior |
|----|----------------|---------------|
| 0 (stdin) | Appends to stdin buffer only (does not write to real stdin) | Reads from stdin buffer first; if empty, falls through to real stdin |
| 1 (stdout) | Writes to real stdout *and* appends to stdout buffer | Reads from stdout buffer (previously written output) |
| 2 (stderr) | Writes to real stderr *and* appends to stderr buffer | Reads from stderr buffer (previously written output) |

This enables in-process piping: a program can write to fd 0 to queue input, or capture
its own output by reading from fd 1/2.

### Subroutine: define, store, and call

Define a subroutine in C that unions U with itself, then call it:

```
Sets' Sets'
    Set sets Set's sets Set's sets set Set's set
Sets'
Set Sets'
```

First line: `Sets' Sets'` begins definition, subroutine body is `Set sets Set's sets Set's sets set Set's set`, then `Sets'` ends definition. The subroutine is stored in C.

`Set Sets'` calls the subroutine in C (no address → defaults to C), which executes the body, doubling U.

### Conditional call

Define a subroutine that doubles U, then call it only if U is non-empty:

```
Sets' Sets'
    Set sets Set's sets Set's sets set Set's sets
Sets'
Set Sets' set Set's sets
```

The condition is `Set's sets` (U). Since U starts as `{∅}` (non-empty), the call executes, doubling U to `{∅, ∅}`.

To skip the call, produce an empty condition via difference:

```
Set set Set's sets Set's sets set Set's sets   -- U = U \ U = {}
Set Sets' set Set's sets                        -- condition is {} → skip
```

The first instruction empties U. The second instruction's condition resolves to `∅`, so the subroutine is never called. The program halts immediately after (since `len(U) == 0`).

## Computing 42

A set whose value is 42, built via the mixed-unary scheme. Each
step applies the next element's operation to the running total:

| Step | Element             | Operation | Running total |
|------|---------------------|-----------|---------------|
| 1    | ∅ (empty set)       | +1        | 1             |
| 2    | {∅} (nonempty)      | ×2        | 2             |
| 3    | {∅} (nonempty)      | ×2        | 4             |
| 4    | ∅ (empty set)       | +1        | 5             |
| 5    | {∅} (nonempty)      | ×2        | 10            |
| 6    | {∅} (nonempty)      | ×2        | 20            |
| 7    | ∅ (empty set)       | +1        | 21            |
| 8    | {∅} (nonempty)      | ×2        | 42            |

The corresponding set:

```
{∅, {∅}, {∅}, ∅, {∅}, {∅}, ∅, {∅}}
```

And the equivalent token sequence (as used in addresses):

```
set sets sets set sets sets set sets
```

Tracing the full computation:

```
r = 0
r →+1  = 1    (∅ / set)
r →×2  = 2    ({∅} / sets)
r →×2  = 4    ({∅} / sets)
r →+1  = 5    (∅ / set)
r →×2  = 10   ({∅} / sets)
r →×2  = 20   ({∅} / sets)
r →+1  = 21   (∅ / set)
r →×2  = 42   ({∅} / sets)
```

The mixed-unary encoding of 42 uses the same +1/×2 pattern
as the binary representation `101010`, but with +1 applied where
the binary bit is 1 and ×2 where it is 0.

## CLI

```
usage: s5 [-h] [--repl] [--bufsize BUFSIZE] [--bufsize_0 BUFSIZE_0]
          [--bufsize_1 BUFSIZE_1] [--bufsize_2 BUFSIZE_2]
          [FILE ...]
```

| Flag | Short | Description |
|------|-------|-------------|
| `--repl` | | Force REPL mode (stderr redirected to stdout) |
| `--bufsize N` | `-b N` | Set IO buffer size for all file descriptors (default: 0) |
| `--bufsize_0 N` | `-b0 N` | Set IO buffer size for stdin / fd 0 |
| `--bufsize_1 N` | `-b1 N` | Set IO buffer size for stdout / fd 1 |
| `--bufsize_2 N` | `-b2 N` | Set IO buffer size for stderr / fd 2 |

Buffer size 0 means no data is retained; writes to an output descriptor still reach the
real file descriptor, but reads from it will return empty (or for fd 0, fall through to
real stdin). Non-zero sizes retain only the tail (last N bytes) of writes.
