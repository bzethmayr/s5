"""Generate succ.s5 - successor structure with NORM_SUCC, UGROWTH, and NORM."""
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

def union(a,b,d):  return Instruction(Opcode.UNION, addr_a=a, addr_b=b, addr_dest=d)
def inters(a,b,d): return Instruction(Opcode.INTERSECTION, addr_a=a, addr_b=b, addr_dest=d)
def diff_(a,b,d):  return Instruction(Opcode.DIFFERENCE, addr_a=a, addr_b=b, addr_dest=d)
def subset(n):     return Instruction(Opcode.SUBSET_SELECT, n=n)
def subr_decl(body, loc=None): return Instruction(Opcode.SUBR, subr_body=body, addr_a=loc)
def subr_call(loc=None, cond=None): return Instruction(Opcode.SUBR, addr_a=loc, addr_b=cond)

# U[6][0] = NORM_SUCC: normalize IN_A = OUT = canonicalize(IN_A + 1)
# C = IN_A ∪ ONE; write C to IO fd0; zero C; read C from IO fd0; C → OUT
norm_succ = [
    union(UD(3), UD(1), C()),           # C = IN_A ∪ ONE
    inters(C(), C(), IO(1)),            # write C to fd0 (normalize)
    diff_(C(), C(), C()),                # C = ∅
    union(IO(1), C(), C()),             # read back from fd0 → C
    inters(C(), C(), UD(5)),            # U[5] = C (OUT)
]

# U[6][1] = UGROWTH: U = U ∪ ONE; COUNTER = normalize(COUNTER + 1)
ugrowth = [
    union(U(), UD(1), U()),             # U = U ∪ ONE
    union(UD(2), UD(1), C()),           # C = COUNTER ∪ ONE
    inters(C(), C(), IO(1)),            # write C to fd0 (normalize)
    diff_(C(), C(), C()),                # C = ∅
    union(IO(1), C(), C()),             # read back from fd0 → C
    inters(C(), C(), UD(2)),            # U[2] = C (update COUNTER)
]

# U[6][2] = NORM: normalize IN_A = OUT = canonicalize(IN_A)
norm = [
    inters(UD(3), UD(3), C()),          # C = IN_A
    inters(C(), C(), IO(1)),            # write C to fd0 (normalize)
    diff_(C(), C(), C()),                # C = ∅
    union(IO(1), C(), C()),             # read back from fd0 → C
    inters(C(), C(), UD(5)),            # U[5] = C (OUT)
]

instrs = []
for body in [norm_succ, ugrowth, norm]:
    instrs.append(subr_decl(body))
    instrs.append(union(UD(6), WRAP(C()), UD(6)))

out = pretty_print(instrs)
print(out)

path = os.path.join(os.path.dirname(__file__), 'succ.s5')
with open(path, 'w', encoding='utf-8') as f:
    f.write(out)
print(f"Wrote {path}  ({len(instrs)} instrs)")
