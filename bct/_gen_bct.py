"""Generate bct.s5 — a constant-size, runtime Bitwise-Cyclic-Tag interpreter.

One S5 program, independent of any particular BCT machine, that reads a BCT
instance from stdin (fd 0) and runs it to completion with an *unbounded*
data buffer (the universe U itself grows at runtime, one slot per appended
bit).  It prints the number of ticks on stdout (fd 1).

Input protocol (integer lines on stdin):
    plen
    program bits, one per line  (plen lines, each '0' or '1')
    dlen
    data bits, one per line     (dlen lines, each '0' or '1')

REQUIRES (prior, in the same universe, in this order):
    arithmetic/init.s5   — grows U to 32 and installs ZERO (U[0]) / ONE (U[1])
    arithmetic/succ.s5   — installs SUCC structure (U[6][0] = NORM_SUCC)

Design (full discussion in PLAN.md):
* BCT is the cyclic-tag model where every production is one bit: the program
  is a cyclic string; a tick deletes the data head bit and, if it was 1,
  appends the current program bit to the data; the program head then
  advances cyclically.
* Program bits are stored in a runtime-grown U region [P_BASE, P_BASE+plen);
  data follows immediately, so D_BASE = P_BASE + plen doubles as the program
  pointer's wrap bound (PP := succ(PP); if PP == D_BASE: PP := P_BASE).
* The data buffer is linear and unbounded: each append grows U by one slot
  (U := U ∪ {∅}) before writing U[DT], then advances DT.  No 48-slot cap.
* The interpreter body is entirely structure-driven (STR = U[29]) and
  constant-size: READ_LOOP, APPEND, STEP, RESET_PP.  No production-specific
  code is generated at all.

I/O discipline (important): the BCT input is read through *raw* (non-fd)
IO addresses, which read sys.stdin directly and never touch the fd-0 buffer
that NORM_SUCC uses for its normalization round-trips.  This keeps the two
streams disjoint so increments may interleave with input reads.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from s5 import Address, AddressType, Instruction, Opcode, int_to_s5set
from s5.pretty import pretty_print

# --- environment slots (from arithmetic init/succ) ------------------------
ZERO = 0    # ∅ (value 0)
ONE = 1     # {∅} (value 1)
IN_A = 3    # NORM_SUCC input register
SUCC = 6    # NORM_SUCC structure (U[6][0])

# --- interpreter registers (slots 17..30 are free in the 32-slot U) -------
PP = 17     # program pointer (absolute slot index, canonical)
PLEN = 18   # count bound, reused for program load and data load
I = 19      # loop counter (0..PLEN)
W = 20      # write pointer (next slot to fill)
DH = 21     # data head pointer
DT = 22     # data tail pointer
BIT = 23    # current data-head bit
SC = 24     # tick counter (result)
CONT = 25   # non-empty iff DH != DT (word non-empty)
EQN = 26    # loop/wrap condition scratch
TMP = 27    # scratch: succ(PP)
PBOUND = 28 # program wrap bound (= P_BASE + plen = D_BASE)
STR = 29    # interpreter structure: [0]=READ_LOOP [1]=APPEND [2]=STEP [3]=RESET_PP
PBC = 30    # canonical P_BASE (first program slot index)

P_BASE = 32  # program region begins here; data follows immediately


# --- address/instruction builders ----------------------------------------
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


def IO_R():
    """Raw stdin read: IO address that bypasses the fd buffer."""
    return Address(AddressType.IO)


def IO_W():
    """fd 1 write (prints the value)."""
    addr = Address(AddressType.IO, dispatch_depth=2)
    addr.has_depth = True
    return addr


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
    """Build the canonical set with value `value` in C, store to U[dest_slot]."""
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


def load_subr(select):
    return [inters(UD(STR), UD(STR), C()), subset(select)]


def build_interpreter():
    """Return the constant-size BCT interpreter instruction list."""
    instrs = []

    instrs.append(inters(UD(ONE), UD(ONE), C()))          # C safe

    # ---- READ_LOOP (U[STR][0]): consume one input bit, write it at U[W] --
    read_loop = [
        union_(IO_R(), UD(ZERO), C()),                      # C = input line
        union_(U(), WRAP(UD(ZERO)), U()),                   # grow U by one slot
        inters(C(), C(), DEPTH2(UD(W))),                    # U[W] = C
        *emit_incr(W, W),
        *emit_incr(I, I),
        diff_(WRAP(UD(PLEN)), WRAP(UD(I)), UD(EQN)),        # EQN iff I != PLEN
        *load_subr(0),
        subr_call(cond=UD(EQN)),                            # recurse while I != PLEN
    ]

    # ---- APPEND (U[STR][1]): write the current program bit at U[DT] ------
    append = [
        inters(DEPTH2(UD(PP)), DEPTH2(UD(PP)), C()),        # C = U[PP]
        union_(U(), WRAP(UD(ZERO)), U()),                   # grow U by one slot
        inters(C(), C(), DEPTH2(UD(DT))),                   # U[DT] = C
        *emit_incr(DT, DT),
    ]

    # ---- RESET_PP (U[STR][3]): program pointer wraps to P_BASE -----------
    reset_pp = [inters(UD(PBC), UD(PBC), UD(PP))]

    # ---- STEP (U[STR][2]): one BCT tick (entry guards word non-empty) ----
    step = [
        inters(DEPTH2(UD(DH)), DEPTH2(UD(DH)), UD(BIT)),    # BIT = U[DH]
        *emit_incr(DH, DH),                                 # delete head bit
        *load_subr(1),
        subr_call(cond=UD(BIT)),                            # if BIT: APPEND
        *emit_incr(PP, TMP),                                # TMP = succ(PP)
        inters(WRAP(UD(TMP)), WRAP(UD(PBOUND)), UD(EQN)),   # EQN iff TMP == PBOUND
        inters(UD(TMP), UD(TMP), UD(PP)),                   # PP = TMP
        *load_subr(3),
        subr_call(cond=UD(EQN)),                            # if EQN: RESET_PP
        *emit_incr(SC, SC),                                 # ticks += 1
        diff_(WRAP(UD(DH)), WRAP(UD(DT)), UD(CONT)),        # CONT iff word non-empty
        *load_subr(2),
        subr_call(cond=UD(CONT)),                           # recurse STEP
    ]

    # Build STR = [READ_LOOP, APPEND, STEP, RESET_PP].
    for body in (read_loop, append, step, reset_pp):
        instrs.append(subr_decl(body))
        instrs.append(union_(UD(STR), WRAP(C()), UD(STR)))

    # ---- entry -------------------------------------------------------------
    instrs += emit_const(P_BASE, PBC)                       # PBC = 32
    instrs.append(inters(UD(PBC), UD(PBC), UD(W)))          # W = P_BASE
    instrs.append(inters(UD(PBC), UD(PBC), UD(PP)))         # PP = P_BASE
    instrs.append(inters(UD(ZERO), UD(ZERO), UD(I)))        # I = 0
    instrs.append(inters(UD(ZERO), UD(ZERO), UD(SC)))       # SC = 0

    # read plen -> PLEN, then load plen program bits
    instrs.append(union_(IO_R(), UD(ZERO), UD(PLEN)))
    instrs.append(diff_(WRAP(UD(PLEN)), WRAP(UD(I)), UD(EQN)))
    instrs += load_subr(0) + [subr_call(cond=UD(EQN))]

    # D_BASE = P_BASE + plen == W now; also the wrap bound for PP
    instrs.append(inters(UD(W), UD(W), UD(PBOUND)))
    instrs.append(inters(UD(W), UD(W), UD(DH)))
    instrs.append(inters(UD(W), UD(W), UD(DT)))

    # read dlen -> PLEN, then append dlen data bits starting at U[DT]
    instrs.append(union_(IO_R(), UD(ZERO), UD(PLEN)))
    instrs.append(inters(UD(ZERO), UD(ZERO), UD(I)))        # I = 0
    instrs.append(diff_(WRAP(UD(PLEN)), WRAP(UD(I)), UD(EQN)))
    instrs += load_subr(0) + [subr_call(cond=UD(EQN))]
    instrs.append(inters(UD(W), UD(W), UD(DT)))             # DT = D_BASE + dlen

    # run STEP while the word is non-empty
    instrs.append(diff_(WRAP(UD(DH)), WRAP(UD(DT)), UD(CONT)))
    instrs += load_subr(2) + [subr_call(cond=UD(CONT))]

    # print the tick count on stdout
    instrs.append(inters(UD(SC), UD(SC), IO_W()))

    return instrs


def main():
    instrs = build_interpreter()
    out = pretty_print(instrs)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bct.s5")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"Wrote {path}  ({len(instrs)} instrs)")
    print("A constant-size BCT interpreter; reads plen/bits/dlen/bits on stdin.")


if __name__ == "__main__":
    main()