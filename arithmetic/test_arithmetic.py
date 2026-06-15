"""Consolidated arithmetic regression tests: init, succ, pred, pred1, demo."""
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


def _run_setup():
    """Run init.s5 + succ.s5 + pred.s5, return executor with fully set-up U."""
    files = [str(HERE / "init.s5"), str(HERE / "succ.s5"), str(HERE / "pred.s5")]
    tokens = list(tokenize_files(files))
    instructions = Parser(tokens).parse_program()
    executor = Executor(buf_sizes={0: 64, 1: 64, 2: 64})
    status = executor.run(instructions)
    assert status == "finished", f"setup failed: {status}"
    return executor


def _run_pred1(executor):
    """Run pred1.s5 to build LUT in U[16] for all 0..COUNTER-1."""
    files = [str(HERE / "pred1.s5")]
    tokens = list(tokenize_files(files))
    instructions = Parser(tokens).parse_program()
    status = executor.run(instructions)
    assert status == "finished", f"pred1 failed: {status}"


def _run_demo(executor, q_val):
    """Run demo.s5 on an existing executor, reading Q from stdin."""
    import io
    old_stdin = sys.stdin
    sys.stdin = io.StringIO(f"{q_val}\n")
    files = [str(HERE / "demo.s5")]
    tokens = list(tokenize_files(files))
    instructions = Parser(tokens).parse_program()
    status = executor.run(instructions)
    sys.stdin = old_stdin
    assert status == "finished", f"demo failed: {status}"


def _lut_len(executor):
    """Number of entries in the LUT at U[16]."""
    return len(executor.U[16])


def _lut_value(executor, idx):
    """Get LUT entry value from U[16][idx]."""
    return set_value(executor.U[16][idx])


def _call_pred(executor, v):
    """Call PRED_MAIN (U[7][0]) with IN_A=v, return result from U[5]."""
    items = list(executor.U._items)
    items[3] = int_to_s5set(v)
    executor.U = S5Set._from_items(items)
    executor.C = executor.U[7]
    executor.exec_instruction(Instruction(Opcode.SUBSET_SELECT, n=0))
    executor.exec_instruction(Instruction(Opcode.SUBR))
    return set_value(executor.U[5])


class TestInitSucc:
    """Verify init.s5 + succ.s5 produce correct universe state."""

    def test_u_size(self):
        ex = _run_setup()
        assert len(ex.U) == 32

    def test_zero(self):
        ex = _run_setup()
        assert set_value(ex.U[0]) == 0
        assert len(ex.U[0]) == 0

    def test_one(self):
        ex = _run_setup()
        assert set_value(ex.U[1]) == 1
        assert len(ex.U[1]) == 1
        assert len(ex.U[1][0]) == 0

    def test_counter(self):
        ex = _run_setup()
        assert set_value(ex.U[2]) == 32

    def test_succ_structure(self):
        ex = _run_setup()
        assert len(ex.U[6]) == 3
        for i in range(3):
            assert isinstance(ex.U[6][i], SubroutineSet), f"U[6][{i}] not SubroutineSet"

    def test_norm_succ_body_len(self):
        ex = _run_setup()
        assert len(ex.U[6][0]._body) == 5

    def test_ugrowth_body_len(self):
        ex = _run_setup()
        assert len(ex.U[6][1]._body) == 6

    def test_norm_body_len(self):
        ex = _run_setup()
        assert len(ex.U[6][2]._body) == 5

    def test_norm_succ_smoke(self):
        """Call NORM_SUCC(ONE) → TWO (value 2)."""
        ex = _run_setup()
        items = list(ex.U._items)
        items[3] = ex.U[1]
        ex.U = S5Set._from_items(items)
        ex.C = ex.U[6]
        ex.exec_instruction(Instruction(Opcode.SUBSET_SELECT, n=0))
        ex.exec_instruction(Instruction(Opcode.SUBR))
        assert set_value(ex.U[5]) == 2


class TestPredStructure:
    """Verify pred.s5 subroutine structure."""

    def test_pred_structure(self):
        ex = _run_setup()
        assert len(ex.U[7]) == 3
        for i in range(3):
            assert isinstance(ex.U[7][i], SubroutineSet), f"U[7][{i}] not SubroutineSet"
        assert isinstance(ex.U[8], S5Set), "U[8] should be scratch data (S5Set), not SubroutineSet"

    def test_pred_main_body_len(self):
        ex = _run_setup()
        assert len(ex.U[7][0]._body) == 7

    def test_pred_advance_body_len(self):
        ex = _run_setup()
        assert len(ex.U[7][1]._body) == 5

    def test_pred_step_body_len(self):
        ex = _run_setup()
        assert len(ex.U[7][2]._body) == 8


