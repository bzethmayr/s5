"""Generate demo.s5 — simple pred demo.

Reads an integer Q from stdin, computes predecessor via PRED_MAIN (U[7][0]),
outputs result to stdout, and loops until invalid/EOF input is hit.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from s5 import Address, AddressType, Opcode, Instruction
from s5.pretty import pretty_print

def U():   return Address(AddressType.U)
def C():   return Address(AddressType.C)
def UD(i): return Address(AddressType.UD, index=i)
def WRAP(a): return Address(AddressType.WRAP, sub_addr=a)

def IO(depth=1):
    a = Address(AddressType.IO); a.dispatch_depth = depth; a.has_depth = True; return a

def inters(a, b, d): return Instruction(Opcode.INTERSECTION, addr_a=a, addr_b=b, addr_dest=d)
def union_(a, b, d): return Instruction(Opcode.UNION, addr_a=a, addr_b=b, addr_dest=d)
def diff_(a, b, d):  return Instruction(Opcode.DIFFERENCE, addr_a=a, addr_b=b, addr_dest=d)
def subset(n):       return Instruction(Opcode.SUBSET_SELECT, n=n)
def subr_decl(body, loc=None): return Instruction(Opcode.SUBR, subr_body=body, addr_a=loc)
def subr_call(loc=None, cond=None): return Instruction(Opcode.SUBR, addr_a=loc, addr_b=cond)

# U[13] holds demo subroutines (U[12] is used by pred1.s5)
DEMO_SLOT = 13
all_instrs = []

def add_subr(body):
    all_instrs.append(subr_decl(body))
    all_instrs.append(union_(UD(DEMO_SLOT), WRAP(C()), UD(DEMO_SLOT)))

# Slot assignments:
# U[0]=ZERO, U[1]=ONE, U[2]=COUNTER, U[3]=IN_A, U[4]=IN_B, U[5]=OUT
# U[6]=SUCC, U[7]=PRED+LUT, U[8]=pred scratch
# U[9]=MAX (set by pred1.s5), U[10]=QUERY
# U[12]=PRED1 subrs (pred1.s5), U[13]=DEMO subrs

# =====================
# DEMO_MAIN (U[13][0]): read Q, pred(Q), output — single pass
# =====================
demo_main = [
    # Read Q from stdin
    union_(IO(1), UD(0), UD(10)),           # U[10] = Q

    # Call PRED_MAIN(Q)
    inters(UD(10), UD(10), UD(3)),          # IN_A = Q
    inters(UD(7), UD(7), C()),              # C = U[7]
    subset(0),                               # C = C[0] = PRED_MAIN
    subr_call(),                             # U[5] = pred(Q)

    # Output result to stdout
    inters(UD(5), UD(5), C()),              # C = result
    inters(C(), C(), IO(2)),                 # write to stdout (fd 1)
]
add_subr(demo_main)

# ===== Entry: call DEMO_MAIN =====
all_instrs.append(inters(UD(DEMO_SLOT), UD(DEMO_SLOT), C()))
all_instrs.append(subset(0))
all_instrs.append(subr_call())

out = pretty_print(all_instrs)
print(out)

path = os.path.join(os.path.dirname(__file__), 'demo.s5')
with open(path, 'w', encoding='utf-8') as f:
    f.write(out)
print(f"Wrote {path}  ({len(all_instrs)} instrs)")
