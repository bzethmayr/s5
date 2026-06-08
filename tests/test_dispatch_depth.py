import pytest
from s5 import Executor, Parser, S5Set, AddressType, Address, set_value, tokenize, SubroutineSet, LineSet, int_to_s5set, Opcode, Instruction

empty = S5Set()


def run_src(src, exec=None):
    parsed = Parser(tokenize(src)).parse_program()
    if exec:
        return exec.run(parsed)
    else:
        return Executor().run(parsed)


class TestParseDepth:
    def test_no_depth_defaults_to_1(self):
        addr = Parser(tokenize("Set's sets")).parse_address()
        assert addr.dispatch_depth == 1

    def test_u_with_depth_2(self):
        addr = Parser(tokenize("Set's sets sets' set")).parse_address()
        assert addr.type == AddressType.U
        assert addr.dispatch_depth == 2

    def test_c_with_depth_3(self):
        addr = Parser(tokenize("Set's set sets' set sets")).parse_address()
        assert addr.type == AddressType.C
        assert addr.dispatch_depth == 3

    def test_cn_with_depth_2(self):
        addr = Parser(tokenize("Sets set sets' set sets' set")).parse_address()
        assert addr.type == AddressType.DERIVED
        assert addr.index == 1
        assert addr.dispatch_depth == 2

    def test_ud_with_depth_3(self):
        addr = Parser(tokenize("Sets sets sets' set sets' set sets")).parse_address()
        assert addr.type == AddressType.UD
        assert addr.index == 1
        assert addr.dispatch_depth == 3

    def test_io_with_depth_2(self):
        addr = Parser(tokenize("set's' sets' set")).parse_address()
        assert addr.type == AddressType.IO
        assert addr.dispatch_depth == 2

    def test_io_byte_with_depth_2(self):
        addr = Parser(tokenize("sets set's' sets' set")).parse_address()
        assert addr.type == AddressType.IO_BYTE
        assert addr.dispatch_depth == 2

    def test_wrap_with_inner_depth(self):
        addr = Parser(tokenize("Sets sets' Set's sets sets' set")).parse_address()
        assert addr.type == AddressType.WRAP
        assert addr.sub_addr.type == AddressType.U
        assert addr.sub_addr.dispatch_depth == 2

    def test_bounded_integer_no_interference(self):
        src = "Set's set sets' set sets Set's sets set Set's sets"
        tokens = tokenize(src)
        parser = Parser(tokens)
        a = parser.parse_address()
        b = parser.parse_address(bound_integer=True)
        assert a.type == AddressType.C
        assert a.dispatch_depth == 3
        assert b.type == AddressType.U

    def test_depth_0_via_sets(self):
        addr = Parser(tokenize("Set's sets sets' sets")).parse_address()
        assert addr.type == AddressType.U
        assert addr.dispatch_depth == 1

    def test_depth_4_encoding(self):
        addr = Parser(tokenize("Set's sets sets' set set set")).parse_address()
        assert addr.type == AddressType.U
        assert addr.dispatch_depth == 4


