import io
import sys
from pathlib import Path

import pytest
from s5 import (
    TokenType,
    tokenize,
    Parser,
    Executor,
    AddressType,
    Address,
    SubroutineSet,
    LineSet,
    S5Set,
    set_value,
    int_to_s5set,
    encode_tokens,
    decode_tokens,
    _write_s5b,
    _read_s5b,
)
from s5.serialize import serialize_address, serialize_instruction, serialize_body, serialize_integer

HERE = Path(__file__).parent
ROOT = HERE.parent


class TestParseIO_S5B:
    def test_io_s5b_no_depth(self):
        addr = Parser(tokenize("sets sets set's'")).parse_address()
        assert addr.type == AddressType.IO_S5B
        assert not addr.has_depth
        assert addr.dispatch_depth == 1

    def test_io_s5b_with_depth(self):
        addr = Parser(tokenize("sets sets set's' sets' set sets")).parse_address()
        assert addr.type == AddressType.IO_S5B
        assert addr.has_depth
        assert addr.dispatch_depth == 3

    def test_io_byte_unchanged(self):
        addr = Parser(tokenize("sets set's'")).parse_address()
        assert addr.type == AddressType.IO_BYTE
        assert not addr.has_depth

    def test_io_unchanged(self):
        addr = Parser(tokenize("set's'")).parse_address()
        assert addr.type == AddressType.IO
        assert not addr.has_depth

    def test_too_many_sets_prefixes(self):
        with pytest.raises(Exception):
            Parser(tokenize("sets sets sets set's'")).parse_address()


class TestSerializeInteger:
    def test_0(self):
        assert serialize_integer(0) == []

    def test_1(self):
        assert serialize_integer(1) == [TokenType.SINGULAR_LOWER]

    def test_2(self):
        assert serialize_integer(2) == [TokenType.SINGULAR_LOWER, TokenType.PLURAL_LOWER]

    def test_3(self):
        assert serialize_integer(3) == [TokenType.SINGULAR_LOWER, TokenType.PLURAL_LOWER, TokenType.SINGULAR_LOWER]

    def test_4(self):
        assert serialize_integer(4) == [TokenType.SINGULAR_LOWER, TokenType.PLURAL_LOWER, TokenType.PLURAL_LOWER]

    def test_42(self):
        tokens = serialize_integer(42)
        parser = Parser(tokens)
        val = parser._parse_integer()
        assert val == 42

    def test_roundtrip_many(self):
        for n in range(1, 200):
            tokens = serialize_integer(n)
            parser = Parser(tokens)
            val = parser._parse_integer()
            assert val == n, f"roundtrip failed for {n}"


