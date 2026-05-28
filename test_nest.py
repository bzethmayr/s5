import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s5 import S5Set, tokenize, Parser, Executor

empty = S5Set()

# ---- Step 1: Build U = {empty, {empty}} ----
#  1. C = U âˆ© U = {empty}
#  2. U = U âˆª {U} = {empty} âˆª {{empty}} = {empty, {empty}}
#  3. C = U âˆ© U = {empty, {empty}}
src = (
    "Set Set's Set's sets Set's sets set Set's set\n"
    "Set sets Set's sets Sets sets' Set's sets set Set's sets\n"
    "Set Set's Set's sets Set's sets set Set's set"
)
exec0 = Executor()
exec0.run(Parser(tokenize(src)).parse_program())

print('Step 1:')
print(f'  U = {exec0.U}  (len={len(exec0.U)})')
print(f'  C = {exec0.C}  (len={len(exec0.C)})')
assert len(exec0.U) == 2
assert len(exec0.C) == 2

c0 = exec0.C[0]
c1 = exec0.C[1]
assert c0 == empty, f'C[0] should be empty, got {c0}'
assert c1 != empty and len(c1) == 1, f'C[1] should be {{empty}}, got {c1}'
assert c1[0] == empty, 'C[1][0] should be empty'
print('  C[0] = {}, C[1] = {{}}, C[1][0] = {}')

# ---- Step 2: U = U \ C[1] = {empty, {empty}} \ {empty} = {{empty}} ----
exec2 = Executor()
exec2.U = exec0.U
exec2.C = exec0.C
exec2.run(Parser(tokenize(
    "Set set Set's sets Sets set sets' set set Set's sets"
)).parse_program())
print('\nStep 2: U = U \\ C[1]')
print(f'  U = {exec2.U}  (len={len(exec2.U)})')
assert len(exec2.U) == 1
assert exec2.U[0] != empty
print('  Result: {{empty}}')

# ---- Step 3: U = U âˆª {C[1]} â€” wrap around derived addr ----
exec3 = Executor()
exec3.U = exec0.U
exec3.C = exec0.C
exec3.run(Parser(tokenize(
    "Set sets Set's sets Sets sets' Sets set sets' set set Set's sets"
)).parse_program())
print('\nStep 3: U = U âˆª {C[1]}')
print(f'  U = {exec3.U}  (len={len(exec3.U)})')
assert len(exec3.U) == 3
print('  Result: {empty, {empty}, {{empty}}}')

# ---- Step 4: Wrap around base address U ----
exec4 = Executor()
exec4.U = exec0.U
exec4.C = exec0.C
exec4.run(Parser(tokenize(
    "Set sets Set's sets Sets sets' Set's sets set Set's sets"
)).parse_program())
print('\nStep 4: U = U âˆª {U}')
print(f'  U = {exec4.U}  (len={len(exec4.U)})')
assert len(exec4.U) == 3
print('  Result: 3 elements (two original + wrapped set)')

# ---- Step 5: assign to wrap should error ----
exec5 = Executor()
try:
    exec5.run(Parser(tokenize(
        "Set sets Set's sets Set's sets set Sets sets' Set's sets"
    )).parse_program())
    print('\nStep 5: assign to wrap should have errored')
    assert False, 'Should have raised RuntimeError_'
except Exception as e:
    print(f'\nStep 5: assign to wrap error: {e}')
    assert 'cannot assign' in str(e)

print('\nAll nesting tests passed!')

