"""Verify executor state after running init.s5 + succ.s5."""
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from s5 import (
    tokenize_files, Parser, Executor, SubroutineSet,
    set_value, S5Set, int_to_s5set,
    Opcode, Instruction, Address, AddressType,
)

def verify():
    files = [str(HERE / "init.s5"), str(HERE / "succ.s5")]
    tokens = list(tokenize_files(files))
    instructions = Parser(tokens).parse_program()
    executor = Executor(buf_sizes={0: 64, 1: 64, 2: 64})
    status = executor.run(instructions)
    assert status == "finished", f"expected finished, got {status}"

    # U size
    assert len(executor.U) == 9, f"len(U) == 9, got {len(executor.U)}"

    # U[0] = ZERO = {{∅}}  (value 0, non-empty, inner {∅} = non-empty)
    zero = executor.U[0]
    assert set_value(zero) == 0, f"U[0] value != 0"
    assert len(zero) == 1, f"U[0] len != 1"
    assert len(zero[0]) == 1, f"U[0][0] should be {{∅}}"
    assert len(zero[0][0]) == 0, f"U[0][0][0] should be ∅"

    # U[1] = ONE = {∅}  (value 1)
    one = executor.U[1]
    assert set_value(one) == 1, f"U[1] value != 1"
    assert len(one) == 1, f"U[1] len != 1"
    assert len(one[0]) == 0, f"U[1][0] not empty"

    # U[2] = COUNTER = int_to_s5set(8)  (value 8, since 8 empty elements after 3 doublings)
    counter = executor.U[2]
    assert set_value(counter) == 8, f"U[2] value != 8, got {set_value(counter)}"

    # U[6] = SUCC structure with 2 subroutines
    assert len(executor.U[6]) == 2, f"U[6] len != 2, got {len(executor.U[6])}"
    assert isinstance(executor.U[6][0], SubroutineSet), "U[6][0] not SubroutineSet"
    assert isinstance(executor.U[6][1], SubroutineSet), "U[6][1] not SubroutineSet"

    # U[8] = leftover ZERO from double-wrap (same as U[0])
    assert executor.U[8] == zero, "U[8] != U[0]"

    # Subroutine body lengths
    assert len(executor.U[6][0]._body) == 5, f"NORM_SUCC body != 5, got {len(executor.U[6][0]._body)}"
    assert len(executor.U[6][1]._body) == 6, f"UGROWTH body != 6, got {len(executor.U[6][1]._body)}"

    # Quick smoke test: call NORM_SUCC with ONE, expect TWO
    executor2 = Executor(buf_sizes={0: 64, 1: 64, 2: 64})
    _ = executor2.run(instructions)

    # Set IN_A = ONE, call NORM_SUCC
    one = executor2.U[1]
    items = list(executor2.U._items)
    items[3] = one  # U[3] = IN_A = ONE
    executor2.U = S5Set._from_items(items)

    # Load NORM_SUCC into C and call
    executor2.C = executor2.U[6]
    subset = Instruction(Opcode.SUBSET_SELECT, n=0)
    executor2.exec_instruction(subset)  # C = C[0] = NORM_SUCC
    call = Instruction(Opcode.SUBR)
    executor2.exec_instruction(call)  # Set Sets' → call NORM_SUCC

    # OUT should be succ(ONE) = TWO, which has value 2
    out = executor2.U[5]
    assert set_value(out) == 2, f"NORM_SUCC(ONE) value != 2, got {set_value(out)}"

    print("ALL VERIFICATIONS PASSED")
    return 0

if __name__ == "__main__":
    sys.exit(verify())