class TestSerializeAddress:
    def test_u(self):
        addr = Address(AddressType.U)
        assert serialize_address(addr) == [TokenType.SINGULAR_APOS, TokenType.PLURAL_LOWER]

    def test_c(self):
        addr = Address(AddressType.C)
        assert serialize_address(addr) == [TokenType.SINGULAR_APOS, TokenType.SINGULAR_LOWER]

    def test_derived(self):
        addr = Address(AddressType.DERIVED, index=3)
        tokens = serialize_address(addr)
        assert tokens[:3] == [TokenType.PLURAL_CAP, TokenType.SINGULAR_LOWER, TokenType.PLURAL_APOS]
        # Parse back
        parser = Parser(tokens)
        back = parser.parse_address()
        assert back.type == AddressType.DERIVED
        assert back.index == 3

    def test_ud(self):
        addr = Address(AddressType.UD, index=3)
        tokens = serialize_address(addr)
        assert tokens[:3] == [TokenType.PLURAL_CAP, TokenType.PLURAL_LOWER, TokenType.PLURAL_APOS]
        parser = Parser(tokens)
        back = parser.parse_address()
        assert back.type == AddressType.UD
        assert back.index == 3

    def test_wrap(self):
        inner = Address(AddressType.U)
        addr = Address(AddressType.WRAP, sub_addr=inner)
        tokens = serialize_address(addr)
        assert tokens[:2] == [TokenType.PLURAL_CAP, TokenType.PLURAL_APOS]
        parser = Parser(tokens)
        back = parser.parse_address()
        assert back.type == AddressType.WRAP
        assert back.sub_addr.type == AddressType.U

    def test_io(self):
        addr = Address(AddressType.IO)
        assert serialize_address(addr) == [TokenType.SINGULAR_LOWER_APOS_APOS]

    def test_io_byte(self):
        addr = Address(AddressType.IO_BYTE)
        assert serialize_address(addr) == [TokenType.PLURAL_LOWER, TokenType.SINGULAR_LOWER_APOS_APOS]

    def test_io_s5b(self):
        addr = Address(AddressType.IO_S5B)
        assert serialize_address(addr) == [TokenType.PLURAL_LOWER, TokenType.PLURAL_LOWER, TokenType.SINGULAR_LOWER_APOS_APOS]

    def test_has_depth(self):
        addr = Address(AddressType.U)
        addr.has_depth = True
        addr.dispatch_depth = 3
        tokens = serialize_address(addr)
        assert tokens[-3:] == [TokenType.PLURAL_APOS, TokenType.SINGULAR_LOWER, TokenType.PLURAL_LOWER]

    def test_address_parse_roundtrip(self):
        sources = [
            "Set's sets",
            "Set's set",
            "Sets set sets' set sets",
            "Sets sets sets' set",
            "Sets sets' Set's sets",
            "set's'",
            "sets set's'",
            "sets sets set's'",
        ]
        for src in sources:
            addr = Parser(tokenize(src)).parse_address()
            tokens = serialize_address(addr)
            back = Parser(tokens).parse_address()
            assert back.type == addr.type
            assert back.has_depth == addr.has_depth
            assert back.dispatch_depth == addr.dispatch_depth
            if back.index is not None:
                assert back.index == addr.index


class TestSerializeInstruction:
    SIMPLE_UNION = "Set sets Set's sets Set's sets set Set's set"

    def test_union_roundtrip(self):
        src = self.SIMPLE_UNION
        instrs = Parser(tokenize(src)).parse_program()
        assert len(instrs) == 1
        tokens = serialize_instruction(instrs[0])
        back = Parser(tokens).parse_instruction()
        assert back.opcode == instrs[0].opcode
        assert back.addr_a.type == instrs[0].addr_a.type
        assert back.addr_b.type == instrs[0].addr_b.type
        assert back.addr_dest.type == instrs[0].addr_dest.type

    def test_program_roundtrip(self):
        src = (
            "Set sets Set's sets Set's sets set Set's set\n"
            "Set Set's Set's set Set's set set Set's sets\n"
            "Set set Set's sets Set's sets set Set's set"
        )
        instrs = Parser(tokenize(src)).parse_program()
        tokens = serialize_body(instrs)
        back = Parser(tokens).parse_program()
        assert len(back) == len(instrs)
        for i, (a, b) in enumerate(zip(back, instrs)):
            assert a.opcode == b.opcode, f"instr {i} opcode mismatch"

    def test_subroutine_serialization(self):
        src = (
            "Sets' Sets' Set's sets\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set sets Set's sets Set's sets set Set's set\n"
            "Set set Set's set Set's set set Set's set\n"
            "Set Sets' set Set's set"
        )
        instrs = Parser(tokenize(src)).parse_program()
        tokens = serialize_body(instrs)
        back = Parser(tokens).parse_program()
        assert len(back) == len(instrs)
        assert back[0].opcode == instrs[0].opcode
        assert back[0].subr_body is not None
        assert back[1].opcode == instrs[1].opcode
        assert back[1].subr_body is None
        assert back[3].opcode == instrs[3].opcode
        assert back[3].subr_body is None


