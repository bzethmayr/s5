import sys


class TokenType:
    SINGULAR = "SINGULAR"
    SINGULAR_LOWER = "SINGULAR_LOWER"
    PLURAL_LOWER = "PLURAL_LOWER"
    SINGULAR_APOS = "SINGULAR_APOS"
    PLURAL_APOS = "PLURAL_APOS"
    PLURAL_CAP = "PLURAL_CAP"
    PLURAL_CAP_APOS = "PLURAL_CAP_APOS"
    SINGULAR_LOWER_APOS_APOS = "SINGULAR_LOWER_APOS_APOS"


WORD_MAP = {
    "Set": TokenType.SINGULAR,
    "set": TokenType.SINGULAR_LOWER,
    "sets": TokenType.PLURAL_LOWER,
    "Set's": TokenType.SINGULAR_APOS,
    "sets'": TokenType.PLURAL_APOS,
    "Sets": TokenType.PLURAL_CAP,
    "Sets'": TokenType.PLURAL_CAP_APOS,
    "set's'": TokenType.SINGULAR_LOWER_APOS_APOS,
}

TOKEN_DISPLAY = {v: k for k, v in WORD_MAP.items()}


def token(tt):
    return TOKEN_DISPLAY[tt]


def token_or(tt):
    return TOKEN_DISPLAY.get(tt, tt)


class Opcode:
    SUBSET_SELECT = "SUBSET_SELECT"
    UNION = "UNION"
    INTERSECTION = "INTERSECTION"
    DIFFERENCE = "DIFFERENCE"
    SUBR = "SUBR"


class AddressType:
    U = "U"
    C = "C"
    DERIVED = "DERIVED"
    UD = "UD"
    WRAP = "WRAP"
    IO = "IO"
    IO_BYTE = "IO_BYTE"
    IO_S5B = "IO_S5B"


class Address:
    __slots__ = ("type", "index", "sub_addr", "dispatch_depth", "has_depth")

    def __init__(self, addr_type, index=None, sub_addr=None, dispatch_depth=1):
        self.type = addr_type
        self.index = index
        self.sub_addr = sub_addr
        self.dispatch_depth = dispatch_depth
        self.has_depth = False


class Instruction:
    __slots__ = ("opcode", "n", "addr_a", "addr_b", "addr_dest", "subr_body")

    def __init__(
        self, opcode, n=None, addr_a=None, addr_b=None, addr_dest=None, subr_body=None
    ):
        self.opcode = opcode
        self.n = n
        self.addr_a = addr_a
        self.addr_b = addr_b
        self.addr_dest = addr_dest
        self.subr_body = subr_body


class TokenizerError(Exception):
    pass


class SyntaxError_(Exception):
    pass


class RuntimeError_(Exception):
    pass


def tokenize(source):
    tokens = []
    for word in source.split():
        token = WORD_MAP.get(word)
        if token is None:
            raise TokenizerError(f"unknown token: {word!r}")
        tokens.append(token)
    return tokens


def tokenize_files(file_paths):
    for path in file_paths:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                for word in line.split():
                    token = WORD_MAP.get(word)
                    if token is None:
                        raise TokenizerError(f"unknown token: {word!r}")
                    yield token


