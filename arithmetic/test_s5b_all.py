"""Test: what if we put ALL instruction bytes in buffer at once?"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from s5 import (
    Opcode, Instruction, Address, AddressType,
    SubroutineSet, int_to_s5set,
)
from s5.io_handler import IOHandler
from s5.serialize import serialize_body
from s5.binary import encode_tokens

def U(): return Address(AddressType.U)
def C(): return Address(AddressType.C)
def UD(i): return Address(AddressType.UD, index=i)
def inters(a, b, d):
    return Instruction(Opcode.INTERSECTION, addr_a=a, addr_b=b, addr_dest=d)
def subset(n):
    return Instruction(Opcode.SUBSET_SELECT, n=n)

# Write 3 instruction bodies individually (each has own terminator)
# But write them ALL before reading
print("=== Write 3 bodies, then read ===")
io = IOHandler(buf_sizes={0: 64, 1: 64, 2: 64})

bodies = [
    [inters(UD(7), UD(7), C())],     # C = U[7]
    [subset(5)],                       # C = C[5]
    [inters(C(), C(), UD(5))],        # U[5] = C
]

for body in bodies:
    tokens = serialize_body(body)
    raw = list(encode_tokens(tokens))
    for b in raw:
        io.assign(AddressType.IO_BYTE, 1, int_to_s5set(b))

print(f"Buffer ({len(io._bufs[1])} bytes): {bytes(io._bufs[1]).hex()}")
result = io.resolve(AddressType.IO_S5B, 1)
print(f"Result: {type(result).__name__}")
if isinstance(result, SubroutineSet):
    print(f"Body: {len(result._body)} instructions")
    for i, instr in enumerate(result._body):
        print(f"  [{i}] op={instr.opcode}")

# Test 2: write as combined body
print("\n=== Write combined body, then read ===")
io2 = IOHandler(buf_sizes={0: 64, 1: 64, 2: 64})
combined = [inters(UD(7), UD(7), C()), subset(5), inters(C(), C(), UD(5))]
tokens = serialize_body(combined)
raw = list(encode_tokens(tokens))
for b in raw:
    io2.assign(AddressType.IO_BYTE, 1, int_to_s5set(b))

print(f"Buffer ({len(io2._bufs[1])} bytes): {bytes(io2._bufs[1]).hex()}")
result2 = io2.resolve(AddressType.IO_S5B, 1)
print(f"Result: {type(result2).__name__}")
if isinstance(result2, SubroutineSet):
    print(f"Body: {len(result2._body)} instructions")
    for i, instr in enumerate(result2._body):
        print(f"  [{i}] op={instr.opcode}")

print("\nBuffer after read1:", bytes(io._bufs[1]).hex() if io._bufs[1] else "empty")
print("Buffer after read2:", bytes(io2._bufs[1]).hex() if io2._bufs[1] else "empty")
