# S5 — The Set-Only Language

Every token is a form of `"set"`. All computation is over ordered sets of sets.

## Tokens

| Token     | Kind                                        |
|-----------|---------------------------------------------|
| `Set`     | instruction prefix                          |
| `set`     | difference opcode / integer bit **1** / binary separator |
| `sets`    | union opcode / integer bit **0** / U-address suffix |
| `Set's`   | intersection opcode / base-address prefix   |
| `sets'`   | integer suffix / subset-select suffix       |
| `Sets`    | derived-address / wrap-address / subset-select opcode prefix |

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

<operands>       ::= <subset_operands>
                   | <binary_operands>

<subset_operands> ::= "sets'" <integer>

<binary_operands> ::= <address> <address> "set" <address>

<address>        ::= <base_addr>
                   | <derived_addr>
                   | <wrap_addr>

<base_addr>      ::= "Set's" "sets"       -- Universe U
                   | "Set's" "set"        -- Cache C

<derived_addr>   ::= "Sets" "set" "sets'" <integer>

<wrap_addr>      ::= "Sets" "sets'" <address>

<integer>        ::= ("set" | "sets")*    -- binary, little-endian
```

### Bounded integer (B-operand only)

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

### Integer encoding

Binary little-endian: `"set"` = **1**, `"sets"` = **0**.

| String        | Value |
|---------------|-------|
| `sets`        | 0     |
| `set`         | 1     |
| `set sets`    | 2     |
| `set set`     | 3     |
| `set sets sets` | 4   |
| `set sets set` | 5    |

## Evaluation model

```
for each instruction:
    1. parse          — "Set" <opcode> <operands>
    2. resolve(A, B)  — addresses → S5Set values
    3. compute        — A <op> B  (union / intersection / difference)
    4. assign(D)      — result → destination address (WRAP rejected)
    5. halt check     — if len(U) == 0: H = true, stop
```

- **Subset-select**: `C = C[N]`, 0-indexed. Fails if C is undefined or N out of bounds.
- **Union** (`"sets"`): concatenation (duplicates preserved).
- **Intersection** (`"Set's"`): elements of A that also appear in B (preserves A order).
- **Difference** (`"set"`): elements of A not in B (preserves A order).
- **Wrap** (`"Sets sets'"`): wraps the resolved inner address into a singleton set `{value}`. Read-only — cannot be used as destination.

## Simple cases

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

After `Sets set sets'`: start integer parsing. `set` = bit 1 → value=1. Next is `sets` = bit 0 → value=2. Next is `set` — bounded lookahead: after this `set` would `"Set's"` or `"Sets"` follow? Next token is `Set's sets` (D address). So `Set's` follows → yes, address follows → stop at the `set` without consuming. Return integer = 2.

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

## Computing 42

Program that grows U to size 42. The first instruction seeds C = {∅}, then
each subsequent instruction doubles U (U ∪ U) or increments by one (U ∪ C[0]):

| Instr | Op          | Size of U after |
|-------|-------------|-----------------|
| 1     | C = U ∩ U   | 1 (unchanged)   |
| 2     | U = U ∪ U   | 2                |
| 3     | U = U ∪ U   | 4                |
| 4     | U = U ∪ C[0] | 5               |
| 5     | U = U ∪ U   | 10               |
| 6     | U = U ∪ U   | 20               |
| 7     | U = U ∪ C[0] | 21              |
| 8     | U = U ∪ U   | 42               |

```
Set Set's Set's sets Set's sets set Set's set
Set sets Set's sets Set's sets set Set's sets
Set sets Set's sets Set's sets set Set's sets
Set sets Set's sets Set's set set Set's sets
Set sets Set's sets Set's sets set Set's sets
Set sets Set's sets Set's sets set Set's sets
Set sets Set's sets Set's set set Set's sets
Set sets Set's sets Set's sets set Set's sets
```

### Trace of instruction 4 (increment by one)

```
Set sets Set's sets Set's set set Set's sets
│   │    │      │   │      │   │   │      │
│   │    │      │   │      │   │   └──────┴── D = U
│   │    │      │   │      │   └───── separator
│   │    │      │   └──────┴───────── B = C (Set's set)
│   │    └──────┴──────────────────── A = U (Set's sets)
│   └──────────────────────────────── opcode = "sets" (union)
└──────────────────────────────────── instruction start
```

```
resolve(A)=U={∅,∅,∅,∅} (size 4)
resolve(B)=C={∅}         (size 1)
result = U ∪ C = 4 ∪ 1 = 5 elements
assign(D=U): U has size 5
```

Binary pattern for 42: `101010` = (1×2+0)×2+1... The actual sequence
is: 1, 2, 4, 5, 10, 20, 21, 42. This is: ×2, ×2, +1, ×2, ×2, +1, ×2.
42 = ((((1×2)×2+1)×2)×2+1)×2 = 42.
