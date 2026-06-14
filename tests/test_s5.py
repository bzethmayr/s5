import subprocess
import sys
from pathlib import Path
import pytest
from s5 import (
    tokenize, Parser, Executor, SubroutineSet, LineSet, set_value, S5Set,
    RuntimeError_, Instruction, Opcode, Address, AddressType, int_to_s5set,
)

HERE = Path(__file__).parent
ROOT = HERE.parent


def run(inp):
    p = subprocess.run(
        [sys.executable, "-m", "s5", "--repl"],
        input=inp, capture_output=True, text=True, cwd=str(ROOT))
    return p.stdout.strip(), p.stderr.strip(), p.returncode


def test_halt_u_u():
    out, err, rc = run("Set set Set's sets Set's sets set Set's sets")
    assert out == "halted"


def test_empty():
    out, err, rc = run("")
    assert out == "finished"


def test_union_u_u():
    out, err, rc = run("Set sets Set's sets Set's sets set Set's sets")
    assert out == "finished"


def test_intersect_u_u():
    out, err, rc = run("Set Set's Set's sets Set's sets set Set's sets")
    assert out == "finished"


def test_multi_halt():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Set Sets set sets' sets\n"
        "Set Set's Set's sets Set's set set Set's sets"
    )
    out, err, rc = run(src)
    assert out == "halted"


def test_diff_c():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Set Sets set sets' sets\n"
        "Set set Set's sets Set's set set Set's sets"
    )
    out, err, rc = run(src)
    assert out == "finished"


def test_derived_a():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Set sets Sets set sets' sets Set's sets set Set's sets"
    )
    out, err, rc = run(src)
    assert out == "finished"


def test_derived_b():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Set sets Set's sets Sets set sets' sets set Set's sets"
    )
    out, err, rc = run(src)
    assert out == "finished"


def test_bounded_int_out_of_bounds():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Set set Set's sets Sets set sets' set sets set Set's sets"
    )
    out, err, rc = run(src)
    assert "out of bounds" in out


def test_c_undefined():
    out, err, rc = run("Set Sets set sets' sets")
    assert "C is undefined" in out


def test_bad_token():
    out, err, rc = run("S foo")
    assert "unknown token" in out


def test_incomplete_instr():
    out, err, rc = run("Set")
    assert "end of input" in out


def test_empty_c_intersect():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Set Sets set sets' sets\n"
        "Set set Set's sets Set's set set Set's set\n"
        "Set Set's Set's set Set's set set Set's sets"
    )
    out, err, rc = run(src)
    assert out in ("halted", "finished")


def test_set_value_empty():
    assert set_value(S5Set()) == 0


def test_set_value_singleton_empty():
    assert set_value(S5Set([S5Set()])) == 1


def test_set_value_singleton_nonempty():
    assert set_value(S5Set([S5Set([S5Set()])])) == 0


def test_set_value_42():
    empty = S5Set()
    nonempty = S5Set([empty])
    s = S5Set([empty, nonempty, nonempty, empty,
               nonempty, nonempty, empty, nonempty])
    assert set_value(s) == 42


def test_s5_compute_42():
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
    parser = Parser(tokens)
    executor = Executor()
    status = executor.run(parser.parse_program())
    assert status == "finished"
    assert set_value(executor.U) == 42


def test_s5_compute_42_subr():
    src = (
        "Set sets Set's sets Set's sets set Set's set\n"
        "Sets' Sets' Sets set sets' set\n"
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets\n"
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets\n"
        "  Set sets Set's sets Sets sets' Sets set sets' sets set Set's sets\n"
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets\n"
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets\n"
        "  Set sets Set's sets Sets sets' Sets set sets' sets set Set's sets\n"
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets\n"
        "Sets'\n"
        "Set Sets' Sets set sets' set"
    )
    tokens = tokenize(src)
    parser = Parser(tokens)
    executor = Executor()
    status = executor.run(parser.parse_program())
    assert status == "finished"
    assert set_value(executor.U) == 42


def test_s5_compute_42_subr_oneline():
    src = " ".join(line.strip() for line in [
        "Set sets Set's sets Set's sets set Set's set",
        "Sets' Sets' Sets set sets' set",
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets",
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets",
        "  Set sets Set's sets Sets sets' Sets set sets' sets set Set's sets",
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets",
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets",
        "  Set sets Set's sets Sets sets' Sets set sets' sets set Set's sets",
        "  Set sets Set's sets Sets sets' Sets sets' Sets set sets' sets set Set's sets",
        "Sets'",
        "Set Sets' Sets set sets' set",
    ])
    tokens = tokenize(src)
    parser = Parser(tokens)
    executor = Executor()
    status = executor.run(parser.parse_program())
    assert status == "finished"
    assert set_value(executor.U) == 42


