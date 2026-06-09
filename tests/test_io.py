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

    def test_hello_golfed_via_file_mode(self):
        prog_file = ROOT / "hello_golfed.s5"
        p = subprocess.run(
            [sys.executable, "-m", "s5", str(prog_file)],
            capture_output=True, text=True, cwd=str(ROOT))
        assert p.returncode == 0
        assert p.stdout == "Hello, World!"


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


class TestIOWithFd:
    def test_parse_has_depth_with_suffix(self):
        addr = Parser(tokenize("set's' sets' set")).parse_address()
        assert addr.type == AddressType.IO
        assert addr.dispatch_depth == 2
        assert addr.has_depth

    def test_parse_no_has_depth_without_suffix(self):
        addr = Parser(tokenize("set's'")).parse_address()
        assert addr.type == AddressType.IO
        assert addr.dispatch_depth == 1
        assert not addr.has_depth

    def test_parse_has_depth_zero_inc(self):
        addr = Parser(tokenize("set's' sets' sets")).parse_address()
        assert addr.type == AddressType.IO
        assert addr.dispatch_depth == 1
        assert addr.has_depth

    def test_parse_byte_io_has_depth(self):
        addr = Parser(tokenize("sets set's' sets' set sets")).parse_address()
        assert addr.type == AddressType.IO_BYTE
        assert addr.dispatch_depth == 3
        assert addr.has_depth

    def _io_addr(self, depth):
        addr = Address(AddressType.IO, dispatch_depth=depth)
        addr.has_depth = True
        return addr

    def _byte_io_addr(self, depth):
        addr = Address(AddressType.IO_BYTE, dispatch_depth=depth)
        addr.has_depth = True
        return addr

    def test_write_integer_to_fd1_goes_to_stdout_and_buffer(self):
        executor = Executor(buf_sizes={1: 1024})
        addr = self._io_addr(2)
        value = int_to_s5set(42)
        captured = io.StringIO()
        old_out = sys.stdout
        try:
            sys.stdout = captured
            executor.assign(addr, value)
        finally:
            sys.stdout = old_out
        assert captured.getvalue().strip() == "42"
        assert bytes(executor._io._bufs[1]) == b"42\n"

    def test_write_integer_to_fd2_goes_to_stderr_and_buffer(self):
        executor = Executor(buf_sizes={2: 1024})
        addr = self._io_addr(3)
        value = int_to_s5set(99)
        captured = io.StringIO()
        old_err = sys.stderr
        try:
            sys.stderr = captured
            executor.assign(addr, value)
        finally:
            sys.stderr = old_err
        assert captured.getvalue().strip() == "99"
        assert bytes(executor._io._bufs[2]) == b"99\n"

    def test_write_integer_to_fd0_populates_buffer_only(self):
        executor = Executor(buf_sizes={0: 1024})
        addr = self._io_addr(1)
        value = int_to_s5set(42)
        captured_out = io.StringIO()
        old_out = sys.stdout
        try:
            sys.stdout = captured_out
            executor.assign(addr, value)
        finally:
            sys.stdout = old_out
        assert captured_out.getvalue() == ""
        assert bytes(executor._io._bufs[0]) == b"42\n"

    def test_read_integer_from_fd0_uses_buffer_before_stdin(self):
        executor = Executor(buf_sizes={0: 1024})
        executor._io._bufs[0] = bytearray(b"100\n")
        addr = self._io_addr(1)
        result = executor.resolve(addr)
        assert set_value(result) == 100
        assert len(executor._io._bufs[0]) == 0

    def test_read_integer_from_fd0_falls_back_to_stdin(self):
        executor = Executor(buf_sizes={0: 1024})
        addr = self._io_addr(1)
        old_in = sys.stdin
        try:
            sys.stdin = io.StringIO("77\n")
            result = executor.resolve(addr)
        finally:
            sys.stdin = old_in
        assert set_value(result) == 77

    def test_read_integer_from_fd1_reads_buffer(self):
        executor = Executor(buf_sizes={1: 1024})
        executor._io._bufs[1] = bytearray(b"42\n")
        addr = self._io_addr(2)
        result = executor.resolve(addr)
        assert set_value(result) == 42

    def test_read_integer_from_fd2_reads_buffer(self):
        executor = Executor(buf_sizes={2: 1024})
        executor._io._bufs[2] = bytearray(b"123\n")
        addr = self._io_addr(3)
        result = executor.resolve(addr)
        assert set_value(result) == 123

    def test_read_integer_from_output_fd_empty_raises(self):
        executor = Executor(buf_sizes={1: 1024})
        addr = self._io_addr(2)
        with pytest.raises(Exception, match="buffer empty"):
            executor.resolve(addr)

    def test_write_then_read_integer_through_fd1(self):
        executor = Executor(buf_sizes={1: 1024})
        write_addr = self._io_addr(2)
        read_addr = self._io_addr(2)
        captured = io.StringIO()
        old_out = sys.stdout
        try:
            sys.stdout = captured
            executor.assign(write_addr, int_to_s5set(42))
        finally:
            sys.stdout = old_out
        result = executor.resolve(read_addr)
        assert set_value(result) == 42

    def test_write_then_read_integer_through_fd2(self):
        executor = Executor(buf_sizes={2: 1024})
        write_addr = self._io_addr(3)
        read_addr = self._io_addr(3)
        captured = io.StringIO()
        old_err = sys.stderr
        try:
            sys.stderr = captured
            executor.assign(write_addr, int_to_s5set(255))
        finally:
            sys.stderr = old_err
        result = executor.resolve(read_addr)
        assert set_value(result) == 255

    def test_buffer_tail_with_size_limit(self):
        executor = Executor(buf_sizes={1: 10})
        addr = self._io_addr(2)
        captured = io.StringIO()
        old_out = sys.stdout
        try:
            sys.stdout = captured
            executor.assign(addr, int_to_s5set(12345))
        finally:
            sys.stdout = old_out
        assert len(executor._io._bufs[1]) <= 10

    def test_buffer_size_zero_discards_data(self):
        executor = Executor(buf_sizes={1: 0})
        addr = self._io_addr(2)
        captured = io.StringIO()
        old_out = sys.stdout
        try:
            sys.stdout = captured
            executor.assign(addr, int_to_s5set(42))
        finally:
            sys.stdout = old_out
        assert len(executor._io._bufs[1]) == 0
        assert captured.getvalue().strip() == "42"

    def test_write_byte_to_fd1_goes_to_stdout_and_buffer(self):
        executor = Executor(buf_sizes={1: 1024})
        addr = self._byte_io_addr(2)
        value = int_to_s5set(0xAB)
        buf = io.BytesIO()
        old_out = sys.stdout
        try:
            sys.stdout = io.TextIOWrapper(buf, encoding='latin-1')
            executor.assign(addr, value)
            sys.stdout.flush()
            result = buf.getvalue()
        finally:
            sys.stdout = old_out
        assert result == b'\xAB'
        assert bytes(executor._io._bufs[1]) == b'\xAB'

    def test_read_byte_from_fd0_uses_buffer(self):
        executor = Executor(buf_sizes={0: 1024})
        executor._io._bufs[0] = bytearray(b'\x2A')
        addr = self._byte_io_addr(1)
        result = executor.resolve(addr)
        assert set_value(result) == 42

    def test_write_then_read_byte_through_fd1(self):
        executor = Executor(buf_sizes={1: 1024})
        write_addr = self._byte_io_addr(2)
        read_addr = self._byte_io_addr(2)
        buf = io.BytesIO()
        old_out = sys.stdout
        try:
            sys.stdout = io.TextIOWrapper(buf, encoding='latin-1')
            executor.assign(write_addr, int_to_s5set(200))
            sys.stdout.flush()
        finally:
            sys.stdout = old_out
        read_result = executor.resolve(read_addr)
        assert set_value(read_result) == 200

    def test_write_byte_to_fd2_goes_to_stderr_and_buffer(self):
        executor = Executor(buf_sizes={2: 1024})
        addr = self._byte_io_addr(3)
        value = int_to_s5set(0x42)
        captured = io.BytesIO()
        old_err = sys.stderr
        try:
            sys.stderr = io.TextIOWrapper(captured, encoding='latin-1')
            executor.assign(addr, value)
            sys.stderr.flush()
            result = captured.getvalue()
        finally:
            sys.stderr = old_err
        assert result == b'\x42'
        assert bytes(executor._io._bufs[2]) == b'\x42'

    def test_positional_io_ignores_buffer(self):
        executor = Executor(buf_sizes={0: 1024})
        executor._io._bufs[0] = bytearray(b"999\n")
        addr = Address(AddressType.IO)
        old_in = sys.stdin
        try:
            sys.stdin = io.StringIO("42\n")
            result = executor.resolve(addr)
        finally:
            sys.stdin = old_in
        assert set_value(result) == 42
