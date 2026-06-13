"""Trace init.s5 + succ.s5 execution."""
import sys
sys.path.insert(0, r'C:\Users\Owner\Documents\coderoot\s5')
from s5 import tokenize_files, Parser, Opcode, AddressType, Executor, set_value

files = [r'C:\Users\Owner\Documents\coderoot\s5\arithmetic\init.s5',
         r'C:\Users\Owner\Documents\coderoot\s5\arithmetic\succ.s5']
tokens = list(tokenize_files(files))
parser = Parser(tokens)
instructions = parser.parse_program()

def addr_short(addr):
    if addr is None: return 'None'
    d = f'^{addr.dispatch_depth}' if addr.dispatch_depth != 1 else ''
    m = {AddressType.U:'U', AddressType.C:'C', AddressType.DERIVED:f'C[{addr.index}]',
         AddressType.UD:f'U[{addr.index}]', AddressType.WRAP:f'wrap({addr_short(addr.sub_addr)})',
         AddressType.IO:'IO', AddressType.IO_BYTE:'IO_BYTE', AddressType.IO_S5B:'IO_S5B'}
    return m.get(addr.type, '???') + d

OPS = {Opcode.UNION:'UNION', Opcode.INTERSECTION:'INTERSECTION', Opcode.DIFFERENCE:'DIFFERENCE',
       Opcode.SUBSET_SELECT:'SUBSET_SELECT', Opcode.SUBR:'SUBR'}

print(f'=== PARSED ({len(instructions)} instructions) ===')
for i, instr in enumerate(instructions):
    op = OPS[instr.opcode]
    if instr.opcode == Opcode.SUBSET_SELECT:
        detail = f'n={instr.n}'
    elif instr.opcode == Opcode.SUBR:
        if instr.subr_body is not None:
            detail = f'body_len={len(instr.subr_body)}, loc={addr_short(instr.addr_a)}'
        else:
            detail = f'addr_a={addr_short(instr.addr_a)}, cond={addr_short(instr.addr_b) if instr.addr_b else None}'
    else:
        detail = f'{addr_short(instr.addr_a)}, {addr_short(instr.addr_b)} -> {addr_short(instr.addr_dest)}'
    print(f'[{i+1:3d}] {op:15s} {detail}')

# Now trace execution
executor = Executor(buf_sizes={0: 64, 1: 64, 2: 64})
print(f'\n=== EXECUTION TRACE ===')
print(f'INIT: U len={len(executor.U)}, val={set_value(executor.U)}')

for i, instr in enumerate(instructions):
    if executor.halted:
        print(f'[{i+1}] HALTED')
        break
    u_before = set_value(executor.U)
    u_len_before = len(executor.U)
    c_before = set_value(executor.C) if executor.C is not None else None
    
    try:
        executor.exec_instruction(instr)
    except Exception as e:
        import traceback
        print(f'[{i+1}] ERROR: {e}')
        traceback.print_exc()
        break
    
    u_after = set_value(executor.U)
    u_len_after = len(executor.U)
    c_after = set_value(executor.C) if executor.C is not None else None
    
    op = instr.opcode
    if op == Opcode.SUBR:
        if instr.subr_body is not None:
            print(f'[{i+1}] SUBR def (body_len={len(instr.subr_body)})')
        else:
            print(f'[{i+1}] SUBR call')
    else:
        print(f'[{i+1}] U: {u_len_before}e({u_before}) -> {u_len_after}e({u_after}) | C: {c_before} -> {c_after}')

print(f'\nFINAL U ({len(executor.U)} elements):')
for j in range(len(executor.U)):
    v = set_value(executor.U[j])
    t = str(executor.U[j])[:60]
    sr = isinstance(executor.U[j], SubroutineSet) if 'SubroutineSet' in dir() else False
    print(f'  U[{j}] = val={v}  {repr(executor.U[j])[:80]}')
print(f'FINAL C = {set_value(executor.C) if executor.C is not None else None}')