class Parser:
    def __init__(self, token_stream, lookahead=3):
        self._it = iter(token_stream)
        self._lookahead = lookahead
        self._buf = []
        self._refill()

    def _refill(self):
        while len(self._buf) < self._lookahead:
            try:
                self._buf.append(next(self._it))
            except StopIteration:
                break

    def peek(self, offset=0):
        if offset >= len(self._buf):
            return None
        return self._buf[offset]

    def consume(self):
        if not self._buf:
            raise SyntaxError_("unexpected end of input")
        t = self._buf.pop(0)
        self._refill()
        return t

    def expect(self, tt):
        t = self.consume()
        if t != tt:
            raise SyntaxError_(f"expected {token(tt)}, got {token_or(t)}")
        return t

    def parse_program(self):
        instructions = []
        while self.peek() is not None:
            t = self.peek()
            if t == TokenType.PLURAL_CAP_APOS:
                self.consume()
                if self.peek() == TokenType.PLURAL_CAP_APOS:
                    self.consume()
                    loc = None
                    t2 = self.peek()
                    if t2 in (TokenType.SINGULAR_APOS, TokenType.PLURAL_CAP):
                        loc = self.parse_address()
                    body = []
                    while self.peek() == TokenType.SINGULAR:
                        body.append(self.parse_instruction())
                    if self.peek() != TokenType.PLURAL_CAP_APOS:
                        raise SyntaxError_(f"expected {token(TokenType.PLURAL_CAP_APOS)} to end subroutine")
                    self.consume()
                    instructions.append(
                        Instruction(Opcode.SUBR, subr_body=body, addr_a=loc)
                    )
                else:
                    raise SyntaxError_("unexpected bare Sets'")
            else:
                instructions.append(self.parse_instruction())
        return instructions

    def parse_instruction(self):
        self.expect(TokenType.SINGULAR)
        opcode = self.parse_opcode()
        return self.parse_operands(opcode)

    def parse_opcode(self):
        t = self.peek()
        if t == TokenType.PLURAL_CAP:
            self.consume()
            self.expect(TokenType.SINGULAR_LOWER)
            return Opcode.SUBSET_SELECT
        elif t == TokenType.PLURAL_LOWER:
            self.consume()
            return Opcode.UNION
        elif t == TokenType.SINGULAR_APOS:
            self.consume()
            return Opcode.INTERSECTION
        elif t == TokenType.SINGULAR_LOWER:
            self.consume()
            return Opcode.DIFFERENCE
        elif t == TokenType.PLURAL_CAP_APOS:
            self.consume()
            return Opcode.SUBR
        elif t is None:
            raise SyntaxError_("expected opcode, got end of input")
        else:
            raise SyntaxError_(f"expected opcode, got {token_or(t)}")

    def parse_operands(self, opcode):
        if opcode == Opcode.SUBSET_SELECT:
            self.expect(TokenType.PLURAL_APOS)
            t = self.peek()
            if t is not None:
                if t in (TokenType.SINGULAR_APOS, TokenType.PLURAL_CAP, TokenType.SINGULAR_LOWER_APOS_APOS):
                    addr = self.parse_address()
                    return Instruction(opcode, addr_b=addr)
                if t == TokenType.PLURAL_LOWER:
                    t1 = self.peek(1)
                    if t1 == TokenType.SINGULAR_LOWER_APOS_APOS:
                        addr = self.parse_address()
                        return Instruction(opcode, addr_b=addr)
                    if t1 == TokenType.PLURAL_LOWER and self.peek(2) == TokenType.SINGULAR_LOWER_APOS_APOS:
                        addr = self.parse_address()
                        return Instruction(opcode, addr_b=addr)
            n = self._parse_integer()
            return Instruction(opcode, n=n)
        elif opcode == Opcode.SUBR:
            t = self.peek()
            if t == TokenType.SINGULAR_LOWER:
                self.consume()
                cond = self.parse_address()
                subr_addr = None
                if self.peek() in (TokenType.SINGULAR_APOS, TokenType.PLURAL_CAP):
                    subr_addr = self.parse_address()
                return Instruction(opcode, addr_a=subr_addr, addr_b=cond)
            loc = None
            if t in (TokenType.SINGULAR_APOS, TokenType.PLURAL_CAP):
                loc = self.parse_address()
            return Instruction(opcode, addr_a=loc)
        else:
            a = self.parse_address()
            b = self.parse_address(bound_integer=True)
            self.expect(TokenType.SINGULAR_LOWER)
            d = self.parse_address()
            return Instruction(opcode, addr_a=a, addr_b=b, addr_dest=d)

    def parse_address(self, bound_integer=False):
        t = self.peek()
        if t == TokenType.SINGULAR_APOS:
            self.consume()
            t2 = self.peek()
            if t2 == TokenType.PLURAL_LOWER:
                self.consume()
                addr = Address(AddressType.U)
            elif t2 == TokenType.SINGULAR_LOWER:
                self.consume()
                addr = Address(AddressType.C)
            else:
                raise SyntaxError_(f"expected {token(TokenType.PLURAL_LOWER)} or {token(TokenType.SINGULAR_LOWER)} after {token(TokenType.SINGULAR_APOS)}, got {token_or(t2)}")
        elif t == TokenType.PLURAL_CAP:
            self.consume()
            t2 = self.peek()
            if t2 == TokenType.PLURAL_APOS:
                self.consume()
                inner = self.parse_address(bound_integer)
                addr = Address(AddressType.WRAP, sub_addr=inner)
            elif t2 == TokenType.SINGULAR_LOWER:
                self.consume()
                self.expect(TokenType.PLURAL_APOS)
                n = self._parse_integer(bound_integer)
                addr = Address(AddressType.DERIVED, index=n)
            elif t2 == TokenType.PLURAL_LOWER:
                self.consume()
                self.expect(TokenType.PLURAL_APOS)
                n = self._parse_integer(bound_integer)
                addr = Address(AddressType.UD, index=n)
            else:
                raise SyntaxError_(f"expected {token(TokenType.SINGULAR_LOWER)}, {token(TokenType.PLURAL_LOWER)}, or {token(TokenType.PLURAL_APOS)} after {token(TokenType.PLURAL_CAP)}, got {token_or(t2)}")
        elif t == TokenType.PLURAL_LOWER:
            count = 0
            while self.peek() == TokenType.PLURAL_LOWER:
                self.consume()
                count += 1
            if self.peek() == TokenType.SINGULAR_LOWER_APOS_APOS:
                self.consume()
                if count == 1:
                    addr = Address(AddressType.IO_BYTE)
                elif count == 2:
                    addr = Address(AddressType.IO_S5B)
                else:
                    raise SyntaxError_(
                        f"expected 1 or 2 of {token(TokenType.PLURAL_LOWER)} before "
                        f"{token(TokenType.SINGULAR_LOWER_APOS_APOS)}, got {count}"
                    )
            else:
                raise SyntaxError_(
                    f"expected {token(TokenType.SINGULAR_LOWER_APOS_APOS)} after "
                    f"{token(TokenType.PLURAL_LOWER)}, got {token_or(self.peek())}"
                )
        elif t == TokenType.SINGULAR_LOWER_APOS_APOS:
            self.consume()
            addr = Address(AddressType.IO)
        else:
            raise SyntaxError_(f"expected address, got {token_or(t)}")

        if self.peek() == TokenType.PLURAL_APOS:
            self.consume()
            inc = self._parse_integer(stop_at_separator=bound_integer)
            if inc < 0:
                inc = 0
            addr.dispatch_depth = 1 + inc
            addr.has_depth = True
        return addr

    def _is_followed_by_address(self):
        return self.peek(1) in (
            TokenType.SINGULAR_APOS,
            TokenType.PLURAL_CAP,
            TokenType.SINGULAR_LOWER_APOS_APOS,
        )

    def _parse_integer(self, stop_at_separator=False):
        value = 0
        while self.peek() in (TokenType.SINGULAR_LOWER, TokenType.PLURAL_LOWER):
            t = self.peek()
            if t == TokenType.SINGULAR_LOWER and stop_at_separator:
                if self._is_followed_by_address():
                    return value
            self.consume()
            if t == TokenType.SINGULAR_LOWER:
                value = value + 1
            else:
                value = value * 2
        return value


