import subprocess
import sys
from pathlib import Path

import pytest
from s5 import (
    Executor,
    Parser,
    S5Set,
    int_to_s5set,
    set_value,
    tokenize,
)

HERE = Path(__file__).parent
ROOT = HERE.parent


def run(inp):
    p = subprocess.run(
        [sys.executable, "-m", "s5", "--repl"],
        input=inp, capture_output=True, text=True, cwd=str(ROOT))
    return p.stdout.strip(), p.stderr.strip(), p.returncode


def run_src(src):
    return Executor().run(Parser(tokenize(src)).parse_program())


class TestTokenizerAdversarial:

    def test_whitespace_only(self):
        out, err, rc = run("   \t\n  \r\n  ")
        assert rc != 0
        assert "parity mismatch" in out


class TestParserAdversarial:

    def test_empty_subroutine_body(self):
        src = (
            "Sets' Sets' Sets'\n"
            "Set Sets'"
        )
        out, err, rc = run(src)
        assert out == "finished"


class TestS5SetAdversarial:

    def test_intersection_with_duplicates(self):
        empty = S5Set()
        s = S5Set([empty, empty])
        result = s.intersection(S5Set([empty]))
        assert len(result) == 2
        assert result[0] == empty
        assert result[1] == empty

    def test_difference_identity(self):
        empty = S5Set()
        s = S5Set([empty, S5Set([empty])])
        assert len(s.difference(S5Set())) == 2
        assert len(S5Set().difference(s)) == 0

    def test_int_to_s5set_negative(self):
        s = int_to_s5set(-5)
        assert len(s) == 0
        assert set_value(s) == 0


class TestExecutorAdversarial:

    def test_subset_select_on_empty_C(self):
        src = (
            "Set sets Set's sets Set's sets set Set's set\n"
            "Set Sets set sets' set\n"
            "Set Sets set sets' set"
        )
        out, err, rc = run(src)
        assert "out of bounds" in out

    def test_wrap_around_wrap(self):
        src = (
            "Set sets Set's sets Sets sets' Sets sets' Set's sets"
            " set Set's sets"
        )
        out, err, rc = run(src)
        assert out == "finished"


class TestIOAdversarial:

    def _run_with_stdin(self, program, stdin_input):
        prog_file = ROOT / "_test_adversarial_io.s5"
        try:
            prog_file.write_text(program, encoding="utf-8")
            p = subprocess.run(
                [sys.executable, "-m", "s5", str(prog_file)],
                input=stdin_input, capture_output=True, text=True, cwd=str(ROOT))
            return p.stdout.strip(), p.stderr.strip(), p.returncode
        finally:
            if prog_file.exists():
                prog_file.unlink()

    def test_io_in_B_position(self):
        src = "Set sets Set's sets set's' set Set's sets"
        out, err, rc = self._run_with_stdin(src, "3\n")
        assert rc == 0

    def test_input_non_integer(self):
        src = "Set sets set's' Set's sets set Set's sets"
        out, err, rc = self._run_with_stdin(src, "abc\n")
        assert "expected integer" in err
        assert rc != 0

    def test_input_negative(self):
        src = "Set sets set's' Set's sets set Set's sets"
        out, err, rc = self._run_with_stdin(src, "-5\n")
        assert rc == 0