def run_src(src):
    return Executor().run(Parser(tokenize(src)).parse_program())


class TestSubr:
    def test_subr_decl_default(self):
        src = (
            "Sets' Sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets'"
        )
        assert run_src(src) == "finished"

    def test_subr_explicit_c(self):
        src = (
            "Sets' Sets' Set's set\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets' Set's set"
        )
        assert run_src(src) == "finished"

    def test_subr_call_and_return(self):
        src = (
            "Sets' Sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set sets Set's sets Set's sets set Set's sets\n"
            "Set Sets'"
        )
        tokens = tokenize(src)
        parser = Parser(tokens)
        executor = Executor()
        status = executor.run(parser.parse_program())
        assert status == "finished"
        assert len(executor.U) == 4

    def test_subr_halt_inside(self):
        src = (
            "Sets' Sets'\n"
            "  Set set Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets'"
        )
        out, err, rc = run(src)
        assert out == "halted"

    def test_subr_at_cn(self):
        src = (
            "Set sets Set's sets Set's sets set Set's set\n"
            "Sets' Sets' Sets set sets' sets\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets' Sets set sets' sets"
        )
        out, err, rc = run(src)
        assert out == "finished"

    def test_subr_stores_as_subroutineseet(self):
        src = (
            "Sets' Sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'"
        )
        tokens = tokenize(src)
        parser = Parser(tokens)
        executor = Executor()
        executor.run(parser.parse_program())
        assert isinstance(executor.C, SubroutineSet)
        assert len(executor.C) == 1

    def test_subr_unclosed_decl(self):
        src = (
            "Sets' Sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
        )
        out, err, rc = run(src)
        assert "syntax error" in out

    def test_subr_bare_sets_apos(self):
        out, err, rc = run("Sets'")
        assert "syntax error" in out

    def test_subr_invoke_not_subroutine(self):
        src = (
            "Set sets Set's sets Set's sets set Set's set\n"
            "Set Sets'"
        )
        out, err, rc = run(src)
        assert "not a subroutine" in out

    def test_subr_invoke_undefined_c(self):
        out, err, rc = run("Set Sets'")
        assert "C is undefined" in out

    def test_subr_set_value_42(self):
        empty = S5Set()
        nonempty = S5Set([empty])
        s = S5Set([empty, nonempty, nonempty, empty,
                   nonempty, nonempty, empty, nonempty])
        assert set_value(s) == 42


class TestCondCall:
    def test_cond_call_nonempty_calls(self):
        src = (
            "Sets' Sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets' set Set's sets"
        )
        executor = Executor()
        status = executor.run(Parser(tokenize(src)).parse_program())
        assert status == "finished"
        assert len(executor.U) == 2

    def test_cond_call_empty_skips(self):
        src = (
            "Sets' Sets' Set's sets\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set sets Set's sets Set's sets set Set's set\n"
            "Set set Set's set Set's set set Set's set\n"
            "Set Sets' set Set's set"
        )
        executor = Executor()
        status = executor.run(Parser(tokenize(src)).parse_program())
        assert status == "finished"
        assert len(executor.U) == 1

    def test_cond_call_explicit_addr(self):
        src = (
            "Set sets Set's sets Set's sets set Set's set\n"
            "Sets' Sets' Sets set sets' sets\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets' set Set's sets Sets set sets' sets"
        )
        out, err, rc = run(src)
        assert "finished" in out
        assert rc == 0

    def test_cond_call_default_c(self):
        src = (
            "Sets' Sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets' set Set's sets"
        )
        out, err, rc = run(src)
        assert "finished" in out
        assert rc == 0

    def test_cond_call_empty_does_not_call(self):
        src = (
            "Sets' Sets' Set's sets\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set sets Set's sets Set's sets set Set's set\n"
            "Set set Set's set Set's set set Set's set\n"
            "Set Sets' set Set's set\n"
            "Set set Set's sets Set's sets set Set's sets"
        )
        out, err, rc = run(src)
        assert "halted" in out
        assert rc == 0


