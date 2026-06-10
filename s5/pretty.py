from s5 import TokenType, Opcode, TOKEN_DISPLAY
from s5.serialize import serialize_instruction, serialize_address


def pretty_print(instructions, indent=2):
    lines = []
    for instr in instructions:
        if instr.opcode == Opcode.SUBR and instr.subr_body is not None:
            tokens = [TokenType.PLURAL_CAP_APOS, TokenType.PLURAL_CAP_APOS]
            if instr.addr_a is not None:
                tokens.extend(serialize_address(instr.addr_a))
            lines.append(" ".join(TOKEN_DISPLAY[t] for t in tokens))
            for sub in instr.subr_body:
                sub_tokens = serialize_instruction(sub)
                lines.append(" " * indent + " ".join(TOKEN_DISPLAY[t] for t in sub_tokens))
            lines.append(TOKEN_DISPLAY[TokenType.PLURAL_CAP_APOS])
        else:
            tokens = serialize_instruction(instr)
            lines.append(" ".join(TOKEN_DISPLAY[t] for t in tokens))
    return "\n".join(lines) + "\n"
