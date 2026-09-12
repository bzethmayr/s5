"""Generate ctag.s5 — a bounded Cyclic Tag interpreter written in S5.

Instantiates a fixed Cyclic Tag machine (a finite list of productions plus
an initial data word) as a straight-line S5 program running over a fixed
linear bit buffer.

REQUIRES (prior, in the same universe, in this order):
    arithmetic/init.s5   — grows U to 32 and installs ZERO (U[0]) / ONE (U[1])
    arithmetic/succ.s5   — installs the SUCC structure (U[6][0] = NORM_SUCC)

Operational notes
-----------------
* A "tick" of STEP reads the current head bit out of the word, deletes it
  by advancing the head pointer, conditionally appends production P[m] by
  advancing the tail pointer, advances the production index mod n, then
  re-enters itself while the word is non-empty.
* Head and tail pointers PH / PT are *canonical* mixed-unary values; a
  depth-2 U-address dispatches through them so the buffer is indexed at
  runtime (see PLAN.md).
* Results: after the program finishes, U[38]=PH and U[39]=PT are equal (the
  word is empty) and U[44] holds the number of ticks executed.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from s5 import Address, AddressType, Instruction, Opcode, int_to_s5set
from s5.pretty import pretty_print

from reference import steps, buffer_usage

# --- slot map (assumes U grown to 128 by the generated code) -------------
ZERO = 0       # ∅ (value 0), from arithmetic init
ONE = 1        # {∅} (value 1), from arithmetic init
IN_A = 3       # NORM_SUCC input register
SUCC = 6       # NORM_SUCC structure (U[6][0])
CTAG = 32      # [0]=STEP [1]=DISPATCH_APPEND [2]=RESET_PM
PROD = 33      # [k]=APPEND_P[k]
BIT = 34       # current head bit (∅ or {∅})
CONT = 35      # non-empty iff PH != PT (word non-empty)
EQN = 36       # non-empty iff succ(PM) == n (production wrap)
TMP = 37       # scratch: succ(PM)
PH = 38        # head pointer (canonical value bias + h)
PT = 39        # tail pointer (canonical value bias + t)
PM = 40        # production index (canonical 0..n-1)
N_CANON = 41   # canonical n (number of productions)
BIAS_CANON = 42  # canonical bias (first buffer slot index)
SC = 44        # tick counter

DEFAULT_BIAS = 64
DEFAULT_N = 48


def U():
    return Address(AddressType.U)


def C():
    return Address(AddressType.C)


def UD(i):
    return Address(AddressType.UD, index=i)


def WRAP(a):
    return Address(AddressType.WRAP, sub_addr=a)


def DEPTH2(a):
    """Runtime-indexed U access keyed by the value of a pointer slot."""
    a.dispatch_depth = 2
    a.has_depth = True
    return a


def union_(a, b, d):
    return Instruction(Opcode.UNION, addr_a=a, addr_b=b, addr_dest=d)


def inters(a, b, d):
    return Instruction(Opcode.INTERSECTION, addr_a=a, addr_b=b, addr_dest=d)


def diff_(a, b, d):
    return Instruction(Opcode.DIFFERENCE, addr_a=a, addr_b=b, addr_dest=d)


def subset(n=None, addr=None):
    if addr is not None:
        return Instruction(Opcode.SUBSET_SELECT, addr_b=addr)
    return Instruction(Opcode.SUBSET_SELECT, n=n)


def subr_decl(body, loc=None):
    return Instruction(Opcode.SUBR, subr_body=body, addr_a=loc)


def subr_call(loc=None, cond=None):
    return Instruction(Opcode.SUBR, addr_a=loc, addr_b=cond)


def emit_const(value, dest_slot):
    """Build the canonical set with value `value` in C, store to U[dest_slot].

    Appending an element of a set via union requires wrapping it (union
    concatenates element lists, so a bare ZERO/ONE operand would append
    nothing / an empty set respectively).  The canonical integer encoding
    is scanned MSB-first: a 1-bit is a ZERO element, a 0-bit is ONE.
    """
    instrs = [inters(UD(ZERO), UD(ZERO), C())]      # C = ∅
    for elem in int_to_s5set(value):
        slot = ZERO if len(elem) == 0 else ONE
        instrs.append(union_(C(), WRAP(UD(slot)), C()))
    instrs.append(inters(C(), C(), UD(dest_slot)))
    return instrs


def emit_incr(src_slot, dest_slot):
    """dest_slot := succ(src_slot), canonicalised via NORM_SUCC (U[6][0])."""
    return [
        inters(UD(src_slot), UD(src_slot), UD(IN_A)),   # IN_A = src
        inters(UD(SUCC), UD(SUCC), C()),                # C = SUCC
        subset(0),                                      # C = NORM_SUCC
        subr_call(),                                    # OUT = succ(IN_A); C = OUT
        inters(C(), C(), UD(dest_slot)),                # dest = C
    ]


def build_ctag(productions, initial_data, bias=DEFAULT_BIAS, n=DEFAULT_N,
               print_steps=False):
    """Return the S5 instruction list realising the given cyclic tag machine.

    Raises ValueError if the machine's run would exceed the buffer size.
    """
    if len(productions) == 0:
        raise ValueError("need at least one production")
    expected_steps = steps(productions, initial_data)
    total = buffer_usage(productions, initial_data)
    last_slot = bias + total - 1
    if last_slot >= bias + n:
        raise ValueError(
            f"machine run needs {total} buffer slots "
            f"(bias {bias}, last slot {last_slot}, capacity {n})"
        )

    instrs = []

    # Grow the universe 32 -> 64 -> 128 (our slots and buffer live up to 112).
    instrs.append(union_(U(), U(), U()))
    instrs.append(union_(U(), U(), U()))

    # Make sure C is defined (it may be a leftover SubroutineSet from succ.s5,
    # or anything at all -- intersecting with ONE pins it to {∅}).
    instrs.append(inters(UD(ONE), UD(ONE), C()))

    # Growing U by self-union duplicates the *entire* current universe, so
    # slots 32..63 hold copies of the arithmetic slots (e.g. U[33] is a copy
    # of ONE).  The accumulating structure slots must start empty.
    instrs.append(inters(UD(ZERO), UD(ZERO), UD(CTAG)))
    instrs.append(inters(UD(ZERO), UD(ZERO), UD(PROD)))

    # Canonical constants and registers.
    instrs += emit_const(bias, PH)
    instrs += emit_const(bias + len(initial_data), PT)
    instrs += emit_const(len(productions), N_CANON)
    instrs += emit_const(bias, BIAS_CANON)
    instrs.append(inters(UD(ZERO), UD(ZERO), UD(PM)))
    instrs.append(inters(UD(ZERO), UD(ZERO), UD(SC)))

    # Initial data word into buffer slots bias..bias+L-1.
    for j, ch in enumerate(initial_data):
        b = 1 if ch == "1" else 0
        instrs.append(inters(UD(b), UD(b), UD(bias + j)))

    # ---- STEP: one tick of the machine -----------------------------------
    step = []
    step += emit_incr(SC, SC)                            # tick counter
    step.append(inters(DEPTH2(UD(PH)), DEPTH2(UD(PH)), UD(BIT)))  # BIT = U[PH]
    step += emit_incr(PH, PH)                            # delete head bit
    step.append(inters(UD(CTAG), UD(CTAG), C()))         # C = CTAG
    step.append(subset(1))                               # C = DISPATCH_APPEND
    step.append(subr_call(cond=UD(BIT)))                 # if head==1: append P[m]
    step += emit_incr(PM, TMP)                           # TMP = succ(PM)
    step.append(inters(WRAP(UD(TMP)), WRAP(UD(N_CANON)), UD(EQN)))  # EQN iff ==n
    step.append(inters(UD(TMP), UD(TMP), UD(PM)))        # PM = TMP
    step.append(inters(UD(CTAG), UD(CTAG), C()))         # C = CTAG
    step.append(subset(2))                               # C = RESET_PM
    step.append(subr_call(cond=UD(EQN)))                 # if PM==n: PM = ZERO
    step.append(diff_(WRAP(UD(PH)), WRAP(UD(PT)), UD(CONT)))  # CONT iff PH!=PT
    step.append(inters(UD(CTAG), UD(CTAG), C()))         # C = CTAG
    step.append(subset(0))                               # C = STEP
    step.append(subr_call(cond=UD(CONT)))                # loop while non-empty

    # ---- DISPATCH_APPEND: select production P[m] by runtime index ---------
    dispatch = [
        inters(UD(PROD), UD(PROD), C()),                 # C = PROD
        subset(addr=UD(PM)),                             # C = PROD[value(PM)]
        subr_call(),
    ]

    # ---- RESET_PM: production pointer wraps to zero ------------------------
    reset = [inters(UD(ZERO), UD(ZERO), UD(PM))]

    # Build the CTAG structure: STEP, DISPATCH_APPEND, RESET_PM.
    for body in (step, dispatch, reset):
        instrs.append(subr_decl(body))
        instrs.append(union_(UD(CTAG), WRAP(C()), UD(CTAG)))

    # Build the PROD structure: one append routine per production.
    for prod in productions:
        body = []
        for ch in prod:
            b = 1 if ch == "1" else 0
            body.append(inters(UD(b), UD(b), DEPTH2(UD(PT))))  # U[PT] = bit
            body += emit_incr(PT, PT)                          # PT = succ(PT)
        instrs.append(subr_decl(body))
        instrs.append(union_(UD(PROD), WRAP(C()), UD(PROD)))

    # ---- entry: run STEP while the initial word is non-empty ---------------
    instrs.append(diff_(WRAP(UD(PH)), WRAP(UD(PT)), UD(CONT)))
    instrs.append(inters(UD(CTAG), UD(CTAG), C()))
    instrs.append(subset(0))
    instrs.append(subr_call(cond=UD(CONT)))

    if print_steps:
        from s5 import Address as _A, AddressType as _T
        io_out = _A(_T.IO)
        io_out.dispatch_depth = 2
        io_out.has_depth = True
        instrs.append(inters(UD(SC), UD(SC), io_out))          # print step count

    return instrs


def main():
    productions = ["0", ""]
    initial_data = "101"
    instrs = build_ctag(productions, initial_data, print_steps=True)
    out = pretty_print(instrs)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ctag.s5")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"Wrote {path}  ({len(instrs)} instrs)")
    print(f"A machine P={productions} data={initial_data!r}: "
          f"{steps(productions, initial_data)} ticks")


if __name__ == "__main__":
    main()