class TestUD:
    def test_subr_define_at_u0_and_call(self):
        src = (
            "Sets' Sets' Sets sets sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'\n"
            "Set Sets' Sets sets sets'"
        )
        executor = Executor()
        assert len(executor.U) == 1
        status = executor.run(Parser(tokenize(src)).parse_program())
        assert status == "finished"
        assert len(executor.U) == 2

    def test_subr_define_at_u0_store_type(self):
        src = (
            "Sets' Sets' Sets sets sets'\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'"
        )
        executor = Executor()
        executor.run(Parser(tokenize(src)).parse_program())
        assert isinstance(executor.U[0], SubroutineSet)

    def test_ud_index_out_of_bounds_assign(self):
        src = (
            "Sets' Sets' Sets sets sets' set set\n"
            "  Set sets Set's sets Set's sets set Set's sets\n"
            "Sets'"
        )
        with pytest.raises(RuntimeError_, match="U\\[2\\] out of bounds"):
            Executor().run(Parser(tokenize(src)).parse_program())

    def test_ud_index_out_of_bounds_resolve(self):
        src = "Set Sets' Sets sets sets' set set"
        with pytest.raises(RuntimeError_, match="U\\[2\\] out of bounds"):
            Executor().run(Parser(tokenize(src)).parse_program())


class TestSubrValue:
    def make_instr(self):
        return Instruction(
            Opcode.UNION,
            addr_a=Address(AddressType.U),
            addr_b=Address(AddressType.U),
            addr_dest=Address(AddressType.U),
        )

    def test_subr_value_equals_instruction_count(self):
        instr = self.make_instr()
        n = 3
        subr = SubroutineSet([instr] * n, [LineSet(i) for i in [instr] * n])
        assert set_value(subr) == n

    def test_subr_union_one_normalize(self):
        instr = self.make_instr()
        n = 3
        subr = SubroutineSet([instr] * n, [LineSet(i) for i in [instr] * n])
        assert set_value(subr) == n

        ONE = S5Set([S5Set()])
        combined = subr.union(ONE)
        assert set_value(combined) == n + 1

        normalized = int_to_s5set(set_value(combined))
        assert set_value(normalized) == n + 1
        assert normalized == int_to_s5set(n + 1)

    def test_subr_union_one_commutes(self):
        instr = self.make_instr()
        n = 3
        subr = SubroutineSet([instr] * n, [LineSet(i) for i in [instr] * n])
        ONE = S5Set([S5Set()])
        assert set_value(ONE.union(subr)) == set_value(subr.union(ONE)) == n + 1

    def test_normalized_suffix_encoding(self):
        # Suffix concatenation of normalized sets does not combine
        # by simple arithmetic — the result depends on the internal
        # arrangement of empty/nonempty elements in each operand.
        # This is a fundamental limit of using values operationally.
        # int_to_s5set(2) = [{}, {∅}]        len: 0, 1
        # int_to_s5set(4) = [{}, {∅}, {∅}]   len: 0, 1, 1
        # concatenated  : [{}, {∅}, {}, {∅}, {∅}]  len: 0, 1, 0, 1, 1
        # set_value: 0→+1=1→×2=2→+1=3→×2=6→×2=12
        base = int_to_s5set(2)
        norm = int_to_s5set(4)
        with_suffix = base.union(norm)
        assert set_value(with_suffix) == 12


_EMPTY = S5Set()
_NONEMPTY = S5Set([_EMPTY])


