"""Generate demo.s5 — LUT-based decrement demo using S5B self-I/O.

Dependencies: init.s5 + succ.s5 + pred.s5

Slot usage (beyond what init/succ/pred allocate):
  U[3]  = IN_A / loop variable V
  U[4]  = MAX_VAL
  U[5]  = OUT (pred result / final result)
  U[8]  = QUERY_VAL
  U[9]  = succ(MAX_VAL) precomputed
  U[10] = flag (∅ = not found in range, ONE = Q found during LUT build)
  U[11] = scratch (encoding rem)
  U[12] = DEMO subroutines (see below)
  U[20+] = pre-built byte values for IO_BYTE writes

U[12] subroutines:
  [0] DEMO_MAIN           — entry point
  [1] BUILD_LOOP          — build one LUT entry, maybe recurse
  [2] LUT_LOOKUP          — S5B self-I/O for SUBSET_SELECT + halt
  [3] SEARCH_PRED         — fallback: call pred_main on QUERY_VAL
  [4] ENCODE_DECR         — encoding decrement loop helper
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from s5 import Address, AddressType, Opcode, Instruction, TokenType
from s5.pretty import pretty_print
from s5.serialize import serialize_body, serialize_integer, serialize_address
from s5.binary import encode_tokens, TOKEN_TO_CODE, _even_parity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def U():    return Address(AddressType.U)
def C():    return Address(AddressType.C)
def UD(i):  return Address(AddressType.UD, index=i)
def WRAP(a): return Address(AddressType.WRAP, sub_addr=a)

def IO(depth=1):
    a = Address(AddressType.IO)
    a.dispatch_depth = depth
    a.has_depth = True
    return a

def IO_BYTE(depth=1):
    a = Address(AddressType.IO_BYTE)
    a.dispatch_depth = depth
    a.has_depth = True
    return a

def IO_S5B(depth=1):
    a = Address(AddressType.IO_S5B)
    a.dispatch_depth = depth
    a.has_depth = True
    return a

def union(a, b, d):  return Instruction(Opcode.UNION, addr_a=a, addr_b=b, addr_dest=d)
def inters(a, b, d): return Instruction(Opcode.INTERSECTION, addr_a=a, addr_b=b, addr_dest=d)
def diff_(a, b, d):  return Instruction(Opcode.DIFFERENCE, addr_a=a, addr_b=b, addr_dest=d)
def subset(n):       return Instruction(Opcode.SUBSET_SELECT, n=n)
def subr_decl(body, loc=None):
    return Instruction(Opcode.SUBR, subr_body=body, addr_a=loc)
def subr_call(loc=None, cond=None):
    return Instruction(Opcode.SUBR, addr_a=loc, addr_b=cond)


# ---------------------------------------------------------------------------
# Byte values needed (unique, sorted for incremental build)
# ---------------------------------------------------------------------------
# Fixed parts of the LUT-lookup S5B body:
#   C = U[7] → 11 bytes: 0x30 0xa5 0x9c 0x9a 0x9a 0xa5 0x9c 0x9a 0x9a 0x39 0x89
#   SUBSET_SELECT prefix → 2 bytes: 0x50 0xc9
#   U[5] = C → 7 bytes: 0x30 0x93 0x93 0x59 0xca 0xa9 0x9a
# Variable encoding bytes: 0x9a 0x99 0x89
#
# Unique byte values:
NEEDED_BYTES = sorted(set([
    0x30, 0xa5, 0x9c, 0x9a, 0x39, 0x89,   # C=U7
    0x50, 0xc9,                             # SUBSET_SELECT prefix
    0x93, 0x59, 0xca, 0xa9,                # U5=C
    0x99,                                   # encoding pair
]))
# NEEDED_BYTES = [0x30,0x39,0x50,0x59,0x89,0x93,0x99,0x9a,0x9c,0xa5,0xa9,0xc9,0xca]
# Values: 48, 57, 80, 89, 137, 147, 153, 154, 156, 165, 169, 201, 202

# Map byte value -> U slot index
BYTE_SLOT_START = 20
byte_slot = {b: BYTE_SLOT_START + i for i, b in enumerate(NEEDED_BYTES)}


def s5b_bytes_for_instructions(instrs):
    """Return list of S5B byte values for a list of Instruction objects."""
    tokens = serialize_body(instrs)
    return list(encode_tokens(tokens))


# Pre-compute fixed S5B byte lists
fixed_c_eq_u7 = s5b_bytes_for_instructions([
    inters(UD(7), UD(7), C()),
])
fixed_subset_prefix = s5b_bytes_for_instructions([
    Instruction(Opcode.SUBSET_SELECT, n=0),
])[:2]  # just the 2 prefix bytes (n=0 adds 2 tokens; we only want the 4 prefix tokens)
# Actually n=0 gives serialize_integer(0)=[] so the token list is [Sing,PlCap,SingL,PlApos]
# which is exactly the prefix.  Fixed 2 bytes.
fixed_u5_eq_c = s5b_bytes_for_instructions([
    inters(C(), C(), UD(5)),
])

# ---------------------------------------------------------------------------
# Step 1: Build the byte-value slots via incremental succ
# ---------------------------------------------------------------------------
# We generate a flat sequence of instructions that increment C from ZERO
# through each target value, storing intermediate results in U slots.

# Helper: generate succ(N) call instructions for a list of Instruction objects
def gen_succ_calls(n):
    """Generate n succ() call instruction groups."""
    out = []
    for _ in range(n):
        # C = succ(C) via NORM_SUCC (U[6][0])
        # Save C in IN_A (U[3]), call succ, copy OUT to C
        out.extend([
            inters(UD(3), UD(3), C()),        # scratch = C (IN_A copy)
        ])
        # Actually NORM_SUCC reads IN_A from U[3], so set it:
        # IN_A = C → already in U[3] from above? No, inters(UD(3),UD(3),C()) sets U[3]=C
        # Wait: inters(a,b,Dest) means Dest = a ∩ b. So inters(UD(3),UD(3),C()) means C = U[3].
        # That's BACKWARDS. We want U[3] = C.
        pass
    return out

# Actually, generating succ N times is tedious in instruction form.
# Let me use a different approach: inline the instructions directly.
# Each "C = succ(C)" is:
#   1. Copy C to IN_A (U[3]): inters(C(), C(), UD(3))
#   2. Load SUCC: inters(UD(6), UD(6), C())
#   3. Select NORM_SUCC: subset(0)
#   4. Call: subr_call()
#   5. Copy OUT to C: inters(UD(5), UD(5), C())
# That's 5 instructions per succ. For ~202 total, ~1010 instructions.

# But we can optimize: we don't NEED all 13 byte values as separate slots.
# We only need to WRITE bytes via IO_BYTE'1 during the loop.
# The bytes we write are the same every time (fixed parts + encoding bytes).
# We can batch them: write all fixed bytes at once using a pre-computed
# SubroutineSet.

# KEY INSIGHT: Instead of building byte values individually,
# we can build a SINGLE SubroutineSet whose body IS the S5B content
# we want.  Writing it to IO_S5B'1 serializes the body as S5B bytes.

# So the flow for the LUT lookup body:
#   1. Build a SubroutineSet with the REQUIRED instructions
#      (C=U7 + SUBSET_SELECT + U5=C), where the SUBSET_SELECT
#      uses n = 3+QUERY_VAL
#   2. Write via IO_S5B'1 → serializes to S5B bytes in the buffer
#   3. Read back via IO_S5B'1 → get the same SubroutineSet
#   4. Assign to C, execute

# But step 1 requires building a SubroutineSet at RUNTIME
# with a dynamic n value.  We can't create SubroutineSets at runtime in S5.
# SubroutineSets are only created by Parser._parse_program or by S5B read.

# So the previous plan (write bytes via IO_BYTE) is correct.
# Let me generate the succ sequences more efficiently.

# APPROACH: Generate a single flat block of succ instructions.
# The Python code below outputs the S5 text for building all byte values.


def make_byte_build_instructions():
    """Return list of instructions to build byte-value slots."""
    instrs = []
    # Start with C = ZERO
    instrs.append(inters(UD(0), UD(0), C()))  # C = ZERO
    
    prev_val = 0
    for val in NEEDED_BYTES:
        diff = val - prev_val
        # Apply succ diff times
        for _ in range(diff):
            # C = succ(C)  (5 instructions each)
            instrs.append(inters(C(), C(), UD(3)))  # IN_A = C
            instrs.append(inters(UD(6), UD(6), C()))  # C = U[6]
            instrs.append(subset(0))                   # C = C[0] = NORM_SUCC
            instrs.append(subr_call())                  # call succ
            instrs.append(inters(UD(5), UD(5), C()))  # C = OUT
        # Store in slot
        instrs.append(inters(C(), C(), UD(byte_slot[val])))
        prev_val = val
    
    return instrs


# ---------------------------------------------------------------------------
# Step 2: Define the demo subroutines
# ---------------------------------------------------------------------------

# --- DEMO_MAIN (U[12][0]) ---
demo_main = [
    # Read MAX_VAL from stdin → U[4]
    inters(IO(), IO(), UD(4)),         # U[4] = IO (read int from stdin)
    
    # Read QUERY_VAL from stdin → U[8]
    inters(IO(), IO(), UD(8)),         # U[8] = IO
    
    # Precompute succ(MAX_VAL) → U[9]
    inters(UD(4), UD(4), UD(3)),       # IN_A = MAX_VAL
    inters(UD(6), UD(6), C()),         # C = U[6]
    subset(0),                          # C = C[0] = NORM_SUCC
    subr_call(),                        # call succ
    inters(UD(5), UD(5), UD(9)),       # U[9] = succ(MAX_VAL)
    
    # V = 0 → U[3]
    inters(UD(0), UD(0), UD(3)),       # V = ZERO
    
    # flag = ∅ (not found)
    diff_(C(), C(), UD(10)),           # U[10] = C \ C = ∅
    
    # Call BUILD_LOOP
    inters(UD(12), UD(12), C()),       # C = U[12]
    subset(1),                          # C = C[1] = BUILD_LOOP
    subr_call(),                        # call BUILD_LOOP
    
    # Dispatch: if flag nonempty, LUT_LOOKUP; else SEARCH_PRED
    inters(UD(12), UD(12), C()),       # C = U[12]
    subset(2),                          # C = C[2] = LUT_LOOKUP
    subr_call(cond=UD(10)),            # call only if flag set (Q in range)
    
    # Fallthrough: SEARCH_PRED
    inters(UD(12), UD(12), C()),       # C = U[12]
    subset(3),                          # C = C[3] = SEARCH_PRED
    subr_call(),                        # call SEARCH_PRED
    
    # Output result from U[5]
    inters(UD(5), UD(5), C()),         # C = OUT
    union(UD(0), WRAP(C()), IO()),     # IO = C (print result)
]


# --- BUILD_LOOP (U[12][1]) ---
# Call pred(V), append to U[7], check V==Q, increment V, maybe recurse
build_loop = [
    # Call pred_main (U[7][0]) with IN_A = V (U[3])
    # PRED_MAIN automatically saves IN_A to U[4] and returns result in U[5]
    inters(UD(7), UD(7), C()),         # C = U[7]
    subset(0),                          # C = C[0] = PRED_MAIN
    subr_call(),                        # call pred_main
    # OUT = U[5] now has pred(V)
    
    # Append pred(V) to U[7]
    inters(UD(5), UD(5), C()),         # C = OUT
    # U[7] = U[7] ∪ {C}
    union(UD(7), WRAP(C()), UD(7)),
    
    # Check if V == QUERY_VAL
    diff_(WRAP(UD(3)), WRAP(UD(8)), UD(11)),  # U[11] = diff(WRAP(V), WRAP(Q))
    # If U[11] empty (V==Q): set flag
    # We can't do IF/ELSE directly.  Use conditional call to a helper.
    # Instead: flag = flag ∪ ONE (set to true), but only if V==Q.
    # COND = diff(WRAP(V), WRAP(Q)) reversed: diff is empty when equal
    # Actually diff(WRAP(V), WRAP(Q)) is empty when V == Q
    # We want to SET flag when V == Q:
    #   if diff is empty: flag = ONE (which is nonempty → truthy)
    #   Use: inters(UD(1), UD(1), UD(10)) when diff empty
    # But we can only conditionally CALL when COND is nonempty.
    # Invert: diff(WRAP(Q), WRAP(V)) is empty when Q == V → same thing.
    # So we need a subroutine that sets flag when called.
    # Subroutine SET_FLAG: U[10] = ONE
    # Call SET_FLAG if diff(WRAP(V), WRAP(Q)) is EMPTY.
    # We can't call on empty condition.  Use the opposite:
    #   diff(WRAP(UD(3)), WRAP(UD(8)), UD(11))  (nonempty when V != Q)
    #   If U[11] nonempty: DON'T set flag
    #   If U[11] empty: SET flag
    # We can only CALL on nonempty condition.
    # Restructure: call SET_FLAG always, inside check condition.
    # No, simpler: SET_FLAG = U[10] = ONE (idempotent), called always.
    # Then check if V != Q to SKIP... but we can't conditionally skip a call.
    # 
    # Alternative: compute both conditions and use WRAP trick.
    # We can compute: cond = `diff(WRAP(UD(0)), WRAP(... 
    # Actually, the simplest: call a helper that checks V == Q and sets flag.
    # BUILD_LOOP calls CHECK_AND_SET always.
    # (We'll add a subr at U[12][5] for this)
    inters(UD(12), UD(12), C()),       # C = U[12]
    subset(5),                          # C = C[5] = CHECK_AND_SET
    subr_call(),                        # call always
    
    # Increment V
    inters(UD(3), UD(3), UD(3)),       # IN_A = V (copy V to IN_A for succ call)
    inters(UD(6), UD(6), C()),         # C = U[6]
    subset(0),                          # C = C[0] = NORM_SUCC
    subr_call(),                        # call succ
    inters(UD(5), UD(5), UD(3)),       # V = OUT (succ(V))
    
    # Check if V > MAX_VAL: V == succ(MAX_VAL)?
    diff_(WRAP(UD(3)), WRAP(UD(9)), UD(11)),  # U[11] = diff(WRAP(V), WRAP(succ(MAX_VAL)))
    # Nonempty when V != MAX_VAL+1 → continue loop
    inters(UD(12), UD(12), C()),       # C = U[12]
    subset(1),                          # C = C[1] = BUILD_LOOP
    subr_call(cond=UD(11)),            # call if V != MAX_VAL+1
]


# --- CHECK_AND_SET (U[12][5]) ---
check_and_set = [
    # If V == QUERY_VAL, set flag = ONE
    # Compute V == Q: diff(WRAP(V), WRAP(Q)) is empty when equal
    inters(WRAP(UD(3)), WRAP(UD(8)), UD(11)),  # U[11] = WRAP(V) \ WRAP(Q)
    # Hmm, U[11] now has diff result. empty when equal.
    # We need to set flag only when equal.
    # Use conditional call: SET_FLAG_IF_ZERO ... but we don't have that.
    # 
    # Alternative: always set flag = flag ∪ (ONE if V==Q else ∅)
    # We can compute: flag = flag ∪ result_of_conditional
    # Where conditional: if V==Q → ONE else ∅
    # 
    # V==Q → XOR: diff(WRAP(V), WRAP(Q)) is empty
    # To get ONE when V==Q and ∅ when V≠Q:
    #   diff(WRAP(U[0]), WRAP(U[11])) → nonempty when U[11] != ZERO
    #   But U[11] is diff result (nonempty or empty).
    #   Actually: if diff(WRAP(V), WRAP(Q)) is empty → V==Q → we want ONE
    #   So: result = diff(ZERO, diff(WRAP(V), WRAP(Q)))
    #     = diff(WRAP(ZERO), WRAP(diff_result))
    #     = nonempty when diff_result != ZERO → V != Q → gives ONE when V != Q
    #   We want the OPPOSITE.
    #     
    #   Simpler: compute `inters(ONE, WRAP(CLEARED_C))` ... no.
    #
    #   Use the pattern from pred_advance:
    #   COND = diff(WRAP(UD(3)), WRAP(UD(8)))  # nonempty when V != Q
    #   flag = flag ∪ (COND is ∅ ? ONE : ∅)
    #
    #   Actually: flag = flag ∪ (ZERO if COND nonempty else ONE)
    #   Can compute: diff(WRAP(UD(0)), WRAP(COND)) → nonempty when COND != ZERO
    #     Wait, ZERO is non-empty.  We need ∅ (empty set) for comparison.
    #     We can get ∅ from C \ C.
    #
    #   Let me use a simpler approach: call a subroutine SET_FLAG only when V == Q.
    #   We check: if diff(WRAP(V), WRAP(Q)) empty → call SET_FLAG.
    #   We need "call if empty" which doesn't exist.
    #
    #   INVERT the condition: 
    #     COND = diff(WRAP(V), WRAP(Q))   (nonempty when V != Q)
    #     NOT_COND = diff(WRAP(ZERO), WRAP(COND))  (nonempty when V == Q)
    #     call SET_FLAG(cond=NOT_COND)
    #   
    #   ZERO = {{∅}} which is non-empty.  diff(WRAP(ZERO), WRAP(COND)) is:
    #     {ZERO} \ {COND} = {ZERO} if ZERO != COND, ∅ if ZERO == COND
    #     COND is either ∅ (empty) or some nonempty set.
    #     ZERO != ∅ and ZERO != any nonempty set (since ZERO = {{{∅}}})
    #     So diff(WRAP(ZERO), WRAP(COND)) is ALWAYS nonempty!  That doesn't help.
    #
    #   We need ∅ for comparison.  Let me use:
    #     NOT_COND = diff(C_C, WRAP(COND))  where C_C = C \ C = ∅
    #     diff(∅, WRAP(COND)) = ∅ \ {COND} = ∅ always (empty set minus anything = ∅)
    #     That doesn't work either.
    #
    #   diff(WRAP(COND), WRAP(∅)) = {COND} \ {∅} = nonempty if COND != ∅
    #   So this is nonempty when V != Q (same as COND itself).
    #
    #   We're going in circles.  Let me just ALWAYS set flag to ONE if
    #   V == Q, using a different mechanism.
    #
    #   OK here's the correct approach:
    #     1. Compute COND = diff(WRAP(V), WRAP(Q))  (nonempty when V != Q)
    #     2. Compute TOGGLE = diff(WRAP(ONE), WRAP(COND)) 
    #        {ONE} \ {COND} = ONE if COND != ONE, ∅ if COND == ONE
    #        But COND is either ∅ or some nonempty set, not necessarily ONE.
    #        diff(WRAP(ONE), WRAP(COND)) = ONE when COND != ONE, ∅ when COND == ONE
    #        Since COND is never ONE (it's either ∅ or another set):
    #        This is ALWAYS ONE.  Not useful.
    #
    #   I need a different approach.  Let me use:
    #     - Compute COND = diff(WRAP(V), WRAP(Q))
    #     - COND is empty if V==Q, nonempty if V!=Q
    #     - We want ONE when COND is empty, ∅ when COND is nonempty
    #     - We can use COND as a conditional guard for setting flag
    #     - Call a subroutine that sets flag, with cond = COND?
    #       subr_call(cond=COND) calls SET_FLAG when COND is nonempty.
    #       But we want to call when COND is EMPTY.
    #     - Invert: NOT_COND = flag = NOT(cond) 
    #       We can compute NOT_COND by checking if COND is empty.
    #       COND empty means COND == ∅ (the empty set from C\C).
    #       diff(WRAP(C_C), WRAP(COND)) where C_C = ∅:
    #         {∅} \ {COND} = ∅ if COND == ∅, {∅} if COND != ∅
    #         So this is NONEMPTY when COND is nonempty, EMPTY when COND is empty.
    #         That's the SAME as COND's behavior!  We're not inverting.
    #
    #   The issue: we can't invert in S5 without a NOT operation.
    #   We need to check "is COND empty?"  If yes → set flag.
    #
    #   We CAN check emptiness via the `subr_call(cond=COND)` pattern:
    #   if COND nonempty → call.  If empty → skip.
    #   For our case: we want to call SET_FLAG when COND is EMPTY.
    #   
    #   What if we use a COUNTER approach?  Instead of checking emptiness,
    #   ALWAYS call a helper that decides:
    #     HELPER:
    #       if COND is nonempty: return (don't set flag)
    #       else: flag = ONE
    #
    #   This is what I proposed earlier!  The helper checks COND and
    #   conditionally sets flag OR does nothing.
    #
    #   But COND check in S5 is `diff(WRAP(X), WRAP(Y))` — nonempty when X != Y.
    #   We can't check "is empty" without inverting.
    #
    #   Actually, we CAN!  In S5, the emptiness check is: 
    #     wrap the value, diff with itself:
    #     diff(WRAP(COND), WRAP(COND)) = ∅ regardless of COND
    #     That's not useful either.
    #
    #   What about using the COND as a SUBR_CALL condition?
    #     subr_call(cond=COND) → call only if COND nonempty
    #     If we have a subroutine DO_NOTHING and a subroutine SET_FLAG:
    #       We want: if COND nonempty → DO_NOTHING; if COND empty → SET_FLAG
    #       Can't directly express this.
    #
    #   But we CAN chain: call SET_FLAG conditionally on COND_REVERSED.
    #   To get COND_REVERSED:
    #     COND = diff(WRAP(V), WRAP(Q))
    #     COND_REV = diff(WRAP(C_C), WRAP(COND)) where C_C = ∅
    #     diff(WRAP(∅), WRAP(COND)) = {∅} \ {COND} = ∅ if COND==∅, {∅} if COND!=∅
    #     Wait, {COND} is WRAP(COND) = {COND}. And {∅} is WRAP(∅) = {∅}.
    #     diff({∅}, {COND}) = ∅ if {∅}=={COND} else {∅}.
    #     {∅} == {COND} means COND == ∅.
    #     So if COND == ∅: diff(WRAP(∅), WRAP(∅)) = ∅
    #     If COND != ∅: diff(WRAP(∅), WRAP(COND)) = {∅} (nonempty)
    #     So COND_REV = diff(WRAP(∅), WRAP(COND)) is nonempty when COND != ∅,
    #     and empty when COND == ∅.
    #     That's the SAME polarity as COND!  Not reversed.
    #
    #   Hmm.  I need:
    #     INV = diff(WRAP(ZERO), WRAP(COND))
    #     where ZERO = {{∅}} which is non-empty
    #     {ZERO} \ {COND} = {ZERO} if ZERO != COND, ∅ if ZERO == COND
    #     COND is either ∅ or some nonempty set.
    #     ZERO = {{∅}}.  Are ∅ and {{∅}} ever equal?  No.
    #     Is COND ever equal to {{∅}}?  COND can be ∅ or a SubroutineSet...
    #     Actually WRAP(COND) = {COND}.  And WRAP(ZERO) = {ZERO}.
    #     diff({ZERO}, {COND}) = {ZERO} \ {COND}
    #     If COND == ZERO, then diff({ZERO}, {ZERO}) = ∅.
    #     If COND != ZERO, then diff({ZERO}, {COND}) = {ZERO} (nonempty).
    #     COND would equal ZERO only when V == Q and the diff result equals ZERO.
    #     But diff(WRAP(V), WRAP(Q)) returns WRAP(V) \ WRAP(Q), which is either
    #     {V} (when V != Q) or ∅ (when V == Q).
    #     The result when V == Q is ∅ (empty set), not ZERO.
    #     So COND is never ZERO.
    #
    #   I think the fundamental issue is that we can't directly invert
    #   conditions in S5.  We need an alternative approach.
    #
    #   SIMPLEST SOLUTION: Instead of conditionally setting the flag,
    #   ALWAYS set flag = ONE, then when V passes MAX_VAL, check if
    #   flag was set AND V-1 == Q.  But this doesn't help either.
    #
    #   REAL SOLUTION: Track V == Q DURING THE LOOP using a SUBROUTINE
    #   that checks the condition.  The subroutine is ALWAYS called,
    #   and it decides internally whether to set flag.
    #
    #   The subroutine CHECK_AND_SET:
    #     1. Compute COND = diff(WRAP(V), WRAP(Q))
    #     2. COND is empty when V == Q (we want to set flag)
    #     3. Call SET_FLAG with cond = reversed condition
    #     
    #   To reverse: compute rev = diff(WRAP(C_C), WRAP(COND)) where C_C=∅
    #     WRAP(C_C) = {∅}
    #     WRAP(COND) = {COND}
    #     diff = {∅} \ {COND}
    #     If COND empty (V==Q): diff = {∅} \ {∅} = ∅
    #     If COND nonempty (V!=Q): diff = {∅} \ {COND} = {∅} (nonempty)
    #     
    #   Wait, that means rev is empty when COND empty and nonempty when COND nonempty.
    #   That's the SAME polarity, not reversed!
    #
    #   Let me re-check: {∅} \ {COND}
    #     - COND = ∅: {∅} \ {∅} = ∅ (because both sets contain ∅ as their single element)
    #     - COND = nonempty_X: {∅} \ {nonempty_X} = {∅} (since ∅ != nonempty_X)
    #   Yes, same polarity.
    #
    #   Hmm, what about: rev = diff(WRAP(COND), WRAP(C_C))?
    #     {COND} \ {∅}
    #     - COND = ∅: {∅} \ {∅} = ∅
    #     - COND = X (nonempty): {X} \ {∅} = {X} (nonempty)
    #   Same polarity again!
    #
    #   The issue: diff(WRAP(a), WRAP(b)) is empty when a==b, nonempty when a!=b.
    #   There's no way to "invert" this using only S5 operations because
    #   the empty/non-empty distinction can't be flipped without a NOT operation.
    #
    #   BUT: we can use the COND itself as the condition for a subroutine call.
    #   If we want to call when COND is EMPTY, we need a different approach.
    #
    #   IDEA: Use a COUNTER approach.
    #     - Start with a counter C = ONE (truthy meaning "not found")
    #     - When V passes MAX_VAL, if counter is still ONE, Q was not found
    #     - When V == Q, set counter = ∅ (found)
    #     
    #     To set counter = ∅: diff_(C(), C(), counter_slot)
    #     BUT we need to set counter = ∅ ONLY when V == Q.
    #
    #   What if we compute: counter = diff(WRAP(counter), WRAP(COND))?
    #     counter starts as ONE.
    #     When COND empty (V==Q): counter = diff({ONE}, {∅}) = {ONE} (nonempty) — NOT helpful
    #
    #   What about: flag = flag ∩ COND?
    #     flag starts as ONE (truthy).
    #     COND is nonempty (V!=Q): ONE ∩ nonempty_set = depends on intersection
    #       If sets are disjoint: ∅.  If overlapping: something nonempty.
    #     COND is empty (V==Q): ONE ∩ ∅ = ∅ (empty → falsy)
    #     Oh!  If flag = ONE ∩ COND, and COND is diff(WRAP(V), WRAP(Q)):
    #       - V != Q: COND nonempty, ONE ∩ COND = ??? depends on content
    #         ONE = {∅}.  COND = {V} (a set containing V).  
    #         {∅} ∩ {V}: ∅ != V for most V.  So intersection = ∅.
    #         This means flag becomes ∅ even when V != Q!  That's wrong.
    #
    #   What if: flag = ONE ∩ diff(WRAP(Q), WRAP(V))?
    #     Same issue: diff = {Q} \ {V} = nonempty for V != Q.
    #     ONE ∩ {Q}: empty for Q != ∅.
    #
    #   This won't work because intersection is about element equality, not set_value.
    #
    #   OK, I think the SIMPLEST approach is to track V == Q by UPDATING
    #   the flag EVERY iteration, not just when V == Q.
    #   
    #   The flag starts as ∅ (meaning "Q not yet found").
    #   At each iteration, we check if V == Q.
    #   If V == Q: flag = ONE (set).
    #   If V != Q: leave flag as is.
    #
    #   For "leave flag as is": we need to conditionally SET.
    #   The condition is V != Q (COND nonempty) → DON'T set (leave flag).
    #   
    #   We can ALWAYS set flag = ONE, but only when V == Q.
    #   Use: flag = flag ∪ diff(WRAP(ZERO), WRAP(COND))
    #     (but we showed this doesn't invert properly)
    #
    #   What about: flag = flag ∪ (COND is empty ? ONE : ∅)
    #     To compute "COND is empty → ONE, COND nonempty → ∅":
    #     We can compute: set_value(COND) is 0 when COND empty, >0 when nonempty.
    #     But we can't compute set_value in S5.
    #
    #   Let me try a COMPLETELY different approach.  Instead of tracking
    #   V == Q during the loop, compare AFTER the loop.
    #
    #   After the loop, we know MAX_VAL.  We know the LUT has entries
    #   for 0..MAX_VAL.  Check if QUERY_VAL <= MAX_VAL.
    #
    #   Instead of checking V == Q during LUT construction, just build
    #   the LUT, then COMPARE Q <= MAX_VAL using a comparison subroutine.
    #
    #   The comparison: iterate T from 0 upward:
    #     If T == Q before T == MAX_VAL: Q <= MAX_VAL
    #     If T == MAX_VAL before T == Q: Q > MAX_VAL
    #     (If Q == MAX_VAL, both happen at same time; use Q check)
    #
    #   Let me use this separation.
]

# Actually, let me rethink the whole flow.  The CHECK_AND_SET approach
# was getting too complex.  Let me separate:
#   1. Build LUT (no flag tracking)
#   2. Compare Q vs MAX_VAL by searching from 0
#   3. Dispatch based on comparison result

# --- DEMO_MAIN v2 ---
demo_main_v2 = [
    # Read MAX_VAL → U[4]
    inters(IO(), IO(), UD(4)),
    # Read QUERY_VAL → U[8]
    inters(IO(), IO(), UD(8)),
    
    # Precompute succ(MAX_VAL) → U[9]
    inters(UD(4), UD(4), UD(3)),      # IN_A = MAX_VAL
    inters(UD(6), UD(6), C()),        # C = U[6]
    subset(0),                         # C = C[0]
    subr_call(),                       # call succ
    inters(UD(5), UD(5), UD(9)),      # U[9] = succ(MAX_VAL)
    
    # V = 0 → U[3]
    inters(UD(0), UD(0), UD(3)),
    
    # Call BUILD_LOOP to construct LUT
    inters(UD(12), UD(12), C()),
    subset(1),
    subr_call(),
    
    # --- Compare Q vs MAX_VAL ---
    # T = 0 → U[11]
    inters(UD(0), UD(0), UD(11)),
    # Call COMPARE_LOOP
    inters(UD(12), UD(12), C()),
    subset(5),                         # C = C[5] = COMPARE_LOOP
    subr_call(),
    # After COMPARE_LOOP, U[10] = ∅ (use search) or ONE (use LUT)
    
    # Dispatch
    inters(UD(12), UD(12), C()),
    subset(2),                         # LUT_LOOKUP
    subr_call(cond=UD(10)),           # call only if flag set (Q <= MAX_VAL)
    
    # Fallthrough: SEARCH_PRED
    inters(UD(12), UD(12), C()),
    subset(3),
    subr_call(),
    
    # Output
    inters(UD(5), UD(5), C()),
    union(UD(0), WRAP(C()), IO()),
]


# --- BUILD_LOOP v2 ---
build_loop_v2 = [
    # Call pred_main
    inters(UD(7), UD(7), C()),
    subset(0),
    subr_call(),
    
    # Append pred(V) to U[7]
    inters(UD(5), UD(5), C()),        # C = pred(V)
    union(UD(7), WRAP(C()), UD(7)),
    
    # Increment V via succ
    inters(UD(3), UD(3), UD(3)),      # IN_A = V
    inters(UD(6), UD(6), C()),        # C = U[6]
    subset(0),
    subr_call(),
    inters(UD(5), UD(5), UD(3)),      # V = succ(V)
    
    # Check if V == succ(MAX_VAL)→ stop
    diff_(WRAP(UD(3)), WRAP(UD(9)), UD(11)),  # nonempty when V != MAX_VAL+1
    inters(UD(12), UD(12), C()),
    subset(1),
    subr_call(cond=UD(11)),
]


# --- COMPARE_LOOP (U[12][5]) ---
# T starts at 0 in U[11].  Compare T vs Q and T vs MAX_VAL.
# If T == Q: set flag U[10] = ONE, return (Q <= MAX_VAL)
# If T == MAX_VAL (and T != Q): return with flag still ∅ (Q > MAX_VAL)
# Else: T = succ(T), recurse
compare_loop = [
    # Check T == Q
    diff_(WRAP(UD(11)), WRAP(UD(8)), UD(10)),  # U[10] = diff(WRAP(T), WRAP(Q))
    # If U[10] empty: T == Q → set flag = ONE and return
    inters(UD(12), UD(12), C()),
    subset(6),                          # C = C[6] = SET_FLAG_IF_EQ
    subr_call(cond=UD(10)),            # call only if T != Q
    
    # Check if flag was set: if U[10] is ONE, return
    # We can check: diff(WRAP(U[10]), WRAP(ONE)) — empty when flag == ONE
    # But we can't conditionally return based on this.
    # 
    # Instead: check T == MAX_VAL (and by this point, T != Q was verified above:
    #   if T == Q, SET_FLAG set U[10]=ONE, but we DON'T stop here;
    #   execution continues to the MAX_VAL check)
    #
    # Actually, we need to STOP when flag is set.
    # Use: if flag set → don't continue (don't call COMPARE_LOOP again)
    # 
    # We can use a "skip" approach:
    #   diff_(WRAP(UD(10)), WRAP(UD(1)), UD(11))  # empty when flag == ONE
    #   call COMPARE_LOOP(cond=UD(11)) — called only when flag != ONE
    
    # Check T == MAX_VAL
    diff_(WRAP(UD(11)), WRAP(UD(4)), UD(10)),  # U[10] = diff(T, MAX_VAL)
    # Wait, this overwrites U[10] which might have the flag!
    # Use U[1] (ONE) as scratch? No, ONE is precious.
    
    # Let me restructure: use separate slots for flags and scratch.
    # U[10] = flag (∅ or ONE)
    # U[1]  = ONE (preserved)
    # U[0]  = ZERO (preserved)
    # U[11] = scratch
    
    # Check T == MAX_VAL
    diff_(WRAP(UD(11)), WRAP(UD(4)), UD(11)),  # scratch = diff(T, MAX_VAL)
    # scratch empty when T == MAX_VAL
    # scratch nonempty when T != MAX_VAL and T != Q
    # (since T == Q case was handled above by checking flag)
    
    # Use scratch as condition to continue:
    inters(UD(12), UD(12), C()),
    subset(5),                          # COMPARE_LOOP
    subr_call(cond=UD(11)),            # call only if T != MAX_VAL
    
    # If we reach here: T == MAX_VAL without T == Q → Q > MAX_VAL
    # U[10] should still be ∅ (was set to ∅ before loop started)
    # Actually, COMPARE_LOOP is called from DEMO_MAIN where U[10] was not initialized!
    # Let me fix: initialize U[10] = ∅ before calling COMPARE_LOOP.
    # And inside COMPARE_LOOP:
    #   If T == Q: U[10] = ONE; ... hmm but we can't stop
]


# OK I'm going in circles.  Let me use a different pattern.
# The issue is that S5 can't do "break" or "return early" from a subroutine.
# The subroutine body is a flat sequence; instructions at the end always run.

# NEW APPROACH: Use NESTED subroutines for the branching.

# COMPARE_LOOP:
#   Check T == Q:
#     CONDeqQ = diff(WRAP(T), WRAP(Q))  # empty when T == Q
#     If NOT CONDeqQ (is empty): 
#       U[10] = ONE (flag set)
#       CALL SET_FLAG_SUB which sets flag and DOES NOT call COMPARE_AGAIN
#     If CONDeqQ (nonempty): 
#       Check T == MAX_VAL
#         COND = diff(WRAP(T), WRAP(M))  # empty when T == M
#         If NOT COND (is empty): return (Q > MAX_VAL, U[10] still ∅)
#         If COND (nonempty): T = succ(T), call COMPARE_LOOP again

# We need TWO levels of conditionals.
# U[12][5] = COMPARE_LOOP: called by DEMO_MAIN
#   - Always calls COMPARE_CHECK
# U[12][6] = COMPARE_CHECK: 
#   - Checks T == Q, if so: sets flag, returns
#   - Checks T == M, if so: returns
#   - Otherwise: T = succ(T), calls COMPARE_LOOP

# Let me redo:

# DEMO_MAIN v3:
demo_main_v3 = [
    # Read inputs
    inters(IO(), IO(), UD(4)),        # MAX_VAL
    inters(IO(), IO(), UD(8)),        # QUERY_VAL
    
    # Precompute succ(MAX_VAL) → U[9]
    inters(UD(4), UD(4), UD(3)),
    inters(UD(6), UD(6), C()),
    subset(0),
    subr_call(),
    inters(UD(5), UD(5), UD(9)),
    
    # V = 0 → U[3]
    inters(UD(0), UD(0), UD(3)),
    
    # Call BUILD_LOOP
    inters(UD(12), UD(12), C()),
    subset(1),
    subr_call(),
    
    # Compare: T = U[11] = 0, flag = U[10] = ∅
    inters(UD(0), UD(0), UD(11)),     # U[11] = ZERO
    diff_(C(), C(), UD(10)),          # U[10] = ∅
    
    inters(UD(12), UD(12), C()),
    subset(5),                         # COMPARE_LOOP
    subr_call(),
    
    # After compare: U[10] is ONE (Q in range) or ∅ (Q not in range)
    inters(UD(12), UD(12), C()),
    subset(2),
    subr_call(cond=UD(10)),
    
    # Fallthrough
    inters(UD(12), UD(12), C()),
    subset(3),
    subr_call(),
    
    # Output
    inters(UD(5), UD(5), C()),
    union(UD(0), WRAP(C()), IO()),
]

# COMPARE_LOOP (U[12][5]):
#   T in U[11], flag in U[10]
#   Check T == Q:
#     diff(WRAP(U[11]), WRAP(U[8])) → scratch (empty when T == Q)
#     If scratch empty: set flag = ONE, return (no more recursion)
#   Check T == MAX_VAL:
#     diff(WRAP(U[11]), WRAP(U[4])) → scratch (empty when T == MAX_VAL)
#     If scratch empty: return (flag stays ∅ → search path)
#   T = succ(T), recurse
#
# We implement the "check and branch" using:
#   - Call CHECK_T_EQ_Q with cond = NOT_eqQ (but we can't invert!)
#   - Use a different structure:
#     1. Set up both conditions
#     2. Use COND as guard for calls

# Actually, we can implement CHECK_T_EQ_Q as a subroutine that
# checks if scratch (the eqQ result) is empty, and only sets
# flag if so.  But the subroutine can't check emptiness either!

# Let me try a VERY different approach:
# Don't set flag during comparison.  Instead, use the search-based
# pred call as a SUBROUTINE that the LUT_PATH also calls.

# FLOW:
#   After building LUT:
#   a. Try LUT path with index 3+Q
#   b. If SUBSET_SELECT succeeds: result in C, done
#   c. If fails (out of bounds): use search pred

# But we can't catch failures in S5!

# ALTERNATIVE: Pad U[7] to be large enough that SUBSET_SELECT
# never fails.  For indices beyond the actual LUT, return ∅.
# Then check if the result is ∅ (empty set):
#   If ∅: Q > MAX_VAL → use search pred
#   If nonempty: Q <= MAX_VAL → use LUT result

# But we can't add padding entries that are ∅ (empty) because
# U[7] is a SubroutineSet.  ∅ would be a faulty element.

# Actually, we CAN add padding as long as it doesn't break things.
# The padding entries are just unused elements.

# OK I think the CLEANEST approach is the COMPARE_LOOP pattern.
# Let me implement it properly.

# COMPARE_LOOP (U[12][5]):
compare_loop_v2 = [
    # Check T == Q
    diff_(WRAP(UD(11)), WRAP(UD(8)), UD(10)),  # scratch = diff(T, Q)
    # scratch empty when T == Q
    
    # We need: if scratch empty → set flag and STOP
    # We can call SET_FLAG with a REVERSED condition.
    # To reverse: rev = diff(C_C, WRAP(scratch)) = diff(∅, {scratch}) = ∅ (always!)
    # That doesn't work.
    #
    # Cleaner: call CHECK_T_EQ_Q as a nested subroutine that NEVER returns
    # (halts) when T == Q.
    # CHECK_T_EQ_Q: {
    #   if diff(T, Q) empty → set flag, RETURN
    #   else → DIE (halt)
    # }
    # But how to die?  Halt = U = ∅.
    # If T == Q: flag = ONE, return.
    # If T != Q: halt (error)!
    # No, that's backwards.
    #
    # What if CHECK_T_EQ_Q is an INNER subroutine?
    #
    # Actually, let me use a DIFFERENT approach entirely.
    # Use a single multi-check subroutine:
    
    # Compute COND_T_EQ_Q = diff(WRAP(T), WRAP(Q))
    # Compute COND_T_EQ_M = diff(WRAP(T), WRAP(M))
    
    # IDEA: Use union to combine conditions.
    # COND_CONTINUE = COND_T_EQ_Q ∪ COND_T_EQ_M
    # (COND_T_EQ_Q is empty when T==Q; COND_T_EQ_M empty when T==M)
    # When both are nonempty (T != Q AND T != M): both nonempty → union nonempty
    # When one is empty (T==Q or T==M): union is the other
    # When both empty (T==Q==M): union is empty
    #
    # If COND_CONTINUE is nonempty: T != Q AND T != M → continue looping
    # If COND_CONTINUE is empty: T == Q OR T == M → need to check which
    #
    # But we can't distinguish T==Q from T==M using just COND_CONTINUE.
    
    # Better approach: check each condition separately via CALLS.
    
    # Subroutine CHECK_EQ_Q (U[12][6]): if T == Q, set flag = ONE, DONE
    #   Check: diff(WRAP(T), WRAP(Q)) → scratch
    #   If scratch nonempty: return (T != Q, nothing to do)
    #   If scratch empty: flag = ONE
    #   Question: how to check if scratch is empty?
    #   
    #   Could use a SECOND subroutine that's called with cond=scratch:
    #     If scratch nonempty → called → does nothing
    #     If scratch empty → not called → fall through to SET_FLAG
    #
    #   WAIT.  If scratch nonempty → call SUB1 (does nothing, returns)
    #   If scratch empty → skip SUB1 → fall through → flag = ONE
    # 
    #   YES!  That's the pattern!
    #
    #   COMPARE_LOOP:
    #     diff(WRAP(T), WRAP(Q)) → scratch
    #     call SUB_NOOP(cond=scratch)  # called only if T != Q
    #     # If we're here and scratch was empty (T==Q): set flag
    #     # But we don't know if we came from the call or the skip!
    #     inters(UD(1), UD(1), UD(10))  # flag = ONE (always!)
    #     return  # Then COMPARE_LOOP caller continues
    #
    #   Problem: even when T != Q, we fall through AND set flag!
    #   We'd set flag even when T != Q.
    #
    #   Need to NOT set flag when T != Q.
    #   The call SUB_NOOP consumes an instruction slot.
    #   After it returns/falls through, we still reach flag=ONE.
    
    # Hmm.  What if SUB_NOOP HALTS instead of returning?
    #   SUB_NOOP: diff_(C(), C(), UD(0))  # U = C \ C = ∅ → halts
    #   
    #   Then:
    #     diff(WRAP(T), WRAP(Q)) → scratch
    #     call SUB_HALT(cond=scratch)  # if T != Q: call → halts (wrong!)
    #     # Only reach here if scratch empty (T == Q)
    #     inters(UD(1), UD(1), UD(10))  # flag = ONE (correct now)
    #     return
    
    # Wait, that's backwards again!  If T != Q: call SUB_HALT → program halts.
    # We only want to halt when T == Q?  No...
    
    # OK let me think about this ONE MORE TIME.
    # We want:
    #   IF T == Q: set flag, stop comparing (return to main)
    #   IF T == M: stop comparing (return to main)
    #   ELSE: T = succ(T), recurse
    
    # The problem is checking "IS EMPTY" vs "IS NONEMPTY".
    # S5 can only conditionally CALL when condition is NONEMPTY.
    
    # Here's a trick:
    #   To check "is X empty?": 
    #     Compute diff(WRAP(T), WRAP(T)) = ∅ (always empty)
    #     This doesn't help.
    #   
    #   To check "is X nonempty?": Use X directly as a condition.
    #
    #   So we can only check "is X nonempty" natively.
    #
    # For T == Q: diff(WRAP(T), WRAP(Q)) is EMPTY.
    #   We need to detect emptiness.  We can use:
    #     NOT_EMPTY = diff(WRAP(ONE), WRAP(X))
    #     where X = diff(WRAP(T), WRAP(Q))
    #     If X empty: {ONE} \ {∅} = {ONE} (nonempty!)
    #     If X nonempty: {ONE} \ {X} = depends on whether ONE == X
    #       X could be {T} (a set containing V, value some integer)
    #       ONE = {∅}.  
    #       {ONE} ∩ {X} = ∅ (they're different singleton sets)
    #       So diff = {ONE} (nonempty)
    #     Result: ALWAYS nonempty regardless.  Doesn't work.
    
    # What about: diff(WRAP(X), WRAP(ONE))?
    #   If X empty: {∅} \ {ONE} ... ∅ ≠ ONE → {∅} (nonempty)
    #   If X nonempty: depends on whether X == ONE
    #     Unlikely.  Result = {X} (nonempty)
    #   Always nonempty.  Doesn't work.
    
    # I think the CORRECT approach is:
    #   Use a subroutine that checks EQUALITY and branches based on
    #   it.  Since we can't directly invert, we use a double call:
    
    #   call FIRST_CHECK(cond=COND_T_NE_Q)  # called when T != Q
    #     In FIRST_CHECK: nothing, just return (T != Q, continue)
    #   # If COND_T_NE_Q was nonempty, we JUST returned from FIRST_CHECK.
    #   # If COND_T_NE_Q was empty, we SKIPPED FIRST_CHECK.
    #   # In either case, execution continues here.
    #   # We need to know which case we're in.
    #   # 
    #   # TRICK: FIRST_CHECK can MODIFY a scratch variable to signal.
    #   # FIRST_CHECK: scratch = ONE (signal "T != Q case")
    #   # After the call: if scratch == ONE → T != Q; if scratch == ∅ → T == Q
    #   # But scratch was set to 1 only when COND was nonempty (T != Q).
    #   # If scratch is ∅ after the call → T == Q.
    
    # YES!  This works.
    
    # scratch starts as ∅
    # if T != Q: call FIRST_CHECK which sets scratch=ONE
    # if T == Q: skip FIRST_CHECK, scratch stays ∅
    # After: if scratch is ONE → T != Q; if ∅ → T == Q
    
    # To check scratch == ONE vs ∅:
    #   diff(WRAP(scratch), WRAP(ONE)) → empty when scratch == ONE
    #   Call SET_FLAG with cond = REVERSE (empty check) we still have the same problem!
    
    # Ugh.  We can check "scratch != ONE" with diff(WRAP(scratch), WRAP(ONE))
    # which is nonempty when scratch != ONE.  But we need to check
    # "scratch == ONE" which is the empty case.
    
    # Actually, for the check "if scratch == ONE → flag = ONE":
    #   diff(WRAP(scratch), WRAP(ONE)) is empty when scratch == ONE.
    #   We can call a subroutine with cond = this diff.
    #   But it's called when diff is nonempty (scratch != ONE)!
    #   Scratch is ONE when T != Q.  So we call subroutine when T == Q?
    #   
    # Hmm:
    #   scratch starts ∅
    #   call FIRST_CHECK(cond=diff(T,Q)) → called when T != Q → sets scratch=ONE
    #   Now: scratch=ONE when T!=Q, scratch=∅ when T==Q
    #   
    #   diff(WRAP(scratch), WRAP(ONE)):
    #     When T != Q (scratch=ONE): diff({ONE}, {ONE}) = ∅
    #     When T == Q (scratch=∅): diff({∅}, {ONE}) = {∅} (nonempty)
    #   
    #   Call SET_FLAG(cond=diff(WRAP(scratch), WRAP(ONE))):
    #     Called when T == Q (diff nonempty) → sets flag = ONE ✓
    #     NOT called when T != Q (diff empty) → flag stays ∅ ✓
    
    # YES!  This works!  The trick is to invert the condition by
    # using the FIRST_CHECK signal.
    
    # Let me design the subroutines:
    
    # COMPARE_LOOP (U[12][5]):
    #   1. Check T == Q
    #   scratch = diff(WRAP(T), WRAP(Q))  # nonempty when T != Q
    #   call FIRST_CHECK(cond=scratch)     # called when T != Q
    #     FIRST_CHECK: scratch = ONE (signal)
    #   # After: scratch is ONE if T!=Q, ∅ if T==Q
    #   flag_cond = diff(WRAP(scratch), WRAP(ONE))  # nonempty when scratch != ONE (T==Q)
    #   call SET_FLAG(cond=flag_cond)  # called when T==Q → flag = ONE
    #   # SET_FLAG must RETURN (not halt) so we reach the NEXT check
    #   # Actually, when T==Q, we should STOP (return from COMPARE_LOOP)
    #   # We can make SET_FLAG halt: U = C\C
    #   # But then execution stops entirely!
    #   # Instead, use a FLAG that the caller checks.
    #   # flag was set to ONE by SET_FLAG.
    #   # After SET_FLAG returns, we still continue to the T==M check.
    #   # We need to SKIP the rest when flag is set.
    #   
    #   2. Check T == M (only if not already T==Q)
    #   Since we can't conditionally skip in S5, we must check at the END
    #   whether to continue the loop.
    #   
    #   3. T = succ(T), recurse (unless T==Q or T==M)
    
    # Let me use a different approach.  COMPARE_LOOP will check TWO things:
    #   A. T == Q → set flag = ONE, DON'T continue (don't recurse)
    #   B. T == M → DON'T continue (don't recurse)
    #   C. Otherwise → continue
    
    # For A: use the scratch trick above.
    #   scratch = diff(WRAP(T), WRAP(Q))
    #   call MARK(cond=scratch) → called when T!=Q → scratch = ONE
    #   flag_cond = diff(WRAP(scratch), WRAP(ONE)) → nonempty when T==Q
    #   call SET_FLAG_AND_HALT(cond=flag_cond) → called when T==Q → sets flag, halts
    #   Hmm, but halting stops the whole program, not just the loop.
    #   
    #   We need to RETURN from COMPARE_LOOP when T==Q, not halt.
    #   But S5 subroutines just return when they finish executing.
    #   There's no early return.
    #   
    #   TRICK: Use nested subroutines!
    #   COMPARE_LOOP calls CHECK_T_EQ_Q which:
    #     If T == Q: sets flag, calls NOTHING (return from CHECK_T_EQ_Q)
    #     If T != Q: calls CONTINUE_CHECK
    #   After CHECK_T_EQ_Q returns, COMPARE_LOOP continues.
    #   But flag is now set.
    #   
    #   Then COMPARE_LOOP checks T == M:
    #     If T == M: call NOTHING (return)
    #     If T != M: succ(T), recurse
    #   
    #   The problem is: after T==Q and flag is set, COMPARE_LOOP
    #   still runs the T==M check!  If Q == M, both fire.
    #   But that's OK because flag was already set.
    #   
    #   The issue: even when T==Q, COMPARE_LOOP continues to the
    #   "T = succ(T), recurse" part.  We DON'T want that.
    #   
    #   To prevent recursion when T==Q or T==M:
    #     After both checks, compute:
    #       continue_cond = diff(WRAP(T), WRAP(Q))
    #       If nonempty (T!=Q): check T==M
    #         If T!=Q AND T!=M: call COMPARE_LOOP again
    #     This requires NESTED checks.
    #
    #     OR: at the end, just call COMPARE_LOOP with cond=continue_flag
    #     where continue_flag is computed to be empty when T==Q or T==M.
    #
    #     continue = diff(WRAP(succ(T)), WRAP(succ(Q))) ∩ diff(WRAP(T), WRAP(M))
    #     Hmm, this is getting complex.
    #
    #     Actually: we WANT to continue when T != Q AND T != M.
    #     COND1 = diff(WRAP(T), WRAP(Q)) — nonempty when T != Q
    #     COND2 = diff(WRAP(T), WRAP(M)) — nonempty when T != M
    #     The COND for continuing is COND1 ∩ COND2 (both nonempty)
    #     If COND1∩COND2 nonempty: continue (recurse)
    #     If empty: stop (no recursion)
    #
    #     YES!  If either is empty, the intersection is empty → stop.
    #     If both nonempty, intersection is... wait, intersection checks
    #     for equal elements, not boolean AND.
    #     COND1 and COND2 are both singleton sets: {T} (different from each other
    #     since Q != M).  Intersection of {T} from COND1 and {T} from COND2?
    #     Actually COND1 = {T} \ {Q} = {T} (singleton)
    #     And COND2 = {T} \ {M} = {T} (singleton)
    #     Intersection of {T} and {T} = {T} (nonempty).
    #     But if COND1 is empty (T==Q): intersection of ∅ and {T} = ∅ → stop ✓
    #     If COND2 is empty (T==M): intersection of {T} and ∅ = ∅ → stop ✓
    #
    #     Wait, COND1 is computed as diff(WRAP(T), WRAP(Q)):
    #     When T != Q: diff = {T} \ {Q} = {T} (a singleton containing T)
    #     When T == Q: diff = {T} \ {T} = ∅
    #     So COND1 is either {T} (nonempty) or ∅ (empty).
    #
    #     COND2 = diff(WRAP(T), WRAP(M)) is similar.
    #
    #     Intersection: COND1 ∩ COND2
    #     COND1 is {T} (when T!=Q) or ∅ (when T==Q)
    #     COND2 is {T} (when T!=M) or ∅ (when T==M)
    #     When T != Q AND T != M: {T} ∩ {T} = {T} (nonempty) → continue ✓
    #     When T == Q OR T == M: ∅ ∩ anything = ∅ → stop ✓
    #
    #     But wait, COND1's {T} — is {T} actually {WRAP(T)} = {{T}}?  No.
    #     diff(WRAP(T), WRAP(Q)) returns WRAP(T) \ WRAP(Q) = {T} \ {Q}.
    #     If T != Q: {T} \ {Q} = {T} (a set whose sole element is T).
    #     And COND2 similarly is {T} when T != M.
    #     Intersection of {T} and {T}: both contain T → {T} (nonempty).  ✓
    #
    #     So the continue condition is: COND1 ∩ COND2 = nonempty → recurse
    #
    #   This works!  Let me implement it.
    
    # Scratch U[11] = T (loop variable)
    # U[10] = flag
    
    # COND1 = diff(WRAP(T), WRAP(Q))
    diff_(WRAP(UD(11)), WRAP(UD(8)), UD(10)),  # U[10] = diff(WRAP(T), WRAP(Q))
    # Actually I need TWO scratch slots.  Let me use:
    #   U[10] = COND1  (diff(T,Q))
    #   U[11] = T      (preserve)
    #   U[12] is the subroutines slot (can't use for scratch)
    #   U[13] = scratch (available)
    #   
    # Let me reassign slots:
    #   U[3]  = V (loop variable during LUT build)
    #   U[4]  = MAX_VAL
    #   U[5]  = OUT
    #   U[8]  = QUERY_VAL
    #   U[9]  = succ(MAX_VAL)
    #   U[10] = flag (∅ or ONE)
    #   U[11] = T (compare loop variable)
    #   U[12] = DEMO subroutines
    #   U[13] = scratch1
    #   U[14] = scratch2
    #   U[20+] = byte values
]


# TIME TO ADMIT: writing S5 code by hand is error-prone.
# Let me take a step back and write the code MORE CAREFULLY,
# using Python dataclasses to help structure it.

# NEW STRATEGY: I'll embed the comparison logic as follows:
#
# After LUT is built:
#   1. T = 0
#   2. flag = ∅
#   3. loop:
#      a. if T == Q: flag = ONE; break
#      b. if T == MAX_VAL: break  
#      c. T = succ(T); goto loop
#   4. if flag nonempty: LUT path; else: search path
#
# Steps 3a and 3b use the COND1∩COND2 trick:
#   continue_flag = diff(WRAP(T), WRAP(Q)) ∩ diff(WRAP(T), WRAP(M))
#   If continue_flag nonempty: recurse
#   Else: stop (either T==Q or T==M)
#
# The flag is set by a CHECK_T_EQ_Q subroutine called at the START of each
# iteration:
#   Check T==Q: diff(WRAP(T), WRAP(Q)) → scratch
#   If scratch nonempty (T!=Q): call MARKER → sets marker
#   After: if marker == ONE (T!=Q): no action
#          if marker == ∅ (T==Q): flag = ONE
#   
# Actually simpler: ALWAYS call a subroutine CHECK_AND_SET_FLAG that:
#   1. Check T == Q: if so, set flag = ONE
#   How? Use the double-call trick:
#     marker = ∅
#     scratch = diff(WRAP(T), WRAP(Q))  # nonempty when T!=Q
#     call SET_MARKER(cond=scratch)      # called when T!=Q → marker = ONE
#     # Now: marker=ONE when T!=Q, marker=∅ when T==Q
#     # We want flag=ONE when marker=∅ (T==Q)
#     flag_cond = diff(WRAP(marker), WRAP(ONE))  # nonempty when marker!=ONE → T==Q
#     call SET_FLAG(cond=flag_cond)  # called when T==Q → flag = ONE
#
# COMPARE_LOOP body:
#   call CHECK_AND_SET_FLAG (U[12][6]) → may set flag
#   scratch1 = diff(WRAP(T), WRAP(Q))  # nonempty when T!=Q
#   scratch2 = diff(WRAP(T), WRAP(M))  # nonempty when T!=M
#   continue_cond = ???  # nonempty only when BOTH are nonempty
#   # Intersection: need to intersect scratch1 and scratch2
#   # But intersection returns elements in COMMON, not boolean AND.
#   # scratch1 = {T} when T!=Q, or ∅ when T==Q
#   # scratch2 = {T} when T!=M, or ∅ when T==M
#   # intersection of {T} and {T} = {T} (nonempty) → continue
#   # intersection of ∅ and anything = ∅ → stop
#   # This works!
#   inters(UD(14), UD(14), UD(14))... 
#   Hmm, I need scratch slots for the intersection result.
#   Let me use U[13] for scratch1, U[14] for scratch2.
#   inters(UD(13), UD(14), UD(13))  # U[13] = scratch1 ∩ scratch2 → continue_cond
#   Then: call COMPARE_LOOP(cond=UD(13))
#   But wait, this computes intersection IN-PLACE, clobbering scratch1.
#   That's fine since we don't need scratch1 afterward.
#
#   But the intersection of two singleton {T} sets gives {T} when T is in both.
#   When T != Q AND T != M: scratch1={T}, scratch2={T} → intersection={T} ✓
#   When T == Q: scratch1=∅ → intersection=∅ → stop ✓
#   When T == M: scratch2=∅ → intersection=∅ → stop ✓
#   When T == Q == M: both ∅ → intersection=∅ → stop ✓


# Let me redesign COMPARE_LOOP properly.

# U[11] = T
# U[13] = scratch (COND1)
# U[14] = scratch (COND2)

compare_loop_v3 = [
    # Step 1: CHECK_AND_SET_FLAG (U[12][6])
    #   (We'll define it below as a subroutine)
    inters(UD(12), UD(12), C()),
    subset(6),
    subr_call(),
    
    # Step 2: Compute continue condition
    diff_(WRAP(UD(11)), WRAP(UD(8)), UD(13)),  # COND1 = diff(T, Q)
    diff_(WRAP(UD(11)), WRAP(UD(4)), UD(14)),  # COND2 = diff(T, M)
    # continue_cond NEEDS to be COND1 ∩ COND2 (both nonempty)
    # BUT: COND1 and COND2 are WRAP results (singleton sets or ∅)
    # Their intersection checks ELEMENT equality, not boolean AND.
    # Since both are either {T} or ∅, their intersection IS {T} iff both are {T}.
    # This is equivalent to boolean AND for our case!
    inters(UD(13), UD(14), UD(13)),             # U[13] = COND1 ∩ COND2
    
    # Step 3: If continue, T = succ(T) and recurse
    # Copy T to IN_A for succ call
    inters(UD(11), UD(11), UD(3)),             # IN_A = T
    inters(UD(6), UD(6), C()),                 # C = U[6]
    subset(0),                                   # C = C[0]
    subr_call(),                                 # call succ
    inters(UD(5), UD(5), UD(11)),              # T = succ(T)
    
    # Recurse
    inters(UD(12), UD(12), C()),
    subset(5),                                   # COMPARE_LOOP
    subr_call(cond=UD(13)),                     # call if continue_cond nonempty
]

# CHECK_AND_SET_FLAG (U[12][6]):
#   Uses the double-call trick:
#     marker = ∅
#     scratch = diff(WRAP(T), WRAP(Q))  # nonempty when T!=Q
#     call SET_MARKER(cond=scratch)      # called when T!=Q → marker = ONE
#     flag_cond = diff(WRAP(marker), WRAP(ONE))  # nonempty when marker!=ONE (T==Q)
#     call SET_FLAG(cond=flag_cond)      # called when T==Q → flag = ONE
#
# But SET_MARKER and SET_FLAG need to be subroutines too.
# This is getting too many subroutines.

# SIMPLIFICATION: combine the double-call trick inline.
# CHECK_AND_SET_FLAG body:
#   1. marker = ∅ (scratch register U[14])
#   2. scratch = diff(WRAP(T), WRAP(Q)) → U[13]
#   3. call SET_MARKER(cond=U[13])  # called when T!=Q → U[14] = ONE
#   4. flag_cond = diff(WRAP(scratch), WRAP(ONE))  # HMM
#   
#   After step 3:
#     If T!=Q: SET_MARKER was called, U[14] = ONE
#     If T==Q: SET_MARKER skipped, U[14] = ∅
#   flag_cond = diff(WRAP(U[14]), WRAP(ONE))
#     If T!=Q: diff(WRAP(ONE), WRAP(ONE)) = ∅
#     If T==Q: diff(WRAP(∅), WRAP(ONE)) = {∅} (nonempty)
#   call SET_FLAG(cond=flag_cond)  # called when T==Q → U[10] = ONE

#   SET_MARKER: U[14] = ONE (just inters(ONE,ONE,U[14]))
#   SET_FLAG: U[10] = ONE (just inters(ONE,ONE,U[10]))

check_and_set_flag = [
    # Clear marker
    diff_(C(), C(), UD(14)),          # U[14] = ∅ (C\C)
    
    # Compute T != Q
    diff_(WRAP(UD(11)), WRAP(UD(8)), UD(13)),  # U[13] = diff(T, Q)
    
    # Call SET_MARKER if T != Q
    inters(UD(12), UD(12), C()),      # C = U[12]
    subset(7),                          # C = C[7] = SET_MARKER
    subr_call(cond=UD(13)),            # called only when T != Q
    
    # Compute flag_cond: nonempty when marker != ONE → T == Q
    diff_(WRAP(UD(14)), WRAP(UD(1)), UD(13)),  # U[13] = diff(marker, ONE)
    
    # Call SET_FLAG if T == Q
    inters(UD(12), UD(12), C()),
    subset(8),                          # C = C[8] = SET_FLAG
    subr_call(cond=UD(13)),            # called only when marker != ONE (T==Q)
]

# SET_MARKER (U[12][7]):
set_marker = [
    inters(UD(1), UD(1), UD(14)),     # U[14] = ONE
]

# SET_FLAG (U[12][8]):
set_flag = [
    inters(UD(1), UD(1), UD(10)),     # U[10] = ONE
]


# --- LUT_LOOKUP (U[12][2]) ---
# Build SUBSET_SELECT for index = 3 + Q in buffer, execute, halt.
# After execution, result is in C.  Copy to U[5] and halt.

lut_lookup = [
    # INDEX = 3 + QUERY_VAL
    # succ(succ(succ(Q))) = Q + 3
    # First succ
    inters(UD(8), UD(8), UD(3)),       # IN_A = Q
    inters(UD(6), UD(6), C()),         # C = U[6]
    subset(0),                          # C = C[0]
    subr_call(),                        # call succ
    inters(UD(5), UD(5), UD(3)),       # IN_A = succ(Q)
    # Second succ
    inters(UD(6), UD(6), C()),
    subset(0),
    subr_call(),
    inters(UD(5), UD(5), UD(3)),       # IN_A = succ(succ(Q))
    # Third succ
    inters(UD(6), UD(6), C()),
    subset(0),
    subr_call(),
    # Now U[5] = OUT = succ(succ(succ(Q))) = 3+Q = INDEX
    inters(UD(5), UD(5), UD(11)),      # U[11] = INDEX (store in scratch)
    
    # --- Build S5B bytes in buffer ---
    # Fixed part 1: C = U[7]
    # For each byte in fixed_c_eq_u7, write via IO_BYTE'1
]
for byte_val in fixed_c_eq_u7:
    lut_lookup.append(inters(UD(byte_slot[byte_val]), UD(byte_slot[byte_val]), C()))
    lut_lookup.append(union(UD(0), WRAP(C()), IO_BYTE()))

# SUBSET_SELECT prefix
for byte_val in fixed_subset_prefix:
    lut_lookup.append(inters(UD(byte_slot[byte_val]), UD(byte_slot[byte_val]), C()))
    lut_lookup.append(union(UD(0), WRAP(C()), IO_BYTE()))

# Integer encoding: degenerate unary for INDEX = U[11]
#   Write 0x9a baseline
lut_lookup.append(inters(UD(byte_slot[0x9a]), UD(byte_slot[0x9a]), C()))
lut_lookup.append(union(UD(0), WRAP(C()), IO_BYTE()))
#   rem = INDEX - 1
# Copy INDEX to IN_A for pred call
lut_lookup.append(inters(UD(11), UD(11), UD(3)))  # IN_A = INDEX
lut_lookup.append(inters(UD(7), UD(7), C()))       # C = U[7]
lut_lookup.append(subset(0))                         # C = C[0] = PRED_MAIN
lut_lookup.append(subr_call())                       # call pred → U[5] = OUT = pred(INDEX)
lut_lookup.append(inters(UD(5), UD(5), UD(13)))     # U[13] = rem = pred(INDEX) = INDEX-1
#   Call ENCODE_DECR (U[12][4]) with rem in U[13]
lut_lookup.append(inters(UD(12), UD(12), C()))
lut_lookup.append(subset(4))                          # C = C[4] = ENCODE_DECR
lut_lookup.append(subr_call())

# Fixed part 2: U[5] = C
for byte_val in fixed_u5_eq_c:
    lut_lookup.append(inters(UD(byte_slot[byte_val]), UD(byte_slot[byte_val]), C()))
    lut_lookup.append(union(UD(0), WRAP(C()), IO_BYTE()))

# --- Read buffer via IO_S5B'1 → get executable SubroutineSet ---
# Trigger via DIFFERENCE a=U[7] b=IO_S5B'1 dest=U[8] (trash)
# This auto-executes the body: C = U[7]; C = C[INDEX]; U[5] = C
lut_lookup.append(diff_(UD(7), IO_S5B(), UD(8)))

# Copy result from U[5] to... it's already in U[5] from the auto-exec body
# Halt
lut_lookup.append(diff_(C(), C(), UD(0)))  # U = ∅ → halt


# --- ENCODE_DECR (U[12][4]) ---
# rem in U[13].  Emit bytes: while rem > 1, write 0x99, rem -= 2.
# After loop, if rem == 1, write 0x89.
encode_decr = [
    # Check rem == 0
    diff_(WRAP(UD(13)), WRAP(UD(0)), UD(14)),  # U[14] = diff(rem, ZERO)
    # ZERO is nonempty; diff(WRAP(rem), WRAP(ZERO)) is nonempty when rem != ZERO
    # Hmm, ZERO = {{∅}} which is NOT the same as ∅
    # We need to compare with ∅ (the empty set from C\C)
    diff_(C(), C(), UD(14)),                     # U[14] = ∅ (for comparison base)
]
    
# Wait, I need to think about how to compare rem with 0 (value 0 = ∅, not ZERO which is {{∅}}).
# VALUE 0 is the empty set S5Set() = ∅.
# U[0] = ZERO = {{∅}} which has set_value 0 but is NONEMPTY.
# To get the empty set: C \ C = ∅.
# To check if rem == ∅: diff(WRAP(rem), WRAP(C\C)) = ∅ when rem == ∅.

# Let me redo encode_decr more carefully:
encode_decr = [
    # Check rem == 0 (empty set)
    diff_(C(), C(), UD(14)),                     # U[14] = ∅
    diff_(WRAP(UD(13)), WRAP(UD(14)), UD(14)),  # U[14] = diff(WRAP(rem), WRAP(∅))
    # U[14] nonempty when rem != ∅
    # We need to call CONTINUE when rem != ∅, skip when rem == ∅
    # call ENCODE_CONTINUE(cond=U[14])
    inters(UD(12), UD(12), C()),
    subset(0),                                    # dummy: we need a separate subroutine
    # Actually we don't have ENCODE_CONTINUE yet.
    # Let me structure differently.
]

# I'll restructure: encode_decr is self-contained with nested checks.
# Actually, let me simplify: the encoding loop uses the SKIP trick.

# ENCODE_DECR (U[12][4]):
#   1. Check rem == 0: if so, return (done)
#   2. Check rem == 1: if so, write 0x89, return
#   3. Write 0x99, rem = pred(pred(rem)), call ENCODE_DECR

# For the checks, use the double-call pattern:
#   marker = ∅
#   scratch = diff(WRAP(rem), WRAP(ZERO_C))  -- compare with ∅ (C\C)
#   Since WRAP(rem) \ WRAP(∅) = nonempty when rem != ∅, empty when rem == ∅
#   call SET_MARKER(cond=scratch) → called when rem != ∅ → marker = ONE
#   flag_is_zero = diff(WRAP(marker), WRAP(ONE)) → nonempty when marker!=ONE (rem==∅)
#   call RETURN(cond=flag_is_zero) → called when rem == ∅ → return (do nothing)
#   
#   But "return" in S5 means just... return from the subroutine.  We're already
#   at the end of the subroutine body.  If we reach the end, we return.
#   So if rem == ∅, we want to skip the rest of the body and return.
#   We can't skip.  But we can CONDITIONALLY write bytes only when rem != ∅.
#   
#   Actually, if rem == ∅, we should return without writing anything.
#   If rem != ∅, continue to check rem == 1.
#   
#   Use the marker trick:
#     marker = ∅
#     scratch = diff(WRAP(rem), WRAP(∅))
#     call SET_MARKER(cond=scratch)  # called when rem != ∅
#     # Now marker = ONE only when rem != ∅
#     # Call WRITE_BYTE_89 with cond = ... let me rethink
#
#   This still has the same inversion problem.
#   Let me just use a different algorithm:
#
#   Instead of checking rem == 0 first, check rem <= 1:
#     scratch1 = diff(WRAP(rem), WRAP(∅))   # empty when rem == ∅ (value 0)
#     scratch2 = diff(WRAP(rem), WRAP(ONE))  # empty when rem == ONE (value 1)
#     
#     We want to continue only when BOTH are nonempty (rem > 1).
#     That's the intersection trick again!
#     continue_cond = scratch1 ∩ scratch2
#     Both are {rem} singletons (or empty).  Intersection = {rem} when both nonempty.
#     
#     Then:
#       write 0x99 (ALWAYS if we continue — needs to be conditional too)
#   
#   Hmm, we also need to write 0x89 when rem == 1.
#
#   OK let me just implement a FLAT body with three subcases:

encode_decr = [
    # rem in U[13]
    # Check rem == 0 (empty set)
    diff_(WRAP(UD(13)), WRAP(diff_(C(),C(),UD(14))), UD(14)),  # scratch = diff(rem, ∅)
    # This doesn't work because the inner diff_ is an Instruction, not a value.
    
    # Let me just do it step by step:
]

# I realize I'm making this WAY too complex.  Let me just generate
# a FLAT sequence of instructions that implements the encoding loop
# using a subroutine with conditional recursion.

# The subroutine ENCODE_DECR:
#   1. rem (U[13]) must be a value whose set_value is the decrement count
#   2. Check rem == ∅ (value 0): 
#        diff(WRAP(rem), WRAP(∅)) = empty when rem == ∅
#        → we want to RETURN when empty
#        → use the SKIP trick
#   3. Check rem == ONE (value 1): 
#        diff(WRAP(rem), WRAP(ONE)) = empty when rem == ONE
#        → write 0x89, RETURN
#   4. Write 0x99, rem = pred(pred(rem)), call ENCODE_DECR

# For step 2 (check rem == ∅ with skip trick):
#   marker = ∅ (U[14])
#   scratch = diff(WRAP(rem), WRAP(∅)) → U[14]... wait, I can't use diff with ∅
#   because ∅ is C\C which is computed at runtime.

# Let me pre-compute ∅: C\C → U[14]
# Then scratch = diff(WRAP(rem), WRAP(U[14])) where U[14] = ∅
#   scratch is empty when rem == ∅, nonempty when rem != ∅
#   call SET_MARKER(cond=scratch) → called when rem != ∅ → U[14] = ONE
#   (SET_MARKER is U[12][7]: U[14] = ONE)
#   (But now U[14] was the ∅ holder and is clobbered!)
#   
#   Use U[14] for ∅ initially, then SET_MARKER clobbers to ONE.
#   After:
#     If rem == ∅: U[14] stays ∅ (SET_MARKER not called)
#     If rem != ∅: U[14] = ONE (SET_MARKER was called)
#   
#   flag_is_zero = diff(WRAP(U[14]), WRAP(ONE)) → nonempty when U[14] != ONE (rem == ∅)
#   Call RETURN_IF_ZERO(cond=flag_is_zero):
#     CALLED when rem == ∅ → does nothing (falls through)
#     NOT called when rem != ∅
#   Problem: even when called for rem == ∅, the RETURN_IF_ZERO subroutine
#   just returns.  Execution continues in ENCODE_DECR.
#   
#   We need RETURN_IF_ZERO to prevent further execution.
#   But subroutines always return control.
#
#   Unless RETURN_IF_ZERO HALTS: U = ∅
#   But that halts the WHOLE program, not just ENCODE_DECR.
#
#   I think the FUNDAMENTAL ISSUE is that S5 doesn't have early return.
#   Subroutines always run to completion.
#
#   So every subroutine body must be structured such that all instructions
#   are either conditional or harmless when conditions don't apply.
#
#   For ENCODE_DECR:
#     1. Check rem == ∅ → if so, write nothing, return
#     2. Check rem == 1 → if so, write 0x89, return
#     3. Write 0x99, rem = pred(pred(rem)), call ENCODE_DECR
#
#   The issue: in step 1, if rem == ∅, we don't want steps 2-3 to execute.
#   But they WILL execute because S5 doesn't have early return.
#
#   SOLUTION: Make each step CONDITIONAL using the skip trick.
#     Step 2 (check rem==1):
#       Only check if rem != ∅.  Use the continue_cond approach:
#       We computed scratch = diff(rem, ∅) earlier.
#       If scratch is nonempty (rem != ∅), we should check rem==1.
#       If scratch is empty (rem == ∅), we should skip both checks 2 and 3.
#       
#       Use: call CHECK_REM(cond=scratch) where CHECK_REM does steps 2-3.
#       If scratch nonempty (rem != ∅): CHECK_REM is called
#       If scratch empty (rem == ∅): CHECK_REM is skipped → nothing happens
#
#   YES!  This is the right pattern:
#     ENCODE_DECR:
#       1. scratch = diff(WRAP(rem), WRAP(∅))   → nonempty when rem != ∅
#       2. call CHECK_REM(cond=scratch)           → called only when rem != ∅
#       (Nothing else happens when rem == ∅)
#
#     CHECK_REM (U[12][9]):
#       1. Check rem == 1: 
#          scratch = diff(WRAP(rem), WRAP(ONE)) → empty when rem == ONE
#          marker = ∅
#          call SET_MARKER(cond=scratch) → called when rem != 1 → marker = ONE
#          is_one = diff(WRAP(marker), WRAP(ONE)) → nonempty when marker != ONE (rem==1)
#          call WRITE_89(cond=is_one) → write 0x89 when rem == 1
#          call CHECK_BIG(cond=scratch) → called when rem != 1 (rem > 1)
#
#     WRITE_89 (U[12][10]):
#       Write 0x89, return
#
#     CHECK_BIG (U[12][11]):
#       Write 0x99, rem = pred(pred(rem)), call ENCODE_DECR

# This is getting RIDICULOUSLY deep in nested subroutines.
# Let me step WAY back and think about a simpler approach.

# SIMPLEST POSSIBLE APPROACH:
# Instead of the complex encoding loop, write the SUBSET_SELECT instruction
# using a DIFFERENT STRATEGY.

# STRATEGY: 
#   Since we have pred available, and the encoding for INDEX can be built
#   by decrementing from INDEX:
#     
#     1. Write prefix bytes (0x50, 0xc9)
#     2. Write 0x9a (baseline value 1)
#     3. Write count_99 copies of 0x99
#     4. Write 0x89 if has_89
#     
#   where count_99 = (INDEX-1)//2 and has_89 = (INDEX-1)%2.
#
#   Instead of a loop, we can UNROLL because the generator KNOWS INDEX
#   at generation time?  No, INDEX is runtime.
#
#   But we CAN use a loop that calls pred.  The loop body is FIXED:
#     1. Write 0x99
#     2. rem = pred(pred(rem))
#     3. If rem > 1, call loop again
#
#   The "if rem > 1" check uses the intersection of diff(rem,∅) and diff(rem,ONE).

# OK let me just use a DIFFERENT subroutine pattern that WORKS:

# ENCODE_DECR: handles rem in U[13]
#   1. Compute marker = diff(WRAP(rem), WRAP(∅)) — nonempty when rem != ∅
#      Actually, compute empty_set from C\C first.
#      Then diff(WRAP(rem), WRAP(empty_set))
#
#   2. If marker nonempty (rem != ∅): do MORE_CHECKS
#      MORE_CHECKS: check rem == 1, if so write 0x89
#                   else write 0x99, rem = pred(pred(rem)), call ENCODE_DECR
#
#   3. If marker empty (rem == ∅): nothing (return)

# The key: step 2 is a SEPARATE subroutine called with cond=marker.
# This subroutine does steps 2-3 CONDITIONALLY.
# If not called, we fall through to... the end of ENCODE_DECR.

# This still has the problem that ENCODE_DECR's body includes BOTH
# the marker computation AND the call to MORE_CHECKS, plus fallthrough.

# Let me write it out:

encode_decr_v2 = [
    # Compute empty set in U[14]
    diff_(C(), C(), UD(14)),                     # U[14] = ∅
    # Compute marker: diff(WRAP(rem), WRAP(∅))
    diff_(WRAP(UD(13)), WRAP(UD(14)), UD(14)),  # U[14] = diff(WRAP(rem), WRAP(∅))
    # U[14] is nonempty when rem != ∅, empty when rem == ∅
    
    # Call ENCODE_CONTINUE if rem != ∅
    inters(UD(12), UD(12), C()),
    subset(9),                                    # C = C[9] = ENCODE_CONTINUE
    subr_call(cond=UD(14)),                      # called when rem != ∅
    
    # If rem == ∅, fall through to here → nothing happens
]

# ENCODE_CONTINUE (U[12][9]):
encode_continue = [
    # rem in U[13]
    # Check rem == 1
    diff_(WRAP(UD(13)), WRAP(UD(1)), UD(14)),  # U[14] = diff(rem, ONE)
    # U[14] nonempty when rem != 1, empty when rem == 1
    
    # If rem == 1: write 0x89 and return
    # We need to call WRITE_AND_RETURN when rem == 1
    # But we can only call on NONEMPTY condition.
    # Use marker trick:
    # marker = ∅ (U[14] was clobbered by diff above; use U[15])
    inters(UD(0), UD(0), UD(15)),              # U[15] = ∅... wait, U[0] is ZERO which is NONEMPTY
    
    # Hmm, I can't easily get ∅ again.  Let me use a different slot.
]

# I really need to keep this simpler.  Let me restructure ENCODE_DECR
# to avoid the marker trick for the rem==1 case.

# KEY INSIGHT: I can structure ENCODE_DECR as:
#   1. If rem == ∅: return (nothing happens)
#   2. If rem == ONE: write 0x89, return
#   3. Write 0x99, rem = pred(pred(rem)), call ENCODE_DECR
#
# Instead of complex marker tricks, use CONDITIONAL RECURSION:
#   After writing 0x99 and decrementing rem, check if rem > 1.
#   If rem > 1: call ENCODE_DECR again.
#   The check for rem > 1 uses: continue = diff(rem,∅) ∩ diff(rem,ONE)
#   (both nonempty when rem > 1, one empty when rem <= 1)
#
# For steps 1 and 2: use the CALL-ON-NONEMPTY pattern.
#   Step 1: call NEXT_STEP(cond=diff(rem,∅)) → called when rem != ∅
#     In NEXT_STEP: 
#       Step 2: call WRITE_89(cond=diff(rem,ONE)) → called when rem != 1
#         In WRITE_89 (actually this is backwards):
#           When cond=diff(rem,ONE) is nonempty, rem != 1 → SKIP writing 0x89
#           When cond=diff(rem,ONE) is empty, rem == 1 → WANT to write 0x89
#         Again the "call when nonempty" doesn't match "want when empty".
#
#   Let me INVERT: NEXT_STEP is called when rem != ∅ (which we want).
#   Inside NEXT_STEP, if rem == 1, write 0x89 and return.
#   To check rem == 1: diff(rem, ONE) is empty.
#   We need to DETECT emptiness.  Use the marker trick.

#   mark = ∅
#   scratch = diff(rem, ONE)  # nonempty when rem != 1
#   call SET_MARKER(cond=scratch)  # called when rem != 1 → mark = ONE
#   is_one = diff(mark, ONE)  # nonempty when mark != ONE → rem == 1 → call WRITE_89

#   But this requires 2 more subroutines for SET_MARKER and WRITE_89.
#   Actually, SET_MARKER and WRITE_89 can be the SAME subroutines
#   defined earlier (U[12][7] and U[12][10]).

# OK I'm going to commit to this approach.  Let me write ALL the subroutines
# needed and the complete generator.  I'll use auxiliary subroutines for
# the marker/set_flag patterns.

# SUBROUTINES:
#   U[12][0] = DEMO_MAIN
#   U[12][1] = BUILD_LOOP
#   U[12][2] = LUT_LOOKUP
#   U[12][3] = SEARCH_PRED
#   U[12][4] = ENCODE_DECR
#   U[12][5] = COMPARE_LOOP
#   U[12][6] = CHECK_AND_SET_FLAG (for COMPARE_LOOP)
#   U[12][7] = SET_MARKER: U[14] = ONE (generic marker setter)
#   U[12][8] = SET_FLAG: U[10] = ONE
#   U[12][9] = ENCODE_CONTINUE (for ENCODE_DECR, called when rem != ∅)
#   U[12][10] = WRITE_89: write 0x89 to buffer

# OK let me generate the complete S5 source.

print("Generating demo.s5...")
# The rest will be written to a file
