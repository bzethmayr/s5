"""Trace the execution of hello_world.s5 step by step."""

import sys
import io
import os
sys.path.insert(0, r'C:\Users\Owner\Documents\coderoot\s5')

from s5.__init__ import (
    tokenize, Parser, Executor, Opcode, AddressType,
    set_value, TOKEN_DISPLAY, TokenType
)


def addr_repr(addr):
    if addr is None:
        return "None"
    depth = addr.dispatch_depth if addr.dispatch_depth != 1 else ""
    depth_s = f"^{depth}" if depth else ""
    if addr.type == AddressType.U:
        return f"U{depth_s}"
    if addr.type == AddressType.C:
        return f"C{depth_s}"
    if addr.type == AddressType.DERIVED:
        return f"C[{addr.index}]{depth_s}"
    if addr.type == AddressType.UD:
        return f"U[{addr.index}]{depth_s}"
    if addr.type == AddressType.WRAP:
        return f"WRAP({addr_repr(addr.sub_addr)})"
    if addr.type == AddressType.IO_BYTE:
        return "IO_BYTE"
    if addr.type == AddressType.IO:
        return "IO"
    return "???"


OPCODE_NAMES = {
    Opcode.UNION: "UNION",
    Opcode.INTERSECTION: "INTERSECTION",
    Opcode.DIFFERENCE: "DIFFERENCE",
    Opcode.SUBSET_SELECT: "SUBSET_SELECT",
    Opcode.SUBR: "SUBR",
}


def instr_repr(instr):
    nfo = OPCODE_NAMES.get(instr.opcode, str(instr.opcode))
    if instr.opcode == Opcode.SUBSET_SELECT:
        return f"SUBSET_SELECT n={instr.n}"
    if instr.opcode == Opcode.SUBR:
        if instr.subr_body is not None:
            return f"SUBR(body_len={len(instr.subr_body)})"
        else:
            return f"SUBR(addr_a={addr_repr(instr.addr_a)})"
    return f"{nfo}({addr_repr(instr.addr_a)}, {addr_repr(instr.addr_b)}) -> {addr_repr(instr.addr_dest)}"


def token_repr(tok):
    return TOKEN_DISPLAY.get(tok, str(tok))