class S5Set:
    __slots__ = ("_items",)

    def __init__(self, items=()):
        for item in items:
            if not isinstance(item, S5Set):
                raise RuntimeError_("S5Set elements must be S5Set")
        self._items = tuple(items)

    @classmethod
    def _from_items(cls, items):
        obj = object.__new__(cls)
        obj._items = tuple(items)
        return obj

    def __getitem__(self, index):
        return self._items[index]

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)

    def __hash__(self):
        return hash(self._items)

    def __eq__(self, other):
        if not isinstance(other, S5Set):
            return NotImplemented
        return self._items == other._items

    def __repr__(self):
        if not self._items:
            return "{}"
        inner = ", ".join(repr(e) for e in self._items)
        return "{" + inner + "}"

    def union(self, other):
        return S5Set._from_items(list(self._items) + list(other._items))

    def intersection(self, other):
        other_set = set(other._items)
        result = [item for item in self._items if item in other_set]
        return S5Set._from_items(result)

    def difference(self, other):
        other_set = set(other._items)
        result = [item for item in self._items if item not in other_set]
        return S5Set._from_items(result)


def set_value(s):
    """Numerical value of an ordered set under mixed-unary encoding.

    Start from 0; for each element left-to-right:
      ∅ (empty set) → +1
      nonempty       → ×2
    """
    value = 0
    for elem in s:
        if len(elem) == 0:
            value += 1
        else:
            value *= 2
    return value


