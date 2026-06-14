"""Generate pred1.s5 — LUT-based predecessor builder.

Builds LUT in U[16] for ALL valid decrements 0..COUNTER-1 (COUNTER = U[2])
by calling PRED_MAIN for each V.  The LUT is a pure data set (no subroutines
mixed in) that can be copied to any other U slot and re-used.

Element at index V holds pred(V) — use SUBSET_SELECT(V) for compile-time V.
For runtime pred(Q) where Q varies, use PRED_MAIN (U[7][0]) as before; the
LUT functions as a portable reference table.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from s5 import Address, AddressType, Opcode, Instruction
from s5.pretty import pretty_print

def U():   return Address(AddressType.U)
def C():   return Address(AddressType.C)
def UD(i): return Address(AddressType.UD, index=i)
def WRAP(a): return Address(AddressType.WRAP, sub_addr=a)

def inters(a, b, d): return Instruction(Opcode.INTERSECTION, addr_a=a, addr_b=b, addr_dest=d)
def diff_(a, b, d):  return Instruction(Opcode.DIFFERENCE, addr_a=a, addr_b=b, addr_dest=d)
def union_(a, b, d): return Instruction(Opcode.UNION, addr_a=a, addr_b=b, addr_dest=d)
def subset(n):       return Instruction(Opcode.SUBSET_SELECT, n=n)
def subr_decl(body, loc=None): return Instruction(Opcode.SUBR, subr_body=body, addr_a=loc)
def subr_call(loc=None, cond=None): return Instruction(Opcode.SUBR, addr_a=loc, addr_b=cond)

# Slot assignments:
#   U[0]=ZERO  U[1]=ONE  U[2]=COUNTER  U[3]=IN_A  U[4]=IN_B
#   U[5]=OUT   U[6]=SUCC  U[7]=PRED (search-based, unchanged)
#   U[8]=pred scratch
#   U[11]=V (build loop counter)
#   U[12]=PRED1 subroutines (PRED1_BUILD + LUT_BUILD_LOOP)
#   U[13]=scratch (COND)
#   U[14]=bound
#   U[15]=zero source
#   U[16]=LUT data (pure pred values, no subroutines)

all_instrs = []

def add_subr(body):
    all_instrs.append(subr_decl(body))
    all_instrs.append(union_(UD(12), WRAP(C()), UD(12)))

# =====================
# PRED1_BUILD (U[12][0]): entry point — build LUT in U[16] for 0..COUNTER-1
# =====================
pred1_build = [
    # Get ∅ source
    diff_(C(), C(), UD(15)),                # U[15] = ∅

    # Store pred(0) = ZERO in LUT
    inters(UD(0), UD(0), C()),              # C = ZERO
    union_(UD(16), WRAP(C()), UD(16)),      # U[16] = {pred(0)}

    # V = ONE (start from 1, pred(0) already stored)
    inters(UD(1), UD(1), UD(11)),           # V = ONE

    # bound = COUNTER
    inters(UD(2), UD(2), UD(14)),           # U[14] = COUNTER

    # Call LUT_BUILD_LOOP
    inters(UD(12), UD(12), C()),            # C = U[12]
    subset(1),                               # C = C[1] = LUT_BUILD_LOOP
    subr_call(),
]
add_subr(pred1_build)

# =====================
# LUT_BUILD_LOOP (U[12][1]): for V in 1..COUNTER-1:
#   pred(V) = PRED_MAIN(V), append, V = succ(V)
# =====================
lut_build_loop = [
    # Call PRED_MAIN(V) — result in U[5]
    inters(UD(11), UD(11), UD(3)),          # IN_A = V
    inters(UD(7), UD(7), C()),              # C = U[7]
    subset(0),                               # C = C[0] = PRED_MAIN
    subr_call(),                             # U[5] = pred(V)

    # Append result to U[16]
    inters(UD(5), UD(5), C()),              # C = result
    union_(UD(16), WRAP(C()), UD(16)),      # U[16] = U[16] ∪ {pred(V)}

    # V = succ(V) via NORM_SUCC
    inters(UD(11), UD(11), UD(3)),          # IN_A = V
    inters(UD(6), UD(6), C()),              # C = U[6]
    subset(0),                               # C = C[0] = NORM_SUCC
    subr_call(),                             # U[5] = succ(V)
    inters(UD(5), UD(5), UD(11)),           # V = succ(V)

    # Check if V == bound
    diff_(WRAP(UD(14)), WRAP(UD(11)), UD(13)),  # scratch = {bound} \ {V}

    # Recurse if V != bound
    inters(UD(12), UD(12), C()),            # C = U[12]
    subset(1),                               # C = C[1] = LUT_BUILD_LOOP (self)
    subr_call(cond=UD(13)),                 # recurse if V != bound
]
add_subr(lut_build_loop)

# ===== Entry: call PRED1_BUILD =====
all_instrs.append(inters(UD(12), UD(12), C()))
all_instrs.append(subset(0))
all_instrs.append(subr_call())

out = pretty_print(all_instrs)
print(out)

path = os.path.join(os.path.dirname(__file__), 'pred1.s5')
with open(path, 'w', encoding='utf-8') as f:
    f.write(out)
print(f"Wrote {path}  ({len(all_instrs)} instrs)")
