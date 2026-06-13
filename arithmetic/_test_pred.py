"""Verify pred.s5 end-to-end: init + succ + pred."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from s5 import (
    tokenize_files, Parser, Executor, SubroutineSet,
    set_value, S5Set, int_to_s5set,
    Opcode, Instruction,
)

HERE = Path(__file__).parent
files = [str(HERE / "init.s5"), str(HERE / "succ.s5"), str(HERE / "pred.s5")]

tokens = list(tokenize_files(files))
instructions = Parser(tokens).parse_program()

print(f"Total instructions: {len(instructions)}")

# Run full init + succ + pred
executor = Executor(buf_sizes={0: 64, 1: 64, 2: 64})
status = executor.run(instructions)
assert status == "finished", f"expected finished, got {status}"

# Verify U[7] structure
assert len(executor.U) >= 9, f"U should have at least 9 elements, has {len(executor.U)}"
assert len(executor.U[7]) == 3, f"U[7] should have 3 subroutines, has {len(executor.U[7])}"
for i in range(3):
    assert isinstance(executor.U[7][i], SubroutineSet), f"U[7][{i}] not a SubroutineSet"

# U[7][0] = PRED_MAIN (7 instructions)
assert len(executor.U[7][0]._body) == 7, f"PRED_MAIN body != 7, got {len(executor.U[7][0]._body)}"
# U[7][1] = PRED_ADVANCE (5 instructions)
assert len(executor.U[7][1]._body) == 5, f"PRED_ADVANCE body != 5, got {len(executor.U[7][1]._body)}"
# U[7][2] = PRED_STEP (8 instructions)
assert len(executor.U[7][2]._body) == 8, f"PRED_STEP body != 8, got {len(executor.U[7][2]._body)}"

print("Structure verification PASSED")

# --- Test calling pred ---
def call_pred(executor, v):
    """Call pred(V) and return the result."""
    # Set IN_A = int_to_s5set(v)
    val = int_to_s5set(v)
    items = list(executor.U._items)
    items[3] = val  # U[3] = IN_A
    executor.U = S5Set._from_items(items)

    # Load PRED_MAIN into C and call
    executor.C = executor.U[7]
    subset = Instruction(Opcode.SUBSET_SELECT, n=0)
    executor.exec_instruction(subset)  # C = C[0] = PRED_MAIN
    call = Instruction(Opcode.SUBR)
    executor.exec_instruction(call)    # Set Sets' → call PRED_MAIN

    out = executor.U[5]
    return set_value(out)

# Test with various values
test_cases = [
    (0, 0),   # pred(0) = 0 by convention
    (1, 0),   # pred(1) = 0
    (2, 1),   # pred(2) = 1
    (3, 2),   # pred(3) = 2
    (5, 4),   # pred(5) = 4
    (8, 7),   # pred(8) = 7
    (10, 9),  # pred(10) = 9
]

for v, expected in test_cases:
    # Fresh executor each time
    ex = Executor(buf_sizes={0: 64, 1: 64, 2: 64})
    ex.run(instructions)
    result = call_pred(ex, v)
    assert result == expected, f"pred({v}) = {result}, expected {expected}"

print("Functional tests: ALL PASSED")
print("pred.s5 verified successfully!")