def int_to_s5set(n):
    """Inverse of set_value: construct an S5Set from an integer."""
    if n == 0:
        return S5Set()
    elements = []
    while n > 0:
        if n % 2 == 0:
            elements.append(S5Set([S5Set()]))
            n //= 2
        else:
            elements.append(S5Set())
            n -= 1
    elements.reverse()
    return S5Set(elements)


class LineSet(S5Set):
    __slots__ = ("_instruction",)

    def __init__(self, instruction):
        super().__init__()
        self._instruction = instruction


class SubroutineSet(S5Set):
    __slots__ = ("_body", "_io_s5b")

    def __init__(self, body, items, io_s5b=False):
        super().__init__(items)
        self._body = body
        self._io_s5b = io_s5b


class Executor:
    def __init__(self, buf_sizes=None):
        self.U = S5Set([S5Set()])
        self.C = None
        self.halted = False
        self._io = IOHandler(buf_sizes=buf_sizes)



    def _resolve_base(self, addr):
        if addr.type == AddressType.U:
            return self.U
        elif addr.type == AddressType.C:
            if self.C is None:
                raise RuntimeError_("C is undefined")
            return self.C
        elif addr.type == AddressType.DERIVED:
            if self.C is None:
                raise RuntimeError_("C is undefined")
            if addr.index >= len(self.C):
                raise RuntimeError_(
                    f"C[{addr.index}] out of bounds (len={len(self.C)})"
                )
            return self.C[addr.index]
        elif addr.type == AddressType.UD:
            if addr.index >= len(self.U):
                raise RuntimeError_(
                    f"U[{addr.index}] out of bounds (len={len(self.U)})"
                )
            return self.U[addr.index]
        elif addr.type == AddressType.WRAP:
            inner = self.resolve(addr.sub_addr)
            return S5Set([inner])
        elif addr.type == AddressType.IO_BYTE:
            if addr.has_depth:
                return self._io.resolve(AddressType.IO_BYTE, addr.dispatch_depth - 1)
            byte = sys.stdin.buffer.read(1)
            if not byte:
                raise RuntimeError_("input: unexpected EOF")
            return int_to_s5set(byte[0])
        elif addr.type == AddressType.IO_S5B:
            if addr.has_depth:
                return self._io.resolve(AddressType.IO_S5B, addr.dispatch_depth - 1)
            raw = sys.stdin.buffer.read()
            if not raw:
                raise RuntimeError_("input: unexpected EOF")
            return _read_s5b(raw)
        elif addr.type == AddressType.IO:
            if addr.has_depth:
                return self._io.resolve(AddressType.IO, addr.dispatch_depth - 1)
            line = sys.stdin.readline()
            if not line:
                raise RuntimeError_("input: unexpected EOF")
            try:
                n = int(line.strip())
            except ValueError:
                raise RuntimeError_(f"input: expected integer, got {line.strip()!r}")
            return int_to_s5set(n)

    def resolve(self, addr):
        value = self._resolve_base(addr)
        if addr.type in (AddressType.IO, AddressType.IO_BYTE, AddressType.IO_S5B):
            return value
        for _ in range(addr.dispatch_depth - 1):
            idx = set_value(value)
            if idx >= len(self.U):
                raise RuntimeError_(
                    f"dispatch through U[{idx}] out of bounds (len={len(self.U)})"
                )
            value = self.U[idx]
        return value

    def _assign_base(self, addr, value):
        if addr.type == AddressType.WRAP:
            raise RuntimeError_("cannot assign to a wrap address")
        if addr.type == AddressType.IO_BYTE:
            if addr.has_depth:
                self._io.assign(AddressType.IO_BYTE, addr.dispatch_depth - 1, value)
                return
            n = set_value(value)
            while True:
                sys.stdout.buffer.write(bytes([n & 0xFF]))
                n >>= 8
                if n == 0:
                    break
            sys.stdout.buffer.flush()
        elif addr.type == AddressType.IO_S5B:
            if addr.has_depth:
                self._io.assign(AddressType.IO_S5B, addr.dispatch_depth - 1, value)
                return
            data = _write_s5b(value)
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
        elif addr.type == AddressType.IO:
            if addr.has_depth:
                self._io.assign(AddressType.IO, addr.dispatch_depth - 1, value)
                return
            n = set_value(value)
            print(n)
        elif addr.type == AddressType.U:
            self.U = value
        elif addr.type == AddressType.C:
            self.C = value
        elif addr.type == AddressType.DERIVED:
            if self.C is None:
                raise RuntimeError_("C is undefined")
            if addr.index >= len(self.C):
                raise RuntimeError_(
                    f"C[{addr.index}] out of bounds (len={len(self.C)})"
                )
            items = list(self.C._items)
            items[addr.index] = value
            self.C = S5Set._from_items(items)
        elif addr.type == AddressType.UD:
            if addr.index >= len(self.U):
                raise RuntimeError_(
                    f"U[{addr.index}] out of bounds (len={len(self.U)})"
                )
            items = list(self.U._items)
            items[addr.index] = value
            self.U = S5Set._from_items(items)

    def assign(self, addr, value):
        if addr.type in (AddressType.IO, AddressType.IO_BYTE, AddressType.IO_S5B):
            self._assign_base(addr, value)
            return
        if addr.dispatch_depth > 1:
            v = self._resolve_base(addr)
            for _ in range(addr.dispatch_depth - 2):
                idx = set_value(v)
                if idx >= len(self.U):
                    raise RuntimeError_(
                        f"dispatch through U[{idx}] out of bounds (len={len(self.U)})"
                    )
                v = self.U[idx]
            final_idx = set_value(v)
            if final_idx >= len(self.U):
                raise RuntimeError_(
                    f"assign via dispatch: U[{final_idx}] out of bounds (len={len(self.U)})"
                )
            items = list(self.U._items)
            items[final_idx] = value
            self.U = S5Set._from_items(items)
        else:
            self._assign_base(addr, value)

    def _check_halt(self):
        if len(self.U) == 0:
            self.halted = True

    def exec_instruction(self, instr):
        if instr.opcode == Opcode.SUBSET_SELECT:
            if self.C is None:
                raise RuntimeError_("cannot subset-select: C is undefined")
            if instr.addr_b is not None:
                idx_val = self.resolve(instr.addr_b)
                idx = set_value(idx_val)
            else:
                idx = instr.n
            if idx >= len(self.C):
                raise RuntimeError_(f"C[{idx}] out of bounds (len={len(self.C)})")
            self.C = self.C[idx]
            self._check_halt()
        elif instr.opcode == Opcode.SUBR and instr.subr_body is not None:
            lines = tuple(LineSet(inst) for inst in instr.subr_body)
            subroutine = SubroutineSet(instr.subr_body, lines)
            if instr.addr_a is None:
                self.C = subroutine
            else:
                self.assign(instr.addr_a, subroutine)
            self._check_halt()
        elif instr.opcode == Opcode.SUBR:
            if instr.addr_b is not None:
                cond_val = self.resolve(instr.addr_b)
                if len(cond_val) == 0:
                    return
            if instr.addr_a is None:
                if self.C is None:
                    raise RuntimeError_("C is undefined")
                subr = self.C
            else:
                subr = self.resolve(instr.addr_a)
            if not isinstance(subr, SubroutineSet):
                raise RuntimeError_("not a subroutine")
            self.run(subr._body)
        else:
            a = self.resolve(instr.addr_a)
            b = self.resolve(instr.addr_b)
            for val in (a, b):
                if isinstance(val, SubroutineSet) and val._io_s5b:
                    self.run(val._body)
            if instr.opcode == Opcode.UNION:
                result = a.union(b)
            elif instr.opcode == Opcode.INTERSECTION:
                result = a.intersection(b)
            elif instr.opcode == Opcode.DIFFERENCE:
                result = a.difference(b)
            self.assign(instr.addr_dest, result)
            self._check_halt()

    def run(self, instructions):
        for instr in instructions:
            self.exec_instruction(instr)
            if self.halted:
                return "halted"
        return "finished"


def _read_s5b(data):
    tokens = list(decode_tokens(data))
    instructions = Parser(tokens).parse_program()
    return SubroutineSet(instructions, [LineSet(i) for i in instructions], io_s5b=True)


def _write_s5b(value):
    if isinstance(value, SubroutineSet):
        from s5.serialize import serialize_body
        tokens = serialize_body(value._body)
    else:
        n = set_value(value)
        codes = []
        while n:
            codes.append(n & 7)
            n >>= 3
        tokens = [CODE_TO_TOKEN[c] for c in reversed(codes)]
    return bytes(encode_tokens(tokens))


from s5.io_handler import IOHandler

from s5.binary import encode_tokens, decode_tokens, sniff, CODE_TO_TOKEN

from s5.cli import main
