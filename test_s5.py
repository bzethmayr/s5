import subprocess
import sys
import os

here = os.path.dirname(os.path.abspath(__file__))

def run(inp):
    p = subprocess.run(
        [sys.executable, os.path.join(here, 's5.py')],
        input=inp, capture_output=True, text=True)
    return p.stdout.strip(), p.stderr.strip(), p.returncode

tests = []

# halt example
out, err, rc = run('Set set Set\'s sets Set\'s sets set Set\'s sets')
tests.append(('halt U-U', out == 'halted'))

# empty program
out, err, rc = run('')
tests.append(('empty', out == 'finished'))

# union non-halt
out, err, rc = run('Set sets Set\'s sets Set\'s sets set Set\'s sets')
tests.append(('union U U', out == 'finished'))

# intersection non-halt
out, err, rc = run('Set Set\'s Set\'s sets Set\'s sets set Set\'s sets')
tests.append(('intersect U U', out == 'finished'))

# multi-instr halt via intersection
src = (
    'Set sets Set\'s sets Set\'s sets set Set\'s set\n'
    'Set Sets set sets\' sets\n'
    'Set Set\'s Set\'s sets Set\'s set set Set\'s sets'
)
out, err, rc = run(src)
tests.append(('multi halt', out == 'halted'))

# set C then diff
src = (
    'Set sets Set\'s sets Set\'s sets set Set\'s set\n'
    'Set Sets set sets\' sets\n'
    'Set set Set\'s sets Set\'s set set Set\'s sets'
)
out, err, rc = run(src)
tests.append(('diff C', out == 'finished'))

# derived addr as A
src = (
    'Set sets Set\'s sets Set\'s sets set Set\'s set\n'
    'Set sets Sets set sets\' sets Set\'s sets set Set\'s sets'
)
out, err, rc = run(src)
tests.append(('derived A', out == 'finished'))

# derived addr as B
src = (
    'Set sets Set\'s sets Set\'s sets set Set\'s set\n'
    'Set sets Set\'s sets Sets set sets\' sets set Set\'s sets'
)
out, err, rc = run(src)
tests.append(('derived B', out == 'finished'))

# bounded integer C[2] in B position (should parse, then runtime error bounds)
src = (
    'Set sets Set\'s sets Set\'s sets set Set\'s set\n'
    'Set set Set\'s sets Sets set sets\' set sets set Set\'s sets'
)
out, err, rc = run(src)
tests.append(('bounded int C[2]', 'out of bounds' in err))

# C undefined
out, err, rc = run('Set Sets set sets\' sets')
tests.append(('C undefined', 'C is undefined' in err))

# invalid token
out, err, rc = run('foo')
tests.append(('bad token', 'unknown token' in err))

# incomplete instruction
out, err, rc = run('Set')
tests.append(('incomplete instr', 'end of input' in err))

# singleton halt via intersection
src = (
    'Set sets Set\'s sets Set\'s sets set Set\'s set\n'
    'Set Sets set sets\' sets\n'
    'Set set Set\'s sets Set\'s set set Set\'s set\n'
    'Set Set\'s Set\'s set Set\'s set set Set\'s sets'
)
out, err, rc = run(src)
tests.append(('empty C intersect', out in ('halted', 'finished')))

# compute 42: 101010b = (((((1×2)×2+1)×2)×2+1)×2 = 42
import importlib.util
spec = importlib.util.spec_from_file_location('s5', os.path.join(here, 's5.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

src = (
    "Set Set's Set's sets Set's sets set Set's set\n"
    "Set sets Set's sets Set's sets set Set's sets\n"
    "Set sets Set's sets Set's sets set Set's sets\n"
    "Set sets Set's sets Set's set set Set's sets\n"
    "Set sets Set's sets Set's sets set Set's sets\n"
    "Set sets Set's sets Set's sets set Set's sets\n"
    "Set sets Set's sets Set's set set Set's sets\n"
    "Set sets Set's sets Set's sets set Set's sets"
)
tokens = mod.tokenize(src)
parser = mod.Parser(tokens)
executor = mod.Executor()
status = executor.run(parser.parse_program())
tests.append(('compute 42', status == 'finished' and len(executor.U) == 42))

print(f'{sum(1 for ok in tests if ok)}/{len(tests)} passed')
for i, (name, ok) in enumerate(tests):
    status = 'PASS' if ok else 'FAIL'
    print(f'  {status}: {name}')