class TestWriteS5B:
    def test_write_subroutineset_roundtrip(self):
        src = "Set sets Set's sets Set's sets set Set's set"
        instrs = Parser(tokenize(src)).parse_program()
        body = SubroutineSet(instrs, [LineSet(i) for i in instrs], io_s5b=True)
        data = _write_s5b(body)
        back = _read_s5b(data)
        assert isinstance(back, SubroutineSet)
        assert len(back._body) == 1
        assert back._body[0].opcode == instrs[0].opcode

    def test_write_plain_set_roundtrip(self):
        for n in [0, 1, 2, 3, 5, 10, 42, 100, 255]:
            expected = int_to_s5set(n)
            data = _write_s5b(expected)
            tokens = list(decode_tokens(data))
            codes = [0, 1, 2, 3, 4, 5, 6, 7]
            code_map = {0: TokenType.SINGULAR, 1: TokenType.SINGULAR_LOWER,
                        2: TokenType.PLURAL_LOWER, 3: TokenType.SINGULAR_APOS,
                        4: TokenType.PLURAL_APOS, 5: TokenType.PLURAL_CAP,
                        6: TokenType.PLURAL_CAP_APOS, 7: TokenType.SINGULAR_LOWER_APOS_APOS}
            rev = {v: k for k, v in code_map.items()}
            codes_found = [rev[t] for t in tokens]
            n_rebuilt = 0
            for c in codes_found:
                n_rebuilt = (n_rebuilt << 3) | c
            assert n_rebuilt == n, f"roundtrip failed for {n}: got {n_rebuilt}"

    def test_extend_subroutine_via_s5b(self):
        src1 = "Set sets Set's sets Set's sets set Set's sets"
        instrs1 = Parser(tokenize(src1)).parse_program()

        src2 = "Set sets Set's sets Set's sets set Set's sets"
        instrs2 = Parser(tokenize(src2)).parse_program()

        base_tokens = serialize_body(instrs1)
        extra_tokens = serialize_body(instrs2)
        all_tokens = base_tokens + extra_tokens
        all_data = encode_tokens(all_tokens)

        extended = _read_s5b(all_data)

        assert isinstance(extended, SubroutineSet)
        assert len(extended._body) == 2
        assert extended._body[0].opcode == instrs1[0].opcode
        assert extended._body[1].opcode == instrs2[0].opcode
        assert extended._io_s5b

        executor = Executor()
        executor.run(extended._body)
        assert len(executor.U) == 4


class TestExecutorIOS5B:
    def test_read_s5b_via_stdin(self):
        src = "Set sets Set's sets Set's sets set Set's set"
        instrs = Parser(tokenize(src)).parse_program()
        subr = SubroutineSet(instrs, [LineSet(i) for i in instrs], io_s5b=True)
        data = _write_s5b(subr)
        old_in = sys.stdin
        try:
            buf = io.BytesIO(data)
            sys.stdin = io.TextIOWrapper(buf, encoding='latin-1')
            executor = Executor()
            addr = Parser(tokenize("sets sets set's'")).parse_address()
            result = executor.resolve(addr)
            assert isinstance(result, SubroutineSet)
            assert result._io_s5b
        finally:
            sys.stdin = old_in

    def test_write_s5b_via_stdout(self):
        executor = Executor()
        addr = Address(AddressType.IO_S5B)
        instrs = Parser(tokenize("Set sets Set's sets Set's sets set Set's set")).parse_program()
        value = SubroutineSet(instrs, [LineSet(i) for i in instrs], io_s5b=True)
        buf = io.BytesIO()
        old_out = sys.stdout
        try:
            sys.stdout = io.TextIOWrapper(buf, encoding='latin-1')
            executor.assign(addr, value)
            sys.stdout.flush()
            data = buf.getvalue()
        finally:
            sys.stdout = old_out
        back = _read_s5b(data)
        assert isinstance(back, SubroutineSet)
        assert len(back._body) == 1

    def test_execute_via_union_opcode(self):
        inner = "Set sets Set's sets Set's sets set Set's sets"
        inner_instrs = Parser(tokenize(inner)).parse_program()
        subr = SubroutineSet(inner_instrs, [LineSet(i) for i in inner_instrs], io_s5b=True)
        s5b_data = _write_s5b(subr)
        old_in = sys.stdin
        try:
            buf = io.BytesIO(s5b_data)
            sys.stdin = io.TextIOWrapper(buf, encoding='latin-1')
            src = (
                "Set sets sets sets set's' Set's sets set Set's set"
            )
            instrs = Parser(tokenize(src)).parse_program()
            executor = Executor()
            status = executor.run(instrs)
            assert set_value(executor.C) == 2
        finally:
            sys.stdin = old_in

    def test_plain_set_write_via_stdout(self):
        executor = Executor()
        addr = Address(AddressType.IO_S5B)
        value = int_to_s5set(42)
        buf = io.BytesIO()
        old_out = sys.stdout
        try:
            sys.stdout = io.TextIOWrapper(buf, encoding='latin-1')
            executor.assign(addr, value)
            sys.stdout.flush()
            data = buf.getvalue()
        finally:
            sys.stdout = old_out
        tokens = list(decode_tokens(data))
        code_map = {v: k for k, v in {0: TokenType.SINGULAR, 1: TokenType.SINGULAR_LOWER,
                                       2: TokenType.PLURAL_LOWER, 3: TokenType.SINGULAR_APOS,
                                       4: TokenType.PLURAL_APOS, 5: TokenType.PLURAL_CAP,
                                       6: TokenType.PLURAL_CAP_APOS, 7: TokenType.SINGULAR_LOWER_APOS_APOS}.items()}
        n = 0
        for t in tokens:
            n = (n << 3) | code_map[t]
        assert n == 42