class TestSubsetSelectIndirect:
    def test_direct_still_works(self):
        src = (
            "Set sets Set's sets Set's sets set Set's set\n"
            "Set Sets set sets' set"
        )
        exec = Executor()
        status = exec.run(Parser(tokenize(src)).parse_program())
        assert status == "finished"
        assert exec.C == S5Set()

    def test_indirect_via_u(self):
        exec = Executor()
        exec.C = S5Set([_EMPTY, _NONEMPTY])          # len=2
        instr = Instruction(Opcode.SUBSET_SELECT, addr_b=Address(AddressType.U))
        exec.exec_instruction(instr)
        # value(U) = value({∅}) = 1 → C = C[1] = {∅}
        assert exec.C == _NONEMPTY

    def test_indirect_via_c(self):
        exec = Executor()
        exec.C = S5Set([_NONEMPTY, _EMPTY])           # { {∅}, ∅ }, value = 0→×2=0→+1=1, len=2
        instr = Instruction(Opcode.SUBSET_SELECT, addr_b=Address(AddressType.C))
        exec.exec_instruction(instr)
        # value(C) = 1 → C = C[1] = ∅
        assert exec.C == _EMPTY

    def test_indirect_via_derived(self):
        exec = Executor()
        exec.C = S5Set([_NONEMPTY, _EMPTY])           # C = { {∅}, ∅ }
        exec.U = S5Set([_EMPTY, _NONEMPTY])           # U = { ∅, {∅} }
        # Index from C[0]: value(C[0]) = value({∅}) = 1
        instr = Instruction(Opcode.SUBSET_SELECT, addr_b=Address(AddressType.DERIVED, index=0))
        exec.exec_instruction(instr)
        assert exec.C == _EMPTY                       # C[1] = ∅

    def test_indirect_via_ud(self):
        exec = Executor()
        exec.C = S5Set([_EMPTY, _NONEMPTY])           # len=2
        exec.U = S5Set([_EMPTY, _NONEMPTY, _EMPTY])   # U[1] = {∅} → value = 1
        instr = Instruction(Opcode.SUBSET_SELECT, addr_b=Address(AddressType.UD, index=1))
        exec.exec_instruction(instr)
        assert exec.C == _NONEMPTY                     # C[1] = {∅}

    def test_indirect_via_wrap(self):
        exec = Executor()
        exec.C = S5Set([_EMPTY, _NONEMPTY])            # len=2
        # wrap U into {U}; {U} = {{∅}} has value 0 (single nonempty → ×2)
        wrap = Address(AddressType.WRAP, sub_addr=Address(AddressType.U))
        instr = Instruction(Opcode.SUBSET_SELECT, addr_b=wrap)
        exec.exec_instruction(instr)
        assert exec.C == _EMPTY                        # C[0] = ∅

    def test_indirect_via_depth_suffix(self):
        exec = Executor()
        # U = {{∅}, ∅}: value = 0→×2=0→+1=1, len=2 → dispatch through U[1]=∅
        exec.U = S5Set([_NONEMPTY, _EMPTY])
        exec.C = S5Set([_NONEMPTY, _EMPTY])            # len=2
        # U with depth 2: resolve → V1=U, value(U)=1 → V2=U[1]=∅ → value=0
        addr = Address(AddressType.U, dispatch_depth=2)
        instr = Instruction(Opcode.SUBSET_SELECT, addr_b=addr)
        exec.exec_instruction(instr)
        assert exec.C == _NONEMPTY                     # C[0] = {∅}

    def test_indirect_oob_from_index(self):
        exec = Executor()
        exec.C = S5Set([_EMPTY])                       # len=1
        instr = Instruction(Opcode.SUBSET_SELECT, addr_b=Address(AddressType.U))
        with pytest.raises(RuntimeError_, match="out of bounds"):
            exec.exec_instruction(instr)

    def test_parse_indirect_via_u(self):
        src = "Set Sets set sets' Set's sets"
        instrs = Parser(tokenize(src)).parse_program()
        assert len(instrs) == 1
        assert instrs[0].opcode == Opcode.SUBSET_SELECT
        assert instrs[0].addr_b is not None
        assert instrs[0].addr_b.type == AddressType.U
        assert instrs[0].n is None

    def test_parse_direct_integer(self):
        src = "Set Sets set sets' set sets"
        instrs = Parser(tokenize(src)).parse_program()
        assert len(instrs) == 1
        assert instrs[0].opcode == Opcode.SUBSET_SELECT
        assert instrs[0].addr_b is None
        assert instrs[0].n == 2

    def test_parse_direct_empty_integer(self):
        src = "Set Sets set sets'"
        instrs = Parser(tokenize(src)).parse_program()
        assert len(instrs) == 1
        assert instrs[0].opcode == Opcode.SUBSET_SELECT
        assert instrs[0].addr_b is None
        assert instrs[0].n == 0

    def test_serialize_roundtrip_indirect_u(self):
        from s5.serialize import serialize_instruction
        src = "Set Sets set sets' Set's sets"
        instrs = Parser(tokenize(src)).parse_program()
        tokens = serialize_instruction(instrs[0])
        back = Parser(iter(tokens)).parse_program()
        assert back[0].opcode == Opcode.SUBSET_SELECT
        assert back[0].addr_b is not None
        assert back[0].addr_b.type == AddressType.U

    def test_pretty_roundtrip_indirect(self):
        from s5.pretty import pretty_print
        for src in ("Set Sets set sets' Set's sets",
                    "Set Sets set sets' sets set's'",
                    "Set Sets set sets' sets sets set's'"):
            instrs = Parser(tokenize(src)).parse_program()
            formatted = pretty_print(instrs)
            back = Parser(tokenize(formatted.strip())).parse_program()
            assert back[0].opcode == instrs[0].opcode
            assert back[0].addr_b is not None
            assert back[0].addr_b.type == instrs[0].addr_b.type
