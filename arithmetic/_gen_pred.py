"""Generate pred.s5 — search-based predecessor under U[7]."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from s5 import Address, AddressType, Opcode, Instruction
from s5.pretty import pretty_print

def U():   return Address(AddressType.U)
def C():   return Address(AddressType.C)
def UD(idx): return Address(AddressType.UD, index=idx)
def WRAP(addr): return Address(AddressType.WRAP, sub_addr=addr)

def union(a, b, d):
    return Instruction(Opcode.UNION, addr_a=a, addr_b=b, addr_dest=d)
def intersection(a, b, d):
    return Instruction(Opcode.INTERSECTION, addr_a=a, addr_b=b, addr_dest=d)
def diff(a, b, d):
    return Instruction(Opcode.DIFFERENCE, addr_a=a, addr_b=b, addr_dest=d)
def subset(n):
    return Instruction(Opcode.SUBSET_SELECT, n=n)
def subr_decl(body, loc=None):
    return Instruction(Opcode.SUBR, subr_body=body, addr_a=loc)
def subr_call(loc=None, cond=None):
    return Instruction(Opcode.SUBR, addr_a=loc, addr_b=cond)

# PRED_MAIN (U[7][0]): save IN_A, init test/prev, call PRED_ADVANCE
# If IN_A is ∅, skip loop and return ZERO (prev is already ZERO from init).
pred_main = [
    intersection(UD(3), UD(3), UD(4)),  # U[4] = save IN_A
    intersection(UD(0), UD(0), UD(3)),  # test = ZERO
    intersection(UD(0), UD(0), UD(8)),  # prev = ZERO (U[8] scratch)
    intersection(UD(7), UD(7), C()),    # C = U[7]
    subset(1),                          # C = C[1] = PRED_ADVANCE
    subr_call(cond=UD(4)),             # if IN_A non-empty: call C (PRED_ADVANCE)
    intersection(UD(8), UD(8), UD(5)),  # OUT = prev (fallthrough for IN_A=∅)
]

# PRED_ADVANCE (U[7][1]): if test!=IN_A call PRED_STEP; else set OUT=prev
pred_advance = [
    diff(WRAP(UD(3)), WRAP(UD(4)), UD(5)),  # COND
    intersection(UD(7), UD(7), C()),          # C = U[7]
    subset(2),                                # C = C[2] = PRED_STEP
    subr_call(cond=UD(5)),                   # if COND: call C
    intersection(UD(8), UD(8), UD(5)),       # OUT = prev
]

# PRED_STEP (U[7][2]): prev=test, test=succ(test), recurse
pred_step = [
    intersection(UD(3), UD(3), UD(8)),  # prev = test
    intersection(UD(6), UD(6), C()),     # C = U[6]
    subset(0),                           # C = C[0] = NORM_SUCC
    subr_call(),                         # call succ → U[5]=result
    intersection(UD(5), UD(5), UD(3)),  # test = result
    intersection(UD(7), UD(7), C()),    # C = U[7]
    subset(1),                           # C = C[1] = PRED_ADVANCE
    subr_call(),                         # call PRED_ADVANCE
]

instrs = []
instrs.append(subr_decl(pred_main))
instrs.append(union(UD(7), WRAP(C()), UD(7)))
instrs.append(subr_decl(pred_advance))
instrs.append(union(UD(7), WRAP(C()), UD(7)))
instrs.append(subr_decl(pred_step))
instrs.append(union(UD(7), WRAP(C()), UD(7)))

out = pretty_print(instrs)
print(out)

path = os.path.join(os.path.dirname(__file__), 'pred.s5')
with open(path, 'w', encoding='utf-8') as f:
    f.write(out)
print(f"Wrote {path}  ({len(instrs)} instrs)")