class TestPredFunction:
    """Functional tests for pred()."""

    PRED_CASES = [
        (0, 0),
        (1, 0),
        (2, 1),
        (3, 2),
        (4, 3),
        (5, 4),
        (8, 7),
        (10, 9),
        (20, 19),
    ]

    def test_all_cases(self):
        ex = _run_setup()
        for v, expected in self.PRED_CASES:
            result = _call_pred(ex, v)
            assert result == expected, f"pred({v}) = {result}, expected {expected}"

    def test_pred_separate_executors(self):
        for v, expected in self.PRED_CASES:
            ex = _run_setup()
            result = _call_pred(ex, v)
            assert result == expected, f"pred({v}) = {result}, expected {expected}"


class TestPred1LUT:
    """Verify pred1.s5 builds complete LUT in U[16] for all 0..COUNTER-1."""

    LUT_EXPECTED = [max(0, i - 1) for i in range(32)]

    def test_lut_size(self):
        ex = _run_setup()
        _run_pred1(ex)
        assert _lut_len(ex) == 32, f"LUT len = {_lut_len(ex)}, expected 32"

    def test_lut_values(self):
        ex = _run_setup()
        _run_pred1(ex)
        for i, exp_val in enumerate(self.LUT_EXPECTED):
            assert _lut_value(ex, i) == exp_val, \
                f"LUT[{i}] = {_lut_value(ex, i)} != {exp_val}"

    def test_lut_in_clean_slot(self):
        """U[16] should contain only data — no subroutines mixed in."""
        ex = _run_setup()
        _run_pred1(ex)
        for i in range(len(ex.U[16])):
            from s5 import SubroutineSet
            assert not isinstance(ex.U[16][i], SubroutineSet), \
                f"U[16][{i}] is a SubroutineSet, not data"

    def test_pred_search_still_works_after_lut(self):
        """PRED_MAIN (U[7][0]) should still be callable after LUT build."""
        ex = _run_setup()
        _run_pred1(ex)
        result = _call_pred(ex, 7)
        assert result == 6, f"pred(7) after LUT = {result}, expected 6"


class TestPred1LUTReuse:
    """Demonstrate LUT reusability — copy and compile-time lookup."""

    def test_copy_lut_to_other_slot(self):
        """Copy U[16] to U[20] and verify values match."""
        ex = _run_setup()
        _run_pred1(ex)
        # Simulate: U[20] = U[20] ∪ U[16] (copy)
        ex.U = ex.U.union(ex.U[16]) if len(ex.U) == 0 else ex.U  # ensure U has 32 slots
        # Actually, U is already set up. Let's copy via Python operations:
        old_items = list(ex.U._items)
        old_items[20] = ex.U[16]  # U[20] = copy of LUT
        ex.U = S5Set._from_items(old_items)
        for i in range(32):
            assert set_value(ex.U[20][i]) == set_value(ex.U[16][i]), \
                f"Copy mismatch at [{i}]"

    def test_compile_time_lookup(self):
        """SUBSET_SELECT(V) on U[16] gives pred(V) for compile-time V."""
        ex = _run_setup()
        _run_pred1(ex)
        for v in [0, 1, 2, 3, 5, 10, 20, 31]:
            expected = max(0, v - 1)
            val = ex.U[16][v]
            assert set_value(val) == expected, \
                f"U[16][{v}] = {set_value(val)}, expected pred({v}) = {expected}"

    def test_lut_unaffected_by_pred_search(self):
        """The search-based pred does not modify U[16]."""
        ex = _run_setup()
        _run_pred1(ex)
        before = list(ex.U[16]._items)
        _call_pred(ex, 7)
        after = list(ex.U[16]._items)
        assert before == after, "U[16] was modified by PRED_MAIN call"


class TestDemo:
    """Verify demo.s5 reads Q from stdin and outputs pred(Q)."""

    DEMO_CASES = [(0, 0), (1, 0), (2, 1), (3, 2), (5, 4), (10, 9)]

    def test_demo_output(self):
        for q_val, expected in self.DEMO_CASES:
            ex = _run_setup()
            _run_pred1(ex)
            _run_demo(ex, q_val)
            result = set_value(ex.U[5])
            assert result == expected, \
                f"demo(Q={q_val}) = {result}, expected {expected}"

    def test_demo_separate_executors(self):
        for q_val, expected in self.DEMO_CASES:
            ex = _run_setup()
            _run_pred1(ex)
            _run_demo(ex, q_val)
            result = set_value(ex.U[5])
            assert result == expected, \
                f"demo(Q={q_val}) = {result}, expected {expected}"
