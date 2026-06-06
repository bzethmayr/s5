import subprocess
import sys
from pathlib import Path
import pytest
from s5 import tokenize, Parser, Executor, SubroutineSet, LineSet, set_value, S5Set, RuntimeError_

HERE = Path(__file__).parent
ROOT = HERE.parent


def run(inp):
    p = subprocess.run(
        [sys.executable, "-m", "s5", "--repl"],
        input=inp, capture_output=True, text=True, cwd=str(ROOT))
    return p.stdout.strip(), p.stderr.strip(), p.returncode


def test_halt_u_u():
    out, err, rc = run("Set set Set's sets Set's sets set Set's sets")
    assert out == "halted"


def test_empty():
    out, err, rc = run("")
    assert out == "finished"


def test_union_u_u():
    out, err, rc = run("Set sets Set's sets Set's sets set Set's sets")
    assert out == "finished"


def test_intersect_u_u():
    out, err, rc = run("Set Set's Set's sets Set's sets set Set's sets")
    assert out == "finished"


def test_multi_halt():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Set Sets set sets' sets\n"
        "Set Set's Set's sets Set's set set Set's sets"
    )
    out, err, rc = run(src)
    assert out == "halted"


def test_diff_c():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Set Sets set sets' sets\n"
        "Set set Set's sets Set's set set Set's sets"
    )
    out, err, rc = run(src)
    assert out == "finished"


def test_derived_a():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Set sets Sets set sets' sets Set's sets set Set's sets"
    )
    out, err, rc = run(src)
    assert out == "finished"


def test_derived_b():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Set sets Set's sets Sets set sets' sets set Set's sets"
    )
    out, err, rc = run(src)
    assert out == "finished"


def test_bounded_int_out_of_bounds():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Set set Set's sets Sets set sets' set sets set Set's sets"
    )
    out, err, rc = run(src)
    assert "out of bounds" in out


def test_c_undefined():
    out, err, rc = run("Set Sets set sets' sets")
    assert "C is undefined" in out


def test_bad_token():
    out, err, rc = run("foo")
    assert "unknown token" in out


def test_incomplete_instr():
    out, err, rc = run("Set")
    assert "end of input" in out


def test_empty_c_intersect():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Set Sets set sets' sets\n"
        "Set set Set's sets Set's set set Set's set\n"
        "Set Set's Set's set Set's set set Set's sets"
    )
    out, err, rc = run(src)
    assert out in ("halted", "finished")


def test_set_value_empty():
    assert set_value(S5Set()) == 0


def test_set_value_singleton_empty():
    assert set_value(S5Set([S5Set()])) == 1


def test_set_value_singleton_nonempty():
    assert set_value(S5Set([S5Set([S5Set()])])) == 0


def test_set_value_42():
    empty = S5Set()
    nonempty = S5Set([empty])
    s = S5Set([empty, nonempty, nonempty, empty,
               nonempty, nonempty, empty, nonempty])
    assert set_value(s) == 42


def test_s5_compute_42():
    src = (
        "Set Set's Set's sets Set's sets set Set's set\n"
        "Set sets Set's sets Sets sets' Set's set set Set's sets\n"
        "Set sets Set's sets Sets sets' Set's set set Set's sets\n"
        "Set sets Set's sets Set's set set Set's sets\n"
        "Set sets Set's sets Sets sets' Set's set set Set's sets\n"
        "Set sets Set's sets Sets sets' Set's set set Set's sets\n"
        "Set sets Set's sets Set's set set Set's sets\n"
        "Set sets Set's sets Sets sets' Set's set set Set's sets"
    )
    tokens = tokenize(src)
    parser = Parser(tokens)
    executor = Executor()
    status = executor.run(parser.parse_program())
    assert status == "finished"
    assert set_value(executor.U) == 42


def test_s5_compute_42_subr():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Sets' Sets' Sets set sets' set\n"
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets\n"
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets\n"
        "  Set sets Set's sets Sets sets' Sets set sets' sets set Set's sets\n"
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets\n"
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets\n"
        "  Set sets Set's sets Sets sets' Sets set sets' sets set Set's sets\n"
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets\n"
        "Sets'\n"
        "Set Sets' Sets set sets' set"
    )
    tokens = tokenize(src)
    parser = Parser(tokens)
    executor = Executor()
    status = executor.run(parser.parse_program())
    assert status == "finished"
    assert set_value(executor.U) == 42


def test_s5_compute_42_subr_oneline():
    src = " ".join(line.strip() for line in [
        "Set sets Set's sets Set's sets set Set's set",
        "Sets' Sets' Sets set sets' set",
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets",
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets",
        "  Set sets Set's sets Sets sets' Sets set sets' sets set Set's sets",
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets",
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets",
        "  Set sets Set's sets Sets sets' Sets set sets' sets set Set's sets",
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets",
        "Sets'",
        "Set Sets' Sets set sets' set",
    ])
    tokens = tokenize(src)
    parser = Parser(tokens)
    executor = Executor()
    status = executor.run(parser.parse_program())
    assert status == "finished"
    assert set_value(executor.U) == 42


