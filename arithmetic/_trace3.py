"""Parse subroutine bodies in succ.s5 to understand instructions."""
import sys
sys.path.insert(0, r'C:\Users\Owner\Documents\coderoot\s5')
from s5 import tokenize_files, Parser, Opcode, AddressType, Executor, SubroutineSet, set_value, tokenize

files = [r'C:\Users\Owner\Documents\coderoot\s5\arithmetic\init.s5',
         r'C:\Users\Owner\Documents\coderoot\s5\arithmetic\succ.s5']
tokens = list(tokenize_files(files))
parser = Parser(tokens)
instructions = parser.parse_program()

executor = Executor(buf_sizes={0: 64, 1: 64, 2: 64})
executor.run(instructions)

def addr_short(addr):
    if addr is None: return 'None'
    d = f'^{addr.dispatch_depth}' if addr.dispatch_depth != 1 else ''
    m = {AddressType.U:'U', AddressType.C:'C', AddressType.DERIVED:f'C[{addr.index}]',
         AddressType.UD:f'U[{addr.index}]', AddressType.WRAP:f'wrap({addr_short(addr.sub_addr)})',
         AddressType.IO:'IO', AddressType.IO_BYTE:'IO_BYTE', AddressType.IO_S5B:'IO_S5B'}
    return m.get(addr.type, '???') + d

OPS = {Opcode.UNION:'UNION', Opcode.INTERSECTION:'INTERSECTION', Opcode.DIFFERENCE:'DIFFERENCE',
       Opcode.SUBSET_SELECT:'SUBSET_SELECT', Opcode.SUBR:'SUBR'}

for idx in range(2):
    subr = executor.U[6][idx]
    print(f'=== U[6][{idx}] ({len(subr._body)} instructions) ===')
    for bi, body_instr in enumerate(subr._body):
        op = OPS[body_instr.opcode]
        a = addr_short(body_instr.addr_a) if body_instr.addr_a else 'None'
        b = addr_short(body_instr.addr_b) if body_instr.addr_b else 'None'
        d = addr_short(body_instr.addr_dest) if body_instr.addr_dest else 'None'
        print(f'  body[{bi}]: {op:15s} A={a:20s} B={b:20s} -> D={d}')
