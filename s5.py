import sys


class TokenType:
    SET = 'SET'
    SET_LOWER = 'SET_LOWER'
    SETS_LOWER = 'SETS_LOWER'
    SET_APOS = 'SET_APOS'
    SETS_APOS = 'SETS_APOS'
    SETS_CAP = 'SETS_CAP'


class Opcode:
    SUBSET_SELECT = 'SUBSET_SELECT'
    UNION = 'UNION'
    INTERSECTION = 'INTERSECTION'
    DIFFERENCE = 'DIFFERENCE'


class AddressType:
    U = 'U'
    C = 'C'
    DERIVED = 'DERIVED'
    WRAP = 'WRAP'


class Address:
    __slots__ = ('type', 'index', 'sub_addr')
    def __init__(self, addr_type, index=None, sub_addr=None):
        self.type = addr_type
        self.index = index
        self.sub_addr = sub_addr


class Instruction:
    __slots__ = ('opcode', 'n', 'addr_a', 'addr_b', 'addr_dest')
    def __init__(self, opcode, n=None, addr_a=None, addr_b=None, addr_dest=None):
        self.opcode = opcode
        self.n = n
        self.addr_a = addr_a
        self.addr_b = addr_b
        self.addr_dest = addr_dest


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
            tokens.append(TokenType.SET)
        elif word == 'set':
            tokens.append(TokenType.SET_LOWER)
        elif word == 'sets':
            tokens.append(TokenType.SETS_LOWER)
        elif word == "Set's":
            tokens.append(TokenType.SET_APOS)
        elif word == "sets'":
            tokens.append(TokenType.SETS_APOS)
        elif word == 'Sets':
            tokens.append(TokenType.SETS_CAP)
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
            raise SyntaxError_(f"expected {tt}, got {t}")
        return t

    def parse_program(self):
        instructions = []
        while self.pos < len(self.tokens):
            instructions.append(self.parse_instruction())
        return instructions

    def parse_instruction(self):
        self.expect(TokenType.SET)
        opcode = self.parse_opcode()
        return self.parse_operands(opcode)

    def parse_opcode(self):
        t = self.peek()
        if t == TokenType.SETS_CAP:
            self.consume()
            self.expect(TokenType.SET_LOWER)
            return Opcode.SUBSET_SELECT
        elif t == TokenType.SETS_LOWER:
            self.consume()
            return Opcode.UNION
        elif t == TokenType.SET_APOS:
            self.consume()
            return Opcode.INTERSECTION
        elif t == TokenType.SET_LOWER:
            self.consume()
            return Opcode.DIFFERENCE
        elif t is None:
            raise SyntaxError_("expected opcode, got end of input")
        else:
            raise SyntaxError_(f"expected opcode, got {t}")

    def parse_operands(self, opcode):
        if opcode == Opcode.SUBSET_SELECT:
            self.expect(TokenType.SETS_APOS)
            n = self._parse_integer()
            return Instruction(opcode, n=n)
        else:
            a = self.parse_address()
            b = self.parse_address(bound_integer=True)
            self.expect(TokenType.SET_LOWER)
            d = self.parse_address()
            return Instruction(opcode, addr_a=a, addr_b=b, addr_dest=d)

    def parse_address(self, bound_integer=False):
        t = self.peek()
        if t == TokenType.SET_APOS:
            self.consume()
            t2 = self.peek()
            if t2 == TokenType.SETS_LOWER:
                self.consume()
                return Address(AddressType.U)
            elif t2 == TokenType.SET_LOWER:
                self.consume()
                return Address(AddressType.C)
            else:
                raise SyntaxError_(f"expected 'sets' or 'set' after 'Set's', got {t2}")
        elif t == TokenType.SETS_CAP:
            self.consume()
            t2 = self.peek()
            if t2 == TokenType.SETS_APOS:
                self.consume()
                inner = self.parse_address(bound_integer)
                return Address(AddressType.WRAP, sub_addr=inner)
            elif t2 == TokenType.SET_LOWER:
                self.consume()
                self.expect(TokenType.SETS_APOS)
                n = self._parse_integer(bound_integer)
                return Address(AddressType.DERIVED, index=n)
            else:
                raise SyntaxError_(f"expected 'set' or 'sets'' after 'Sets', got {t2}")
        else:
            raise SyntaxError_(f"expected address, got {t}")

    def _is_followed_by_address(self):
        save = self.pos
        self.pos += 1
        n = self.peek()
        self.pos = save
        return n in (TokenType.SET_APOS, TokenType.SETS_CAP)

    def _parse_integer(self, stop_at_separator=False):
        value = 0
        while self.peek() in (TokenType.SET_LOWER, TokenType.SETS_LOWER):
            t = self.peek()
            if t == TokenType.SET_LOWER and stop_at_separator:
                if self._is_followed_by_address():
                    return value
            self.consume()
            if t == TokenType.SET_LOWER:
                value = value * 2 + 1
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

    def assign(self, addr, value):
        if addr.type == AddressType.WRAP:
            raise RuntimeError_("cannot assign to a wrap address")
        if addr.type == AddressType.U:
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


def main():
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


if __name__ == '__main__':
    main()
