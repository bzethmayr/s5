from s5 import tokenize, Parser, TokenType
from s5.serialize import serialize_body
from s5.pretty import pretty_print


def _parse(src):
    return Parser(tokenize(src)).parse_program()


def _join(src):
    return " ".join(src.split())


def test_empty():
    assert pretty_print([]) == "\n"


def test_single_union():
    src = "Set sets Set's sets Set's sets set Set's set"
    instrs = _parse(src)
    result = pretty_print(instrs)
    assert result.strip() == src


def test_single_intersection():
    src = "Set Set's Set's sets Set's sets set Set's sets"
    instrs = _parse(src)
    result = pretty_print(instrs)
    assert result.strip() == src


def test_single_difference():
    src = "Set set Set's sets Set's sets set Set's sets"
    instrs = _parse(src)
    result = pretty_print(instrs)
    assert result.strip() == src


def test_single_subset_select():
    src = "Set Sets set sets'"
    instrs = _parse(src)
    result = pretty_print(instrs)
    assert result.strip() == src

def test_single_subset_select_n1():
    src = "Set Sets set sets' set"
    instrs = _parse(src)
    result = pretty_print(instrs)
    assert result.strip() == src


def test_multi_instruction():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Set Sets set sets'\n"
        "Set set Set's sets Set's set set Set's sets"
    )
    instrs = _parse(src)
    result = pretty_print(instrs)
    lines = result.strip().split("\n")
    assert len(lines) == 3
    assert _join(lines[0]) == "Set sets Set's sets Set's sets set Set's set"
    assert _join(lines[1]) == "Set Sets set sets'"
    assert _join(lines[2]) == "Set set Set's sets Set's set set Set's sets"


def test_subroutine_default_c():
    src = (
        "Sets' Sets'\n"
        "  Set sets Set's sets Set's sets set Set's sets\n"
        "Sets'"
    )
    instrs = _parse(src)
    result = pretty_print(instrs)
    lines = result.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "Sets' Sets'"
    assert lines[1] == "  Set sets Set's sets Set's sets set Set's sets"
    assert lines[2] == "Sets'"


def test_subroutine_explicit_c():
    src = (
        "Sets' Sets' Set's set\n"
        "  Set sets Set's sets Set's sets set Set's sets\n"
        "Sets'"
    )
    instrs = _parse(src)
    result = pretty_print(instrs)
    lines = result.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "Sets' Sets' Set's set"
    assert lines[1] == "  Set sets Set's sets Set's sets set Set's sets"
    assert lines[2] == "Sets'"


def test_subroutine_at_cn():
    src = (
        "Sets' Sets' Sets set sets'\n"
        "  Set sets Set's sets Set's sets set Set's sets\n"
        "Sets'"
    )
    instrs = _parse(src)
    result = pretty_print(instrs)
    lines = result.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "Sets' Sets' Sets set sets'"
    assert lines[1] == "  Set sets Set's sets Set's sets set Set's sets"
    assert lines[2] == "Sets'"


def test_subroutine_multi_body():
    src = (
        "Sets' Sets'\n"
        "  Set sets Set's sets Set's sets set Set's sets\n"
        "  Set set Set's sets Set's sets set Set's sets\n"
        "  Set Set's Set's sets Set's sets set Set's sets\n"
        "Sets'"
    )
    instrs = _parse(src)
    result = pretty_print(instrs)
    lines = result.strip().split("\n")
    assert len(lines) == 5
    assert lines[0] == "Sets' Sets'"
    assert lines[3] == "  Set Set's Set's sets Set's sets set Set's sets"
    assert lines[4] == "Sets'"


def test_conditional_call():
    src = (
        "Sets' Sets'\n"
        "  Set sets Set's sets Set's sets set Set's sets\n"
        "Sets'\n"
        "Set Sets' set Set's sets"
    )
    instrs = _parse(src)
    result = pretty_print(instrs)
    lines = result.strip().split("\n")
    assert len(lines) == 4
    assert lines[0] == "Sets' Sets'"
    assert lines[2] == "Sets'"
    assert lines[3] == "Set Sets' set Set's sets"


def test_mixed_program():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Sets' Sets'\n"
        "  Set sets Set's sets Set's sets set Set's sets\n"
        "Sets'\n"
        "Set Sets'"
    )
    instrs = _parse(src)
    result = pretty_print(instrs)
    lines = result.strip().split("\n")
    assert len(lines) == 5
    assert lines[0] == "Set sets Set's sets Set's sets set Set's set"
    assert lines[1] == "Sets' Sets'"
    assert lines[2] == "  Set sets Set's sets Set's sets set Set's sets"
    assert lines[3] == "Sets'"
    assert lines[4] == "Set Sets'"


def test_roundtrip_simple():
    src = "Set sets Set's sets Set's sets set Set's set"
    instrs = _parse(src)
    formatted = pretty_print(instrs)
    back = _parse(formatted)
    assert len(back) == len(instrs)
    assert back[0].opcode == instrs[0].opcode


def test_roundtrip_subroutine():
    src = (
        "Sets' Sets'\n"
        "  Set sets Set's sets Set's sets set Set's sets\n"
        "Sets'\n"
        "Set Sets'"
    )
    instrs = _parse(src)
    formatted = pretty_print(instrs)
    back = _parse(formatted)
    assert len(back) == len(instrs)
    assert back[0].opcode == instrs[0].opcode
    assert back[0].subr_body is not None
    assert back[1].opcode == instrs[1].opcode


def test_roundtrip_full_program():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Set Sets set sets'\n"
        "Set set Set's sets Set's set set Set's sets\n"
        "Set Sets'"
    )
    instrs = _parse(src)
    formatted = pretty_print(instrs)
    back = _parse(formatted)
    for a, b in zip(back, instrs):
        assert a.opcode == b.opcode


def test_roundtrip_hello_world():
    with open("hello_world.s5", encoding="utf-8-sig") as f:
        src = f.read()
    instrs = _parse(src)
    formatted = pretty_print(instrs)
    back = _parse(formatted)
    assert len(back) == len(instrs)
    for i, (a, b) in enumerate(zip(back, instrs)):
        assert a.opcode == b.opcode, f"instr {i} opcode mismatch"


def test_custom_indent():
    src = "Sets' Sets'\n  Set sets Set's sets Set's sets set Set's sets\nSets'"
    instrs = _parse(src)
    result = pretty_print(instrs, indent=4)
    lines = result.strip().split("\n")
    assert lines[1] == "    Set sets Set's sets Set's sets set Set's sets"
