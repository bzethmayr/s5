"""Full step-by-step trace of all three arithmetic files."""
import sys
sys.path.insert(0, r'C:\Users\Owner\Documents\coderoot\s5')
from s5 import tokenize, Parser, Opcode, AddressType, Executor, SubroutineSet, set_value

files = [
    r'C:\Users\Owner\Documents\coderoot\s5\arithmetic\init.s5',
    r'C:\Users\Owner\Documents\coderoot\s5\arithmetic\succ.s5',
]

# Parse each file and decode addresses
for fpath in files:
    with open(fpath) as f:
        src = f.read().strip()
    lines = src.split('\n')
    toks = tokenize(src)
    parser = Parser(toks)
    instrs = parser.parse_program()

    print(f'\n{"="*70}')
    print(f'FILE: {fpath.split(chr(92))[-1]}')
    print(f'{"="*70}')
    for i, ins in enumerate(instrs):
        print(f'  [{i+1}] {lines[i].strip()}')

print(f'\n{"="*70}')
print('ADDRESS DECODE')
print(f'{"="*70}')

def addr_short(addr):
    if addr is None: return 'None'
    d = f'^{addr.dispatch_depth}' if addr.dispatch_depth != 1 else ''
    m = {AddressType.U:'U', AddressType.C:'C', AddressType.DERIVED:f'C[{addr.index}]',
         AddressType.UD:f'U[{addr.index}]', AddressType.WRAP:f'wrap({addr_short(addr.sub_addr)})',
         AddressType.IO:'IO', AddressType.IO_BYTE:'IO_BYTE', AddressType.IO_S5B:'IO_S5B'}
    return m.get(addr.type, '???') + d

OPS = {Opcode.UNION:'UNION', Opcode.INTERSECTION:'INTERSECTION', Opcode.DIFFERENCE:'DIFFERENCE',
       Opcode.SUBSET_SELECT:'SEL', Opcode.SUBR:'SUBR'}

for fpath in files:
    with open(fpath) as f:
        src = f.read().strip()
    lines = src.split('\n')
    toks = tokenize(src)
    parser = Parser(toks)
    instrs = parser.parse_program()

    print(f'\n--- {fpath.split(chr(92))[-1]} ---')
    for i, ins in enumerate(instrs):
        op = OPS[ins.opcode]
        if ins.opcode == Opcode.SUBR:
            if ins.subr_body is not None:
                print(f'  [{i+1}] {op} body_len={len(ins.subr_body)} loc={addr_short(ins.addr_a)}')
                for bi, bi_ins in enumerate(ins.subr_body):
                    a = addr_short(bi_ins.addr_a) if bi_ins.addr_a else '∅'
                    b = addr_short(bi_ins.addr_b) if bi_ins.addr_b else '∅'
                    d = addr_short(bi_ins.addr_dest) if bi_ins.addr_dest else '∅'
                    print(f'        body[{bi}]: {OPS[bi_ins.opcode]:6s} {a}, {b} -> {d}')
            else:
                cond = addr_short(ins.addr_b) if ins.addr_b else 'None'
                loc = addr_short(ins.addr_a) if ins.addr_a else 'C'
                print(f'  [{i+1}] {op} loc={loc} cond={cond}')
        elif ins.opcode == Opcode.SUBSET_SELECT:
            print(f'  [{i+1}] {op} n={ins.n}')
        else:
            print(f'  [{i+1}] {op:6s} {addr_short(ins.addr_a):20s} {addr_short(ins.addr_b):20s} -> {addr_short(ins.addr_dest)}')

# Full execution trace with per-step U state
print(f'\n{"="*70}')
print('FULL EXECUTION TRACE')
print(f'{"="*70}')

executor = Executor(buf_sizes={0: 64, 1: 64, 2: 64})
print(f'INIT: U len={len(executor.U)}, C=None')

all_instrs = []
for fpath in files:
    with open(fpath) as f:
        src = f.read()
    toks = tokenize(src)
    parser = Parser(toks)
    all_instrs.extend(parser.parse_program())

for i, ins in enumerate(all_instrs):
    if executor.halted:
        print(f'  [{i+1}] HALTED')
        break
    
    u_len_before = len(executor.U)
    c_before_val = set_value(executor.C) if executor.C is not None else 'None'
    
    try:
        executor.exec_instruction(ins)
    except Exception as e:
        print(f'  [{i+1}] ERROR: {e}')
        break
    
    u_len_after = len(executor.U)
    c_after_val = set_value(executor.C) if executor.C is not None else 'None'
    
    if ins.opcode == Opcode.SUBR:
        if ins.subr_body is not None:
            print(f'  [{i+1}] SUBR def -> C val={c_after_val}')
        else:
            print(f'  [{i+1}] SUBR call -> U: {u_len_before}e → {u_len_after}e, C: {c_before_val} → {c_after_val}')
    else:
        print(f'  [{i+1}] U: {u_len_before}e -> {u_len_after}e, C: {c_before_val} -> {c_after_val}')

print(f'\nFINAL U STATE:')
for j in range(len(executor.U)):
    val = set_value(executor.U[j])
    el = executor.U[j]
    if isinstance(el, SubroutineSet):
        print(f'  U[{j}] = SubroutineSet(val={val}, body_len={len(el._body)})')
    else:
        print(f'  U[{j}] = {el}  (val={val})')
print(f'C = {executor.C}  (val={set_value(executor.C)})')