class TestRValue:
    def test_depth_1_unchanged(self):
        exec = Executor()
        exec.U = S5Set([empty, S5Set([empty])])
        addr = Address(AddressType.U, dispatch_depth=1)
        assert exec.resolve(addr) is exec.U

    def test_depth_2_from_c_resolves_through_u(self):
        exec = Executor()
        exec.U = S5Set([empty, S5Set([empty])])
        exec.C = int_to_s5set(0)
        addr = Address(AddressType.C, dispatch_depth=2)
        result = exec.resolve(addr)
        assert result == empty

    def test_depth_2_from_u_index(self):
        exec = Executor()
        val_at_u2 = S5Set([empty, empty])
        exec.U = S5Set([empty, S5Set([empty]), val_at_u2])
        exec.C = int_to_s5set(2)
        addr = Address(AddressType.C, dispatch_depth=2)
        result = exec.resolve(addr)
        assert result == val_at_u2

    def test_depth_3_chain(self):
        exec = Executor()
        target = S5Set([empty])
        exec.U = S5Set([int_to_s5set(2), S5Set(), target])
        exec.C = int_to_s5set(0)
        addr = Address(AddressType.C, dispatch_depth=3)
        result = exec.resolve(addr)
        assert result == target

    def test_depth_2_through_derived(self):
        exec = Executor()
        exec.U = S5Set([empty, S5Set([empty])])
        exec.C = S5Set([int_to_s5set(0)])
        addr = Address(AddressType.DERIVED, index=0, dispatch_depth=2)
        result = exec.resolve(addr)
        assert result == empty

    def test_depth_oob_in_chain(self):
        exec = Executor()
        exec.U = S5Set([empty])
        exec.C = int_to_s5set(5)
        addr = Address(AddressType.C, dispatch_depth=2)
        with pytest.raises(Exception, match="out of bounds"):
            exec.resolve(addr)

    def test_depth_2_on_wrap_resolves_inner_then_indirect(self):
        exec = Executor()
        exec.C = int_to_s5set(0)
        exec.U = S5Set([empty, S5Set([empty])])
        inner = Address(AddressType.C, dispatch_depth=2)
        addr = Address(AddressType.WRAP, sub_addr=inner)
        result = exec.resolve(addr)
        assert result == S5Set([empty])

    def test_depth_2_on_ud(self):
        exec = Executor()
        exec.U = S5Set([empty, empty])
        addr = Address(AddressType.UD, index=1, dispatch_depth=2)
        result = exec.resolve(addr)
        assert result == empty

    def test_depth_2_from_u_self(self):
        exec = Executor()
        exec.U = S5Set([S5Set([empty]), empty])
        addr = Address(AddressType.U, dispatch_depth=2)
        result = exec.resolve(addr)
        assert result == empty


class TestLValue:
    def test_depth_2_stores_into_u_slot(self):
        exec = Executor()
        exec.U = S5Set([empty, empty])
        exec.C = int_to_s5set(0)
        addr = Address(AddressType.C, dispatch_depth=2)
        val = S5Set([empty])
        exec.assign(addr, val)
        assert exec.U[0] == S5Set([empty])
        assert exec.U[1] == empty

    def test_depth_3_stores_into_chained_slot(self):
        exec = Executor()
        val = S5Set([empty, empty])
        exec.U = S5Set([int_to_s5set(1), empty, empty])
        exec.C = int_to_s5set(0)
        addr = Address(AddressType.C, dispatch_depth=3)
        exec.assign(addr, val)
        assert exec.U[0] == int_to_s5set(1)
        assert exec.U[1] == val
        assert exec.U[2] == empty

    def test_depth_1_unchanged(self):
        exec = Executor()
        exec.U = S5Set([empty, empty])
        exec.C = S5Set([empty])
        addr = Address(AddressType.C, dispatch_depth=1)
        val = S5Set([empty, empty])
        exec.assign(addr, val)
        assert exec.C == S5Set([empty, empty])

    def test_depth_oob_in_chain(self):
        exec = Executor()
        exec.U = S5Set([empty])
        exec.C = int_to_s5set(1)
        addr = Address(AddressType.C, dispatch_depth=2)
        with pytest.raises(Exception, match="out of bounds"):
            exec.assign(addr, S5Set([empty]))

    def test_depth_oob_final_slot(self):
        exec = Executor()
        exec.U = S5Set([empty])
        exec.C = int_to_s5set(1)
        addr = Address(AddressType.C, dispatch_depth=2)
        val = S5Set([empty])
        with pytest.raises(Exception, match="out of bounds"):
            exec.assign(addr, val)

    def test_depth_2_from_derived(self):
        exec = Executor()
        exec.U = S5Set([empty, empty, empty])
        exec.C = S5Set([int_to_s5set(1)])
        addr = Address(AddressType.DERIVED, index=0, dispatch_depth=2)
        val = S5Set([empty, empty])
        exec.assign(addr, val)
        assert exec.U[1] == S5Set([empty, empty])

    def test_depth_2_from_ud(self):
        exec = Executor()
        exec.U = S5Set([int_to_s5set(1), empty, empty])
        addr = Address(AddressType.UD, index=0, dispatch_depth=2)
        val = S5Set([empty, empty])
        exec.assign(addr, val)
        assert exec.U[1] == S5Set([empty, empty])


