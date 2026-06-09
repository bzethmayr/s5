from s5 import TokenType, TokenizerError

TOKEN_TO_CODE = {
    TokenType.SINGULAR: 0,
    TokenType.SINGULAR_LOWER: 1,
    TokenType.PLURAL_LOWER: 2,
    TokenType.SINGULAR_APOS: 3,
    TokenType.PLURAL_APOS: 4,
    TokenType.PLURAL_CAP: 5,
    TokenType.PLURAL_CAP_APOS: 6,
    TokenType.SINGULAR_LOWER_APOS_APOS: 7,
}

CODE_TO_TOKEN = {v: k for k, v in TOKEN_TO_CODE.items()}


def _even_parity(value):
    v = value & 0x7
    return (v ^ (v >> 1) ^ (v >> 2)) & 1


def pack_pair(t1, t2_or_none):
    code1 = TOKEN_TO_CODE[t1]
    byte = code1
    byte |= _even_parity(code1) << 3
    if t2_or_none is not None:
        code2 = TOKEN_TO_CODE[t2_or_none]
        byte |= code2 << 4
        byte |= _even_parity(code2) << 7
    else:
        byte |= 0 << 4
        byte |= 1 << 7
    return byte


def unpack_pair(byte):
    code1 = byte & 0x7
    parity1 = (byte >> 3) & 1
    if _even_parity(code1) != parity1:
        raise TokenizerError("parity mismatch in first token")
    code2 = (byte >> 4) & 0x7
    parity2 = (byte >> 7) & 1
    if code2 == 0 and parity2 == 1:
        return CODE_TO_TOKEN[code1], None
    if _even_parity(code2) != parity2:
        raise TokenizerError("parity mismatch in second token")
    return CODE_TO_TOKEN[code1], CODE_TO_TOKEN[code2]


def encode_tokens(tokens):
    buf = list(tokens)
    out = bytearray()
    for i in range(0, len(buf), 2):
        t1 = buf[i]
        t2 = buf[i + 1] if i + 1 < len(buf) else None
        out.append(pack_pair(t1, t2))
    return bytes(out)


def decode_tokens(data):
    for byte in data:
        t1, t2 = unpack_pair(byte)
        yield t1
        if t2 is None:
            break
        yield t2


def sniff(first_byte):
    return first_byte not in (0x53, 0x73)