class TestIOS5BWithFd:
    def test_write_to_fd1_goes_to_stdout_and_buffer(self):
        io_handler = __import__('s5.io_handler', fromlist=['IOHandler']).IOHandler
        handler = io_handler(buf_sizes={1: 1024})
        instrs = Parser(tokenize("Set sets Set's sets Set's sets set Set's set")).parse_program()
        value = SubroutineSet(instrs, [LineSet(i) for i in instrs], io_s5b=True)
        buf = io.BytesIO()
        old_out = sys.stdout
        try:
            sys.stdout = io.TextIOWrapper(buf, encoding='latin-1')
            handler.assign(AddressType.IO_S5B, 1, value)
            sys.stdout.flush()
            written = buf.getvalue()
        finally:
            sys.stdout = old_out
        assert len(written) > 0
        back = _read_s5b(written)
        assert isinstance(back, SubroutineSet)
        assert len(back._body) == 1

    def test_write_fd0_populates_buffer_only(self):
        io_handler = __import__('s5.io_handler', fromlist=['IOHandler']).IOHandler
        handler = io_handler(buf_sizes={0: 1024})
        instrs = Parser(tokenize("Set sets Set's sets Set's sets set Set's set")).parse_program()
        value = SubroutineSet(instrs, [LineSet(i) for i in instrs], io_s5b=True)
        buf = io.BytesIO()
        old_out = sys.stdout
        try:
            sys.stdout = io.TextIOWrapper(buf, encoding='latin-1')
            handler.assign(AddressType.IO_S5B, 0, value)
            sys.stdout.flush()
            captured = buf.getvalue()
        finally:
            sys.stdout = old_out
        assert captured == b''

        raw = handler._read_all(0)
        assert raw is not None
        back = _read_s5b(raw)
        assert isinstance(back, SubroutineSet)

    def test_read_fd0_from_buffer(self):
        io_handler = __import__('s5.io_handler', fromlist=['IOHandler']).IOHandler
        handler = io_handler(buf_sizes={0: 1024})
        instrs = Parser(tokenize("Set sets Set's sets Set's sets set Set's set")).parse_program()
        value = SubroutineSet(instrs, [LineSet(i) for i in instrs], io_s5b=True)
        data = _write_s5b(value)
        handler._append(0, data)
        result = handler.resolve(AddressType.IO_S5B, 0)
        assert isinstance(result, SubroutineSet)
        assert len(result._body) == 1

    def test_read_fd1_buffer_empty_raises(self):
        io_handler = __import__('s5.io_handler', fromlist=['IOHandler']).IOHandler
        handler = io_handler()
        with pytest.raises(Exception):
            handler.resolve(AddressType.IO_S5B, 1)
