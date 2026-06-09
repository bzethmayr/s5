from s5 import (
    TokenType,
    AddressType,
    Opcode,
    Address,
)


def serialize_integer(n):
    tokens = []
    while n > 0:
        if n % 2 == 1:
            tokens.insert(0, TokenType.SINGULAR_LOWER)
            n -= 1
        else:
            tokens.insert(0, TokenType.PLURAL_LOWER)
            n //= 2
    return tokens


def serialize_address(addr):
    if addr.type == AddressType.U:
        tokens = [TokenType.SINGULAR_APOS, TokenType.PLURAL_LOWER]
    elif addr.type == AddressType.C:
        tokens = [TokenType.SINGULAR_APOS, TokenType.SINGULAR_LOWER]
    elif addr.type == AddressType.DERIVED:
        tokens = [TokenType.PLURAL_CAP, TokenType.SINGULAR_LOWER, TokenType.PLURAL_APOS]
        tokens.extend(serialize_integer(addr.index))
    elif addr.type == AddressType.UD:
        tokens = [TokenType.PLURAL_CAP, TokenType.PLURAL_LOWER, TokenType.PLURAL_APOS]
        tokens.extend(serialize_integer(addr.index))
    elif addr.type == AddressType.WRAP:
        tokens = [TokenType.PLURAL_CAP, TokenType.PLURAL_APOS]
        tokens.extend(serialize_address(addr.sub_addr))
    elif addr.type == AddressType.IO:
        tokens = [TokenType.SINGULAR_LOWER_APOS_APOS]
    elif addr.type == AddressType.IO_BYTE:
        tokens = [TokenType.PLURAL_LOWER, TokenType.SINGULAR_LOWER_APOS_APOS]
    elif addr.type == AddressType.IO_S5B:
        tokens = [TokenType.PLURAL_LOWER, TokenType.PLURAL_LOWER, TokenType.SINGULAR_LOWER_APOS_APOS]
    if addr.has_depth:
        tokens.append(TokenType.PLURAL_APOS)
        tokens.extend(serialize_integer(addr.dispatch_depth - 1))
    return tokens


def serialize_instruction(instr):
    if instr.opcode == Opcode.SUBSET_SELECT:
        tokens = [TokenType.SINGULAR, TokenType.PLURAL_CAP, TokenType.SINGULAR_LOWER, TokenType.PLURAL_APOS]
        tokens.extend(serialize_integer(instr.n))
    elif instr.opcode == Opcode.UNION:
        tokens = [TokenType.SINGULAR, TokenType.PLURAL_LOWER]
        tokens.extend(serialize_address(instr.addr_a))
        tokens.extend(serialize_address(instr.addr_b))
        tokens.append(TokenType.SINGULAR_LOWER)
        tokens.extend(serialize_address(instr.addr_dest))
    elif instr.opcode == Opcode.INTERSECTION:
        tokens = [TokenType.SINGULAR, TokenType.SINGULAR_APOS]
        tokens.extend(serialize_address(instr.addr_a))
        tokens.extend(serialize_address(instr.addr_b))
        tokens.append(TokenType.SINGULAR_LOWER)
        tokens.extend(serialize_address(instr.addr_dest))
    elif instr.opcode == Opcode.DIFFERENCE:
        tokens = [TokenType.SINGULAR, TokenType.SINGULAR_LOWER]
        tokens.extend(serialize_address(instr.addr_a))
        tokens.extend(serialize_address(instr.addr_b))
        tokens.append(TokenType.SINGULAR_LOWER)
        tokens.extend(serialize_address(instr.addr_dest))
    elif instr.opcode == Opcode.SUBR:
        if instr.subr_body is not None:
            tokens = [TokenType.PLURAL_CAP_APOS, TokenType.PLURAL_CAP_APOS]
            if instr.addr_a is not None:
                tokens.extend(serialize_address(instr.addr_a))
            for sub_instr in instr.subr_body:
                tokens.extend(serialize_instruction(sub_instr))
            tokens.append(TokenType.PLURAL_CAP_APOS)
        else:
            tokens = [TokenType.SINGULAR, TokenType.PLURAL_CAP_APOS]
            if instr.addr_b is not None:
                tokens.append(TokenType.SINGULAR_LOWER)
                tokens.extend(serialize_address(instr.addr_b))
                if instr.addr_a is not None:
                    tokens.extend(serialize_address(instr.addr_a))
            elif instr.addr_a is not None:
                tokens.extend(serialize_address(instr.addr_a))
    return tokens


def serialize_body(instructions):
    tokens = []
    for instr in instructions:
        tokens.extend(serialize_instruction(instr))
    return tokens