class TestSubroutineDispatch:
    def test_depth_2_call_through_c_to_u(self):
        exec = Executor()
        body_src = "Set sets Set's sets Set's sets set Set's sets"
        subr_instr = Parser(tokenize(body_src)).parse_program()
        lines = tuple(LineSet(inst) for inst in subr_instr)
        subr = SubroutineSet(subr_instr, lines)
        exec.U = S5Set([subr, empty])
        exec.C = int_to_s5set(0)
        addr = Address(AddressType.C, dispatch_depth=2)
        instr = Instruction(Opcode.SUBR, addr_a=addr)
        exec.exec_instruction(instr)
        assert len(exec.U) == 4

    def test_depth_2_call_on_u0(self):
        exec = Executor()
        body_src = "Set sets Set's sets Set's sets set Set's sets"
        subr_instr = Parser(tokenize(body_src)).parse_program()
        lines = tuple(LineSet(inst) for inst in subr_instr)
        subr = SubroutineSet(subr_instr, lines)
        exec.U = S5Set([empty, subr])
        exec.C = int_to_s5set(1)
        addr = Address(AddressType.C, dispatch_depth=2)
        instr = Instruction(Opcode.SUBR, addr_a=addr)
        exec.exec_instruction(instr)
        assert len(exec.U) == 4

    def test_depth_2_conditional_call(self):
        exec = Executor()
        body_src = "Set sets Set's sets Set's sets set Set's sets"
        subr_instr = Parser(tokenize(body_src)).parse_program()
        lines = tuple(LineSet(inst) for inst in subr_instr)
        subr = SubroutineSet(subr_instr, lines)
        exec.U = S5Set([subr, empty])
        exec.C = int_to_s5set(0)
        cond_addr = Address(AddressType.U)
        subr_addr = Address(AddressType.C, dispatch_depth=2)
        instr = Instruction(Opcode.SUBR, addr_a=subr_addr, addr_b=cond_addr)
        exec.exec_instruction(instr)
        assert len(exec.U) == 4


class TestIntegration:
    def test_depth_suffix_in_b_operand_parses(self):
        src = (
            "Set sets Set's sets Set's set sets' set set Set's sets"
        )
        tokens = tokenize(src)
        parser = Parser(tokens)
        instrs = parser.parse_program()
        assert len(instrs) == 1
        assert instrs[0].addr_a.type == AddressType.U
        assert instrs[0].addr_a.dispatch_depth == 1
        assert instrs[0].addr_b.type == AddressType.C
        assert instrs[0].addr_b.dispatch_depth == 2

    def test_depth_suffix_in_a_operand_parses(self):
        src = (
            "Set sets Set's set sets' set Set's sets set Set's sets"
        )
        tokens = tokenize(src)
        parser = Parser(tokens)
        instrs = parser.parse_program()
        assert len(instrs) == 1
        assert instrs[0].addr_a.type == AddressType.C
        assert instrs[0].addr_a.dispatch_depth == 2
        assert instrs[0].addr_b.type == AddressType.U

    def test_depth_suffix_in_destination_parses(self):
        src = (
            "Set sets Set's sets Set's sets set Set's sets sets' set"
        )
        tokens = tokenize(src)
        parser = Parser(tokens)
        instrs = parser.parse_program()
        assert len(instrs) == 1
        assert instrs[0].addr_dest.type == AddressType.U
        assert instrs[0].addr_dest.dispatch_depth == 2

    def test_depth_suffix_in_wrap_inner_parses(self):
        src = (
            "Set sets Set's sets Sets sets' Set's sets sets' set set Set's sets"
        )
        tokens = tokenize(src)
        parser = Parser(tokens)
        instrs = parser.parse_program()
        assert len(instrs) == 1
        assert instrs[0].addr_b.type == AddressType.WRAP
        assert instrs[0].addr_b.sub_addr.type == AddressType.U
        assert instrs[0].addr_b.sub_addr.dispatch_depth == 2

    def test_basic_execution_with_depth_suffix(self):
        exec = Executor()
        exec.U = S5Set([empty, S5Set([empty])])
        exec.C = int_to_s5set(0)
        addr = Address(AddressType.C, dispatch_depth=2)
        result = exec.resolve(addr)
        assert result == empty
