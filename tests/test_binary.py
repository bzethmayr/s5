import os
import subprocess
import sys
from pathlib import Path

import pytest

from s5 import (
    TokenType,
    TokenizerError,
    tokenize,
    Parser,
    Executor,
    S5Set,
    set_value,
    int_to_s5set,
    encode_tokens,
    decode_tokens,
    sniff,
)

HERE = Path(__file__).parent
ROOT = HERE.parent

ALL_TOKENS = [
    TokenType.SINGULAR,
    TokenType.SINGULAR_LOWER,
    TokenType.PLURAL_LOWER,
    TokenType.SINGULAR_APOS,
    TokenType.PLURAL_APOS,
    TokenType.PLURAL_CAP,
    TokenType.PLURAL_CAP_APOS,
    TokenType.SINGULAR_LOWER_APOS_APOS,
]


def run(inp):
    p = subprocess.run(
        [sys.executable, "-m", "s5", "--repl"],
        input=inp,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    return p.stdout.strip(), p.stderr.strip(), p.returncode


class TestPackUnpack:
    def test_all_tokens_self_pair(self):
        for tt in ALL_TOKENS:
            byte = encode_tokens([tt, tt])
            assert len(byte) == 1
            decoded = list(decode_tokens(byte))
            assert decoded == [tt, tt]

    def test_all_tokens_with_each_other(self):
        for t1 in ALL_TOKENS:
            for t2 in ALL_TOKENS:
                byte = encode_tokens([t1, t2])
                decoded = list(decode_tokens(byte))
                assert decoded == [t1, t2]

    def test_single_token(self):
        for tt in ALL_TOKENS:
            data = encode_tokens([tt])
            assert len(data) == 1
            decoded = list(decode_tokens(data))
            assert decoded == [tt]

    def test_odd_three_tokens(self):
        tokens = [
            TokenType.SINGULAR,
            TokenType.SINGULAR_LOWER,
            TokenType.PLURAL_LOWER,
        ]
        data = encode_tokens(tokens)
        assert len(data) == 2
        decoded = list(decode_tokens(data))
        assert decoded == tokens

    def test_odd_five_tokens(self):
        tokens = ALL_TOKENS[:5]
        data = encode_tokens(tokens)
        assert len(data) == 3
        decoded = list(decode_tokens(data))
        assert decoded == tokens

    def test_even_four_tokens(self):
        tokens = ALL_TOKENS[:4]
        data = encode_tokens(tokens)
        assert len(data) == 2
        decoded = list(decode_tokens(data))
        assert decoded == tokens

    def test_empty_stream(self):
        data = encode_tokens([])
        assert len(data) == 0
        decoded = list(decode_tokens(data))
        assert decoded == []


class TestParity:
    def test_normal_pair_parity(self):
        for t1 in ALL_TOKENS:
            for t2 in ALL_TOKENS:
                data = encode_tokens([t1, t2])
                byte = data[0]
                code1 = byte & 0x7
                p1 = (byte >> 3) & 1
                code2 = (byte >> 4) & 0x7
                p2 = (byte >> 7) & 1
                from s5.binary import _even_parity

                assert _even_parity(code1) == p1, f"parity mismatch t1={t1}"
                assert _even_parity(code2) == p2, f"parity mismatch t2={t2}"

    def test_end_marker_parity(self):
        for tt in ALL_TOKENS:
            data = encode_tokens([tt])
            assert len(data) == 1
            byte = data[0]
            code2 = (byte >> 4) & 0x7
            p2 = (byte >> 7) & 1
            assert code2 == 0, "end marker should have null code"
            assert p2 == 1, "end marker should have reversed parity (1)"


class TestSniff:
    def test_sniff_identifies_binary(self):
        for byte_val in [0x00, 0x06, 0x0C, 0x08, 0xFF, 0x01]:
            assert sniff(byte_val), f"binary byte 0x{byte_val:02x} should pass sniff"

    def test_sniff_rejects_text_capital_s(self):
        assert not sniff(0x53)

    def test_sniff_rejects_text_lowercase_s(self):
        assert not sniff(0x73)

    def test_sniff_rejects_all_text_starting_bytes(self):
        for ch in b"Ss":
            assert not sniff(ch), f"ASCII {chr(ch)!r} should not pass sniff"


class TestDecodeErrors:
    def test_parity_error_first_token(self):
        bad = bytes([0x01])
        with pytest.raises(TokenizerError, match="parity mismatch in first token"):
            list(decode_tokens(bad))

    def test_parity_error_second_token(self):
        bad = bytes([0x20])
        with pytest.raises(TokenizerError, match="parity mismatch in second token"):
            list(decode_tokens(bad))


class TestRoundtrip:
    def test_simple_union_program(self):
        src = "Set sets Set's sets Set's sets set set's'"
        tokens = tokenize(src)
        data = encode_tokens(tokens)
        decoded = list(decode_tokens(data))
        assert decoded == tokens
        parser = Parser(decoded)
        executor = Executor()
        status = executor.run(parser.parse_program())
        assert status == "finished"

    def test_halt_program(self):
        src = "Set set Set's sets Set's sets set Set's sets"
        tokens = tokenize(src)
        data = encode_tokens(tokens)
        decoded = list(decode_tokens(data))
        assert decoded == tokens

    def test_compute_42_program(self):
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
        data = encode_tokens(tokens)
        decoded = list(decode_tokens(data))
        assert decoded == tokens
        parser = Parser(decoded)
        executor = Executor()
        status = executor.run(parser.parse_program())
        assert status == "finished"
        assert set_value(executor.U) == 42

    def test_subroutine_program(self):
        src = (
            "Sets' Sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets'"
        )
        tokens = tokenize(src)
        data = encode_tokens(tokens)
        decoded = list(decode_tokens(data))
        assert decoded == tokens
        assert Executor().run(Parser(decoded).parse_program()) == "finished"

    def test_hello_world_roundtrip(self):
        prog_file = ROOT / "hello_world.s5"
        with open(prog_file, encoding="utf-8-sig") as f:
            src = f.read()
        tokens = tokenize(src)
        data = encode_tokens(tokens)
        decoded = list(decode_tokens(data))
        assert decoded == tokens


class TestCLIIntegration:
    def test_compile_and_run_binary(self):
        src = "Set sets Set's sets Set's sets set set's'"
        src_file = ROOT / "_test_compile.s5"
        bin_file = ROOT / "_test_compile.s5b"
        try:
            src_file.write_text(src, encoding="utf-8")
            p = subprocess.run(
                [sys.executable, "-m", "s5", "-c", str(src_file)],
                capture_output=True,
                cwd=str(ROOT),
            )
            assert p.returncode == 0, f"compile failed: {p.stderr}"
            assert bin_file.exists()

            p2 = subprocess.run(
                [sys.executable, "-m", "s5", str(bin_file)],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            assert p2.returncode == 0, f"run binary failed: {p2.stderr}"
            assert p2.stdout.strip() == "2"
        finally:
            if src_file.exists():
                src_file.unlink()
            if bin_file.exists():
                bin_file.unlink()

    def test_compile_no_extension(self):
        src = "Set sets Set's sets Set's sets set set's'"
        src_file = ROOT / "_test_noext.s5"
        bin_file = ROOT / "_test_noext.s5b"
        try:
            src_file.write_text(src, encoding="utf-8")
            p = subprocess.run(
                [sys.executable, "-m", "s5", "-c", "_test_noext"],
                capture_output=True,
                cwd=str(ROOT),
            )
            assert p.returncode == 0, f"compile failed: {p.stderr}"
            assert bin_file.exists()

            p2 = subprocess.run(
                [sys.executable, "-m", "s5", str(bin_file)],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            assert p2.returncode == 0
            assert p2.stdout.strip() == "2"
        finally:
            if src_file.exists():
                src_file.unlink()
            if bin_file.exists():
                bin_file.unlink()

    def test_compile_binary_source_rejected(self):
        src = "Set sets Set's sets Set's sets set set's'"
        src_file = ROOT / "_test_reject.s5"
        bin_file = ROOT / "_test_reject.s5b"
        try:
            src_file.write_text(src, encoding="utf-8")
            subprocess.run(
                [sys.executable, "-m", "s5", "-c", str(src_file)],
                capture_output=True,
                cwd=str(ROOT),
            )
            assert bin_file.exists()
            p = subprocess.run(
                [sys.executable, "-m", "s5", "-c", str(bin_file)],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            assert p.returncode != 0
            assert "already binary" in p.stderr
        finally:
            if src_file.exists():
                src_file.unlink()
            if bin_file.exists():
                bin_file.unlink()

    def test_auto_detect_binary_on_stdin(self):
        src = "Set set Set's sets Set's sets set Set's sets"
        data = encode_tokens(tokenize(src))
        p = subprocess.run(
            [sys.executable, "-m", "s5", "--repl"],
            input=data,
            capture_output=True,
            cwd=str(ROOT),
        )
        assert p.returncode == 0
        assert b"halted" in p.stdout

    def test_binary_file_produces_same_output_as_text(self):
        src = "Set sets Set's sets Set's sets set set's'"
        text_file = ROOT / "_test_compare.s5"
        bin_file = ROOT / "_test_compare.s5b"
        try:
            text_file.write_text(src, encoding="utf-8")

            subprocess.run(
                [sys.executable, "-m", "s5", "-c", str(text_file)],
                capture_output=True,
                cwd=str(ROOT),
            )

            p_text = subprocess.run(
                [sys.executable, "-m", "s5", str(text_file)],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            p_bin = subprocess.run(
                [sys.executable, "-m", "s5", str(bin_file)],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            assert p_text.returncode == p_bin.returncode
            assert p_text.stdout == p_bin.stdout
            assert p_text.stderr == p_bin.stderr
        finally:
            if text_file.exists():
                text_file.unlink()
            if bin_file.exists():
                bin_file.unlink()
