"""Verify pred.s5 instruction structure."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\Users\Owner\Documents\coderoot\s5')
from s5 import tokenize, Parser, Opcode, AddressType

files = [
    r'C:\Users\Owner\Documents\coderoot\s5\arithmetic\init.s5',
    r'C:\Users\Owner\Documents\coderoot\s5\arithmetic\succ.s5',
    r'C:\Users\Owner\Documents\coderoot\s5\arithmetic\pred.s5',
]

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
        src = f.read()
    toks = tokenize(src)
    parser = Parser(toks)
    instrs = parser.parse_program()
    print(f'\n=== {fpath.split(chr(92))[-1]} ({len(instrs)} instrs) ===')
    for i, ins in enumerate(instrs):
        op = OPS[ins.opcode]
        if ins.opcode == Opcode.SUBR:
            if ins.subr_body is not None:
                print(f'  [{i+1}] SUBR body_len={len(ins.subr_body)} loc={addr_short(ins.addr_a)}')
                for bi, bi_ins in enumerate(ins.subr_body):
                    a = addr_short(bi_ins.addr_a) if bi_ins.addr_a else '--'
                    b = addr_short(bi_ins.addr_b) if bi_ins.addr_b else '--'
                    d = addr_short(bi_ins.addr_dest) if bi_ins.addr_dest else '--'
                    print(f'  body[{bi}]: {OPS[bi_ins.opcode]:6s} {a}, {b} -> {d}')
            else:
                loc = addr_short(ins.addr_a) if ins.addr_a else 'C'
                cond = addr_short(ins.addr_b) if ins.addr_b else '--'
                print(f'  [{i+1}] SUBR call loc={loc} cond={cond}')
        elif ins.opcode == Opcode.SUBSET_SELECT:
            print(f'  [{i+1}] SEL n={ins.n}')
        else:
            print(f'  [{i+1}] {op:6s} {addr_short(ins.addr_a):25s} {addr_short(ins.addr_b):25s} -> {addr_short(ins.addr_dest)}')