def run_src(src):
    return Executor().run(Parser(tokenize(src)).parse_program())


class TestSubr:
    def test_subr_decl_default(self):
        src = (
            "Sets' Sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets'"
        )
        assert run_src(src) == "finished"

    def test_subr_explicit_c(self):
        src = (
            "Sets' Sets' Set's set\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets' Set's set"
        )
        assert run_src(src) == "finished"

    def test_subr_call_and_return(self):
        src = (
            "Sets' Sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set sets Set's sets Set's sets set Set's sets\n"
            "Set Sets'"
        )
        tokens = tokenize(src)
        parser = Parser(tokens)
        executor = Executor()
        status = executor.run(parser.parse_program())
        assert status == "finished"
        assert len(executor.U) == 4

    def test_subr_halt_inside(self):
        src = (
            "Sets' Sets'\n"
            "  Set set Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets'"
        )
        out, err, rc = run(src)
        assert out == "halted"

    def test_subr_at_cn(self):
        src = (
            "Set sets Set's sets Set's sets set Set's set\n"
            "Sets' Sets' Sets set sets' sets\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets' Sets set sets' sets"
        )
        out, err, rc = run(src)
        assert out == "finished"

    def test_subr_stores_as_subroutineseet(self):
        src = (
            "Sets' Sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'"
        )
        tokens = tokenize(src)
        parser = Parser(tokens)
        executor = Executor()
        executor.run(parser.parse_program())
        assert isinstance(executor.C, SubroutineSet)
        assert len(executor.C) == 1

    def test_subr_unclosed_decl(self):
        src = (
            "Sets' Sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
        )
        out, err, rc = run(src)
        assert "syntax error" in out

    def test_subr_bare_sets_apos(self):
        out, err, rc = run("Sets'")
        assert "syntax error" in out

    def test_subr_invoke_not_subroutine(self):
        src = (
            "Set sets Set's sets Set's sets set Set's set\n"
            "Set Sets'"
        )
        out, err, rc = run(src)
        assert "not a subroutine" in out

    def test_subr_invoke_undefined_c(self):
        out, err, rc = run("Set Sets'")
        assert "C is undefined" in out

    def test_subr_set_value_42(self):
        empty = S5Set()
        nonempty = S5Set([empty])
        s = S5Set([empty, nonempty, nonempty, empty,
                   nonempty, nonempty, empty, nonempty])
        assert set_value(s) == 42


class TestCondCall:
    def test_cond_call_nonempty_calls(self):
        src = (
            "Sets' Sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets' set Set's sets"
        )
        executor = Executor()
        status = executor.run(Parser(tokenize(src)).parse_program())
        assert status == "finished"
        assert len(executor.U) == 2

    def test_cond_call_empty_skips(self):
        src = (
            "Sets' Sets' Set's sets\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set sets Set's sets Set's sets set Set's set\n"
            "Set set Set's set Set's set set Set's set\n"
            "Set Sets' set Set's set"
        )
        executor = Executor()
        status = executor.run(Parser(tokenize(src)).parse_program())
        assert status == "finished"
        assert len(executor.U) == 1

    def test_cond_call_explicit_addr(self):
        src = (
            "Set sets Set's sets Set's sets set Set's set\n"
            "Sets' Sets' Sets set sets' sets\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets' set Set's sets Sets set sets' sets"
        )
        out, err, rc = run(src)
        assert "finished" in out
        assert rc == 0

    def test_cond_call_default_c(self):
        src = (
            "Sets' Sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets' set Set's sets"
        )
        out, err, rc = run(src)
        assert "finished" in out
        assert rc == 0

    def test_cond_call_empty_does_not_call(self):
        src = (
            "Sets' Sets' Set's sets\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set sets Set's sets Set's sets set Set's set\n"
            "Set set Set's set Set's set set Set's set\n"
            "Set Sets' set Set's set\n"
            "Set set Set's sets Set's sets set Set's sets"
        )
        out, err, rc = run(src)
        assert "halted" in out
        assert rc == 0


class TestUD:
    def test_subr_define_at_u0_and_call(self):
        src = (
            "Sets' Sets' Sets sets sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets' Sets sets sets'"
        )
        executor = Executor()
        assert len(executor.U) == 1
        status = executor.run(Parser(tokenize(src)).parse_program())
        assert status == "finished"
        assert len(executor.U) == 2

    def test_subr_define_at_u0_store_type(self):
        src = (
            "Sets' Sets' Sets sets sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'"
        )
        executor = Executor()
        executor.run(Parser(tokenize(src)).parse_program())
        assert isinstance(executor.U[0], SubroutineSet)

    def test_ud_index_out_of_bounds_assign(self):
        src = (
            "Sets' Sets' Sets sets sets' set set\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'"
        )
        with pytest.raises(RuntimeError_, match="U\\[2\\] out of bounds"):
            Executor().run(Parser(tokenize(src)).parse_program())

    def test_ud_index_out_of_bounds_resolve(self):
        src = "Set Sets' Sets sets sets' set set"
        with pytest.raises(RuntimeError_, match="U\\[2\\] out of bounds"):
            Executor().run(Parser(tokenize(src)).parse_program())
