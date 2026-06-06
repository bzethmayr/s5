import sys
import subprocess
import io
from pathlib import Path
import pytest
from s5 import (tokenize, Parser, Executor, int_to_s5set, set_value, S5Set,
                TokenType, Address, AddressType)

HERE = Path(__file__).parent
ROOT = HERE.parent


def run(inp):
    p = subprocess.run(
        [sys.executable, "-m", "s5", "--repl"],
        input=inp, capture_output=True, text=True, cwd=str(ROOT))
    return p.stdout.strip(), p.stderr.strip(), p.returncode


class TestIntToS5Set:
    def test_zero(self):
        assert len(int_to_s5set(0)) == 0

    def test_one(self):
        s = int_to_s5set(1)
        assert len(s) == 1
        assert len(s[0]) == 0

    def test_two(self):
        s = int_to_s5set(2)
        assert len(s) == 2
        assert len(s[0]) == 0
        assert len(s[1]) == 1
        assert len(s[1][0]) == 0

    def test_three(self):
        s = int_to_s5set(3)
        assert len(s) == 3
        assert len(s[0]) == 0
        assert len(s[1]) == 1
        assert len(s[1][0]) == 0
        assert len(s[2]) == 0

    def test_42_roundtrip(self):
        assert set_value(int_to_s5set(42)) == 42

    def test_roundtrip_many(self):
        for n in [0, 1, 2, 3, 5, 13, 42, 100, 255, 256]:
            assert set_value(int_to_s5set(n)) == n


class TestIOToken:
    def test_tokenize(self):
        tokens = tokenize("set's'")
        assert tokens == [TokenType.SINGULAR_LOWER_APOS_APOS]
        assert len(tokens) == 1

    def test_parse_address(self):
        parser = Parser([TokenType.SINGULAR_LOWER_APOS_APOS])
        addr = parser.parse_address()
        assert addr.type == AddressType.IO

    def test_assign_output(self):
        executor = Executor()
        addr = Address(AddressType.IO)
        value = int_to_s5set(42)
        captured = io.StringIO()
        old_out = sys.stdout
        try:
            sys.stdout = captured
            executor.assign(addr, value)
        finally:
            sys.stdout = old_out
        assert captured.getvalue().strip() == "42"

    def test_resolve_input(self):
        executor = Executor()
        addr = Address(AddressType.IO)
        old_in = sys.stdin
        try:
            sys.stdin = io.StringIO("42\n")
            result = executor.resolve(addr)
        finally:
            sys.stdin = old_in
        assert set_value(result) == 42


class TestIOIntegration:
    def test_output_via_subprocess(self):
        src = "Set Set's Set's sets Set's sets set Set's set"
        out, err, rc = run(src)
        assert "finished" in out
        assert rc == 0

    def test_output_union_u_u(self):
        src = "Set sets Set's sets Set's sets set set's'"
        out, err, rc = run(src)
        lines = out.splitlines()
        assert lines[0] == "2"
        assert "finished" in lines[1]

    def test_input_via_file_mode(self):
        program = "Set sets set's' Set's sets set Set's sets"
        prog_file = ROOT / "_test_io_input.s5"
        try:
            prog_file.write_text(program, encoding="utf-8")
            p = subprocess.run(
                [sys.executable, "-m", "s5", str(prog_file)],
                input="7\n", capture_output=True, text=True, cwd=str(ROOT))
            assert p.returncode == 0
        finally:
            if prog_file.exists():
                prog_file.unlink()

    def test_hello_world_via_file_mode(self):
        prog_file = ROOT / "hello_world.s5"
        p = subprocess.run(
            [sys.executable, "-m", "s5", str(prog_file)],
            capture_output=True, text=True, cwd=str(ROOT))
        assert p.returncode == 0
        assert p.stdout == "Hello World!"


class TestByteIO:
    def test_tokenize(self):
        tokens = tokenize("sets set's'")
        assert tokens == [TokenType.PLURAL_LOWER, TokenType.SINGULAR_LOWER_APOS_APOS]

    def test_parse_address(self):
        parser = Parser([TokenType.PLURAL_LOWER, TokenType.SINGULAR_LOWER_APOS_APOS])
        addr = parser.parse_address()
        assert addr.type == AddressType.IO_BYTE

    def test_parse_address_rejected_no_io(self):
        parser = Parser([TokenType.PLURAL_LOWER])
        with pytest.raises(Exception):
            parser.parse_address()

    def test_resolve_input(self):
        executor = Executor()
        addr = Address(AddressType.IO_BYTE)
        old_in = sys.stdin
        try:
            sys.stdin = io.TextIOWrapper(io.BytesIO(b'\x2A'), encoding='latin-1')
            result = executor.resolve(addr)
        finally:
            sys.stdin = old_in
        assert set_value(result) == 42

    def test_assign_output_single_byte(self):
        executor = Executor()
        addr = Address(AddressType.IO_BYTE)
        value = int_to_s5set(42)
        buf = io.BytesIO()
        old_out = sys.stdout
        try:
            sys.stdout = io.TextIOWrapper(buf, encoding='latin-1')
            executor.assign(addr, value)
            sys.stdout.flush()
            result = buf.getvalue()
        finally:
            sys.stdout = old_out
        assert result == b'\x2A'

    def test_assign_output_multi_byte(self):
        executor = Executor()
        addr = Address(AddressType.IO_BYTE)
        value = int_to_s5set(256)
        buf = io.BytesIO()
        old_out = sys.stdout
        try:
            sys.stdout = io.TextIOWrapper(buf, encoding='latin-1')
            executor.assign(addr, value)
            sys.stdout.flush()
            result = buf.getvalue()
        finally:
            sys.stdout = old_out
        assert result == b'\x00\x01'

    def test_assign_output_zero(self):
        executor = Executor()
        addr = Address(AddressType.IO_BYTE)
        value = int_to_s5set(0)
        buf = io.BytesIO()
        old_out = sys.stdout
        try:
            sys.stdout = io.TextIOWrapper(buf, encoding='latin-1')
            executor.assign(addr, value)
            sys.stdout.flush()
            result = buf.getvalue()
        finally:
            sys.stdout = old_out
        assert result == b'\x00'

    def test_assign_output_large(self):
        executor = Executor()
        addr = Address(AddressType.IO_BYTE)
        value = int_to_s5set(0x01020304)
        buf = io.BytesIO()
        old_out = sys.stdout
        try:
            sys.stdout = io.TextIOWrapper(buf, encoding='latin-1')
            executor.assign(addr, value)
            sys.stdout.flush()
            result = buf.getvalue()
        finally:
            sys.stdout = old_out
        assert result == b'\x04\x03\x02\x01'

    def test_byte_output_via_file_mode(self):
        program = "Set sets Set's sets Set's sets set sets set's'"
        prog_file = ROOT / "_test_byte_output.s5"
        try:
            prog_file.write_text(program, encoding="utf-8")
            p = subprocess.run(
                [sys.executable, "-m", "s5", str(prog_file)],
                capture_output=True, cwd=str(ROOT))
            assert p.returncode == 0
            assert b'\x02' in p.stdout
        finally:
            if prog_file.exists():
                prog_file.unlink()