def main():
    with open(r'C:\Users\Owner\Documents\coderoot\s5\hello_world.s5', encoding='utf-8-sig') as f:
        source = f.read()

    lines = source.strip().split('\n')
    tokens = tokenize(source)
    parser = Parser(tokens)
    instructions = parser.parse_program()

    print("=" * 120)
    print("S5 HELLO WORLD TRACE")
    print("=" * 120)

    # Print each instruction with parsed form
    print("\n--- PARSED INSTRUCTIONS ---\n")
    for i, instr in enumerate(instructions):
        line_no = i + 1
        src = lines[i].strip()
        parsed = instr_repr(instr)
        print(f"  [{line_no:3d}] {src}")
        print(f"         => {parsed}")
        toks = tokenize(src)
        tok_str = ' '.join(token_repr(t) for t in toks)
        print(f"         => tokens: {tok_str}")
        print()

    # Execute with trace - redirect executor's byte output to /dev/null
    print("=" * 120)
    print("EXECUTION TRACE")
    print("=" * 120)

    executor = Executor()
    # We let executor byte output print to stdout (it interleaves with trace but that's OK)
    print(f"\n  Initial: U = {executor.U}  (set_value = {set_value(executor.U)}), C = {executor.C}")

    char_instr_counts = {}  # char_idx -> count

    for i, instr in enumerate(instructions):
        line_no = i + 1
        src = lines[i].strip()
        u_before = set_value(executor.U)
        c_before = set_value(executor.C) if executor.C is not None else None

        is_output = (instr.opcode == Opcode.INTERSECTION
                     and instr.addr_dest is not None
                     and instr.addr_dest.type == AddressType.IO_BYTE)

        is_reset = (instr.opcode == Opcode.INTERSECTION
                    and instr.addr_dest is not None
                    and instr.addr_dest.type == AddressType.U
                    and instr.addr_a is not None and instr.addr_a.type == AddressType.C
                    and instr.addr_b is not None and instr.addr_b.type == AddressType.C)

        is_init_c = (i == 0)

        try:
            executor.exec_instruction(instr)
        except Exception as e:
            print(f"  *** ERROR at line {line_no}: {e}")
            break

        u_after = set_value(executor.U)
        c_after = set_value(executor.C) if executor.C is not None else None

        markers = []
        if is_init_c:
            markers.append("INIT C")
        if is_reset:
            markers.append("RESET")
        if is_output:
            out_char = chr(u_after) if 32 <= u_after < 127 else f"\\x{u_after:02x}"
            markers.append(f"OUTPUT '{out_char}' ({u_after})")

        marker_str = "  *** " + ", ".join(markers) if markers else ""
        print(f"  [{line_no:3d}] U: {u_before:4d} -> {u_after:4d} | C: {c_before} -> {c_after} {marker_str}")

    print("\n" + "=" * 120)
    print("CHARACTER BREAKDOWN")
    print("=" * 120)

    target = "Hello World!"
    print(f"\n  Target string: {target!r}\n")

    char_boundaries = []
    char_start = 1
    for ch_idx in range(len(target)):
        for i, instr in enumerate(instructions):
            line_no = i + 1
            is_output = (instr.opcode == Opcode.INTERSECTION
                         and instr.addr_dest is not None
                         and instr.addr_dest.type == AddressType.IO_BYTE)
            if is_output and line_no >= char_start:
                char_boundaries.append((char_start, line_no))
                char_start = line_no + 1
                break

    for ch_idx, ch in enumerate(target):
        if ch_idx < len(char_boundaries):
            start, end = char_boundaries[ch_idx]
        else:
            print(f"  [{ch_idx}] '{ch}' — no boundary found")
            continue

        char_src_lines = lines[start-1:end]
        char_src = '\n'.join(char_src_lines)
        char_tokens = tokenize(char_src)
        char_parser = Parser(char_tokens)
        char_instrs = char_parser.parse_program()

        ascii_val = ord(ch)
        count = len(char_instrs)

        print(f"  [{ch_idx}] '{ch}' (ASCII {ascii_val}) \u2014 lines {start}-{end} ({count} instrs)")
        print(f"       Instructions:")
        for ci, cinstr in enumerate(char_instrs):
            cinstr_line = start + ci
            if cinstr.opcode == Opcode.UNION:
                if cinstr.addr_b.type == AddressType.WRAP:
                    print(f"         [{cinstr_line:3d}] x2  (UNION(U, WRAP(C), U))")
                elif cinstr.addr_b.type == AddressType.C:
                    print(f"         [{cinstr_line:3d}] +1  (UNION(U, C, U))")
                else:
                    print(f"         [{cinstr_line:3d}] UNION  {instr_repr(cinstr)}")
            elif cinstr.opcode == Opcode.INTERSECTION:
                if cinstr.addr_dest.type == AddressType.IO_BYTE:
                    print(f"         [{cinstr_line:3d}] OUT (INTERSECTION(U, U, IO_BYTE))")
                elif cinstr.addr_dest.type == AddressType.U and cinstr.addr_a.type == AddressType.C:
                    print(f"         [{cinstr_line:3d}] RESET (INTERSECTION(C, C, U))")
                elif cinstr.addr_dest.type == AddressType.C:
                    print(f"         [{cinstr_line:3d}] INIT C (INTERSECTION(U, U, C))")
                else:
                    print(f"         [{cinstr_line:3d}] INTERSECTION  {instr_repr(cinstr)}")
        print()

    print("=" * 120)
    print("SUMMARY")
    print("=" * 120)
    total = 0
    for ch_idx, ch in enumerate(target):
        if ch_idx < len(char_boundaries):
            start, end = char_boundaries[ch_idx]
            count = end - start + 1
            total += count
            print(f"  '{ch}' (ASCII {ord(ch):3d}): lines {start:3d}-{end:3d} = {count:2d} instrs")
        else:
            print(f"  '{ch}': ???")
    print(f"  {'=' * 50}")
    print(f"  TOTAL: {total} instructions (out of {len(instructions)} total)")


if __name__ == '__main__':
    main()
