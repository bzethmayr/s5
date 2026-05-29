import sys


class TokenType:
    SINGULAR = 'SINGULAR'
    SINGULAR_LOWER = 'SINGULAR_LOWER'
    PLURAL_LOWER = 'PLURAL_LOWER'
    SINGULAR_APOS = 'SINGULAR_APOS'
    PLURAL_APOS = 'PLURAL_APOS'
    PLURAL_CAP = 'PLURAL_CAP'
    PLURAL_CAP_APOS = 'PLURAL_CAP_APOS'
    SINGULAR_LOWER_APOS_APOS = 'SINGULAR_LOWER_APOS_APOS'


TOKEN_DISPLAY = {
    TokenType.SINGULAR: "Set",
    TokenType.SINGULAR_LOWER: "set",
    TokenType.PLURAL_LOWER: "sets",
    TokenType.SINGULAR_APOS: "Set's",
    TokenType.PLURAL_APOS: "sets'",
    TokenType.PLURAL_CAP: "Sets",
    TokenType.PLURAL_CAP_APOS: "Sets'",
    TokenType.SINGULAR_LOWER_APOS_APOS: "set's'",
}


class Opcode:
    SUBSET_SELECT = 'SUBSET_SELECT'
    UNION = 'UNION'
    INTERSECTION = 'INTERSECTION'
    DIFFERENCE = 'DIFFERENCE'
    SUBR = 'SUBR'


class AddressType:
    U = 'U'
    C = 'C'
    DERIVED = 'DERIVED'
    WRAP = 'WRAP'
    IO = 'IO'


class Address:
    __slots__ = ('type', 'index', 'sub_addr')
    def __init__(self, addr_type, index=None, sub_addr=None):
        self.type = addr_type
        self.index = index
        self.sub_addr = sub_addr


class Instruction:
    __slots__ = ('opcode', 'n', 'addr_a', 'addr_b', 'addr_dest', 'subr_body')
    def __init__(self, opcode, n=None, addr_a=None, addr_b=None, addr_dest=None, subr_body=None):
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
        if word == 'Set':
            tokens.append(TokenType.SINGULAR)
        elif word == 'set':
            tokens.append(TokenType.SINGULAR_LOWER)
        elif word == 'sets':
            tokens.append(TokenType.PLURAL_LOWER)
        elif word == "Set's":
            tokens.append(TokenType.SINGULAR_APOS)
        elif word == "sets'":
            tokens.append(TokenType.PLURAL_APOS)
        elif word == 'Sets':
            tokens.append(TokenType.PLURAL_CAP)
        elif word == "Sets'":
            tokens.append(TokenType.PLURAL_CAP_APOS)
        elif word == "set's'":
            tokens.append(TokenType.SINGULAR_LOWER_APOS_APOS)
        else:
            raise TokenizerError(f"unknown token: {word!r}")
    return tokens


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def consume(self):
        if self.pos >= len(self.tokens):
            raise SyntaxError_("unexpected end of input")
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def expect(self, tt):
        t = self.consume()
        if t != tt:
            d_tt = TOKEN_DISPLAY.get(tt, tt)
            d_t = TOKEN_DISPLAY.get(t, t)
            raise SyntaxError_(f"expected {d_tt}, got {d_t}")
        return t

    def parse_program(self):
        instructions = []
        while self.pos < len(self.tokens):
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
                        raise SyntaxError_("expected Sets' to end subroutine")
                    self.consume()
                    instructions.append(Instruction(Opcode.SUBR, subr_body=body, addr_a=loc))
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
            raise SyntaxError_(f"expected opcode, got {TOKEN_DISPLAY.get(t, t)}")

    def parse_operands(self, opcode):
        if opcode == Opcode.SUBSET_SELECT:
            self.expect(TokenType.PLURAL_APOS)
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
                return Address(AddressType.U)
            elif t2 == TokenType.SINGULAR_LOWER:
                self.consume()
                return Address(AddressType.C)
            else:
                raise SyntaxError_(f"expected 'sets' or 'set' after 'Set's', got {t2}")
        elif t == TokenType.PLURAL_CAP:
            self.consume()
            t2 = self.peek()
            if t2 == TokenType.PLURAL_APOS:
                self.consume()
                inner = self.parse_address(bound_integer)
                return Address(AddressType.WRAP, sub_addr=inner)
            elif t2 == TokenType.SINGULAR_LOWER:
                self.consume()
                self.expect(TokenType.PLURAL_APOS)
                n = self._parse_integer(bound_integer)
                return Address(AddressType.DERIVED, index=n)
            else:
                raise SyntaxError_(f"expected 'set' or 'sets'' after 'Sets', got {t2}")
        elif t == TokenType.SINGULAR_LOWER_APOS_APOS:
            self.consume()
            return Address(AddressType.IO)
        else:
            raise SyntaxError_(f"expected address, got {TOKEN_DISPLAY.get(t, t)}")

    def _is_followed_by_address(self):
        save = self.pos
        self.pos += 1
        n = self.peek()
        self.pos = save
        return n in (TokenType.SINGULAR_APOS, TokenType.PLURAL_CAP)

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
    __slots__ = ('_items',)

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
    __slots__ = ('_instruction',)
    def __init__(self, instruction):
        super().__init__()
        self._instruction = instruction


