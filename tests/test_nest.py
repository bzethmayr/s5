import pytest

from s5 import Executor, Parser, S5Set, tokenize

empty = S5Set()


def run_src(src, exec=None):
    parsed = Parser(tokenize(src)).parse_program()
    if exec:
        return exec.run(parsed)
    else:
        return Executor().run(parsed)


def build_step1_state() -> Executor:
    src = (
        "Set Set's Set's sets Set's sets set Set's set\n"
        "Set sets Set's sets Sets sets' Set's sets set Set's sets\n"
        "Set Set's Set's sets Set's sets set Set's set"
    )
    exec0 = Executor()
    run_src(src, exec0)
    return exec0


class TestNesting:
    def test_step1_build_u_of_size_2(self):
        exec0 = build_step1_state()
        assert len(exec0.U) == 2
        assert len(exec0.C) == 2
        c0 = exec0.C[0]
        c1 = exec0.C[1]
        assert c0 == empty
        assert c1 != empty and len(c1) == 1
        assert c1[0] == empty

    def test_step2_difference_removes_element(self):
        exec0 = build_step1_state()
        exec2 = Executor()
        exec2.U = exec0.U
        exec2.C = exec0.C
        run_src("Set set Set's sets Sets set sets' set set Set's sets", exec2)
        assert len(exec2.U) == 1
        assert exec2.U[0] != empty

    def test_step3_wrap_around_derived_addr(self):
        exec0 = build_step1_state()
        exec3 = Executor()
        exec3.U = exec0.U
        exec3.C = exec0.C
        run_src(
            "Set sets Set's sets Sets sets' Sets set sets' set set Set's sets", exec3
        )
        assert len(exec3.U) == 3

    def test_step4_wrap_around_base_addr(self):
        exec0 = build_step1_state()
        exec4 = Executor()
        exec4.U = exec0.U
        exec4.C = exec0.C
        run_src("Set sets Set's sets Sets sets' Set's sets set Set's sets", exec4)
        assert len(exec4.U) == 3

    def test_step5_assign_to_wrap_errors(self):
        with pytest.raises(Exception) as exc:
            run_src("Set sets Set's sets Set's sets set Sets sets' Set's sets")
        assert "cannot assign" in str(exc.value)
