"""Detailed trace of init.s5 + succ.s5 with subroutine body inspection."""
import sys
sys.path.insert(0, r'C:\Users\Owner\Documents\coderoot\s5')
from s5 import tokenize_files, Parser, Opcode, AddressType, Executor, SubroutineSet, set_value

files = [r'C:\Users\Owner\Documents\coderoot\s5\arithmetic\init.s5',
         r'C:\Users\Owner\Documents\coderoot\s5\arithmetic\succ.s5']
tokens = list(tokenize_files(files))
parser = Parser(tokens)
instructions = parser.parse_program()

executor = Executor(buf_sizes={0: 64, 1: 64, 2: 64})
executor.run(instructions)

print('=== FINAL STATE ===')
for j in range(len(executor.U)):
    v = set_value(executor.U[j])
    el = executor.U[j]
    if isinstance(el, SubroutineSet):
        print(f'U[{j}] = SubroutineSet (value={v}, body_len={len(el._body)})')
        for bi, body_instr in enumerate(el._body):
            print(f'  body[{bi}]: {body_instr}')
    else:
        print(f'U[{j}] = {el}  (value={v})')

print(f'\nC = {executor.C} (value={set_value(executor.C)})')

# Show subroutine bodies more readably
print('\n=== SUBROUTINE BODIES ===')
from s5.serialize import serialize_instruction
from s5.pretty import pretty_print

for idx in range(2):
    subr = executor.U[6][idx]
    print(f'\nU[6][{idx}] body ({len(subr._body)} instructions):')
    print(pretty_print(subr._body))
    print()