class SubroutineSet(S5Set):
    __slots__ = ('_body',)
    def __init__(self, body, items):
        super().__init__(items)
        self._body = body


class Executor:
    def __init__(self):
        self.U = S5Set([S5Set()])
        self.C = None
        self.halted = False

    def resolve(self, addr):
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
                    f"C[{addr.index}] out of bounds (len={len(self.C)})")
            return self.C[addr.index]
        elif addr.type == AddressType.WRAP:
            inner = self.resolve(addr.sub_addr)
            return S5Set([inner])
        elif addr.type == AddressType.IO:
            line = sys.stdin.readline()
            if not line:
                raise RuntimeError_("input: unexpected EOF")
            try:
                n = int(line.strip())
            except ValueError:
                raise RuntimeError_(
                    f"input: expected integer, got {line.strip()!r}")
            return int_to_s5set(n)

    def assign(self, addr, value):
        if addr.type == AddressType.WRAP:
            raise RuntimeError_("cannot assign to a wrap address")
        if addr.type == AddressType.IO:
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
                    f"C[{addr.index}] out of bounds (len={len(self.C)})")
            items = list(self.C._items)
            items[addr.index] = value
            self.C = S5Set._from_items(items)

    def _check_halt(self):
        if len(self.U) == 0:
            self.halted = True

    def exec_instruction(self, instr):
        if instr.opcode == Opcode.SUBSET_SELECT:
            if self.C is None:
                raise RuntimeError_(
                    "cannot subset-select: C is undefined")
            if instr.n >= len(self.C):
                raise RuntimeError_(
                    f"C[{instr.n}] out of bounds (len={len(self.C)})")
            self.C = self.C[instr.n]
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


def detect_mode():
    if len(sys.argv) > 1:
        return "file"
    return "repl" if sys.stdin.isatty() else "piped"


def main():
    mode = detect_mode()
    if mode == "repl":
        sys.stderr = sys.stdout

    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding='utf-8-sig') as f:
            source = f.read()
    else:
        source = sys.stdin.read()

    try:
        tokens = tokenize(source)
    except TokenizerError as e:
        print(f"tokenizer error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        parser = Parser(tokens)
        instructions = parser.parse_program()
    except SyntaxError_ as e:
        print(f"syntax error: {e}", file=sys.stderr)
        sys.exit(1)

    executor = Executor()
    try:
        status = executor.run(instructions)
        print(status)
    except RuntimeError_ as e:
        print(f"runtime error: {e}", file=sys.stderr)
        sys.exit(1)
