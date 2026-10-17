import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent


def run_cat(data):
    return subprocess.run(
        [sys.executable, "-m", "s5", str(ROOT / "cat.s5")],
        input=data, capture_output=True, cwd=str(ROOT))


class TestCat:
    def test_empty_stdin_terminates_with_empty_output(self):
        p = run_cat(b"")
        assert p.returncode == 0
        assert p.stderr == b""
        assert p.stdout == b""

    def test_echoes_text(self):
        p = run_cat(b"hello world\n")
        assert p.returncode == 0
        assert p.stdout == b"hello world\n"

    def test_echoes_zero_byte_distinct_from_eof(self):
        data = b"\x00\xff\n\r\t A"
        p = run_cat(data)
        assert p.returncode == 0
        assert p.stdout == data

    def test_echoes_full_byte_range(self):
        data = bytes(range(256))
        p = run_cat(data)
        assert p.returncode == 0
        assert p.stdout == data

    def test_echoes_large_input_without_recursion_limit(self):
        data = bytes(range(256)) * 400
        p = run_cat(data)
        assert p.returncode == 0
        assert p.stderr == b""
        assert p.stdout == data
