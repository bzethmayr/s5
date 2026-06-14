"""Generate init.s5 with correct universe size.

Grows U to 32 (5 doublings), then reads COUNTER, sets ZERO and ONE.

After init: U[0]=ZERO=∅, U[1]=ONE, U[2]=COUNTER, U[3..31]=∅ (from growth)

ZERO is ∅ (empty set) so that ZERO ∪ ONE = {∅} (value 1), giving correct successor.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from s5 import Address, AddressType, Opcode, Instruction
from s5.pretty import pretty_print

def U(): return Address(AddressType.U)
def C(): return Address(AddressType.C)
def UD(i): return Address(AddressType.UD, index=i)
def WRAP(a): return Address(AddressType.WRAP, sub_addr=a)

def IO(depth=1):
    a = Address(AddressType.IO)
    a.dispatch_depth = depth
    a.has_depth = True
    return a

def inters(a,b,d): return Instruction(Opcode.INTERSECTION, addr_a=a, addr_b=b, addr_dest=d)
def union_(a,b,d): return Instruction(Opcode.UNION, addr_a=a, addr_b=b, addr_dest=d)

instrs = [
    # 0: C = U ∩ U (save ONE = {∅} before growth)
    inters(U(), U(), C()),
]

# 1-5: U = U ∪ U (5 doublings: 1→2→4→8→16→32)
N_GROWTH = 5
for _ in range(N_GROWTH):
    instrs.append(union_(U(), U(), U()))

# After growth: U has 32 elements, all ∅.
# U[0] is already ∅ — it becomes ZERO.

# Write COUNTER (universe size = 32) to fd 1 buffer
instrs.append(inters(U(), U(), IO(2)))  # U ∩ U → IO'2 (writes to fd1 buffer)

# Read back COUNTER from fd 1 buffer into U[2]
instrs.append(union_(IO(2), UD(4), UD(2)))  # U[2] = IO'2 ∪ U[4]

# ZERO = U[0] = ∅ (already ∅ after growth, no change needed)

# Copy ONE (still in C) to U[1]
instrs.append(inters(C(), C(), UD(1)))  # U[1] = C ∩ C

out = pretty_print(instrs)
print(out)

path = os.path.join(os.path.dirname(__file__), 'init.s5')
with open(path, 'w', encoding='utf-8') as f:
    f.write(out)
print(f"Wrote {path}  ({len(instrs)} instrs)")
