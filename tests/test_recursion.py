from s5 import Executor, Instruction, Opcode

DEPTH = 20000


def _nested_tail_call_body(depth):
    """Build a body of `depth` nested levels, each declaring the next level in
    C and then calling it as its final instruction (a tail call)."""
    body = []
    for _ in range(depth):
        body = [
            Instruction(Opcode.SUBR, subr_body=body),
            Instruction(Opcode.SUBR),
        ]
    return body


class TestDeepRecursion:
    def test_deep_tail_recursion_does_not_use_python_stack(self):
        executor = Executor()
        status = executor.run(_nested_tail_call_body(DEPTH))
        assert status == "finished"

    def test_repeated_run_is_independent(self):
        executor = Executor()
        body = _nested_tail_call_body(DEPTH)
        assert executor.run(body) == "finished"
        assert executor.run(body) == "finished"
