import subprocess
import sys
from pathlib import Path
import pytest
from s5 import tokenize, Parser, Executor

HERE = Path(__file__).parent
ROOT = HERE.parent


def run(inp):
    p = subprocess.run(
        [sys.executable, "-m", "s5"],
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
    assert "out of bounds" in err


def test_c_undefined():
    out, err, rc = run("Set Sets set sets' sets")
    assert "C is undefined" in err


def test_bad_token():
    out, err, rc = run("foo")
    assert "unknown token" in err


def test_incomplete_instr():
    out, err, rc = run("Set")
    assert "end of input" in err


def test_empty_c_intersect():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Set Sets set sets' sets\n"
        "Set set Set's sets Set's set set Set's set\n"
        "Set Set's Set's set Set's set set Set's sets"
    )
    out, err, rc = run(src)
    assert out in ("halted", "finished")


def test_compute_42():
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
    tokens = tokenize(src)
    parser = Parser(tokens)
    executor = Executor()
    status = executor.run(parser.parse_program())
    assert status == "finished"
    assert len(executor.U) == 42
