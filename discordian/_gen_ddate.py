"""Generate ddate.s5 — Discordian date converter (structured fields).

Reads 8 ASCII bytes `YYYYMMDD` from stdin, prints one integer per line:
    season        1-5
    day_in_season 1-73
    weekday       1-5
    yold          year + 1166
St. Tib's Day prints the sentinel `0 0 0 <yold>`.

Algorithm (canonical ddate.c `makeday` semantics):
    days0   = cumDaysBefore(month) + (day - 1)
    season  = days0 // 73 + 1
    din     = days0 %  73 + 1
    weekday = days0 %   5
    yold    = year + 1166            (digit-wise add, Horner recombine)
    if leap and month == 2 and day == 29  -> St. Tib's Day

Leap (Gregorian): leap = (Y%100!=0)? (Y%4==0) : (Y%400==0)  via last-2/first-2
digit components.

Runs on top of arithmetic/init.s5 + arithmetic/succ.s5 (which supply U[0..6],
NORM_SUCC and successor).  Requires `s5 --bufsize >= 64` (IO normalize uses
fd0 buffers sized >= 64).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from s5 import Address, AddressType, Opcode, Instruction
from s5.pretty import pretty_print

# ---------------------------------------------------------------------------
# Slot map. U grown to 256 at runtime by init+self-unions.
# Arithmetic (init/succ): 0=ZERO 1=ONE 2=COUNTER 3=IN_A 4=IN_B 5=OUT 6=SUCC
# ---------------------------------------------------------------------------
ZERO, ONE, COUNTER, IN_A, IN_B, OUT, SUCC = 0, 1, 2, 3, 4, 5, 6

DIGITS   = [70, 71, 72, 73, 74, 75, 76, 77]   # d1..d8 (year,month,day digits)
DIGLUT   = 78
TENSLUT  = 79
CUMLEN   = 80
PLUT     = 81
MCONST   = 82

ADDSTR, ADDA, ADDB, ADDDST, ADDI, ADDCOND, ADDBOUND = 83, 84, 85, 86, 87, 88, 89
PLBSTR, PREV, CUR, STOP, PLB2 = 90, 91, 92, 93, 94
VSSTR, VSA, VSB, VSR, VSI, VSC = 95, 96, 97, 98, 99, 100
DMSTR, DMA, DMD, DMQ, DMR, DMGE = 101, 102, 103, 104, 105, 106
ZRSTR, FLAG = 107, 108
OVSTR = 109
PRSTR = 110

Y2, A12 = 111, 112
REM2, REM4, F2, FA = 113, 114, 118, 119
LEAP, BM2, BD29, TB1, TIB = 115, 116, 117, 120, 121
DAY0, MONTH, DDAY, S0, D0, W0 = 122, 123, 124, 125, 126, 127
SEAS, DIN, WD, YOLDNUM = 128, 129, 130, 131
TNORM, TTIB = 132, 133
O_ONES, O_TENS, O_HUND, O_THOU = 134, 135, 136, 137
CARR, COLSUM, TMP = 138, 139, 140
SCR1, SCR2, SCR3 = 141, 142, 143
GESCR = 144
XCPY = 145

# materialized constants
C73, C5, C4, C2, C29, C10, C6, CST1 = 40, 41, 42, 43, 44, 45, 46, 47

all_instrs = []
_out = None


def U():   return Address(AddressType.U)
def C():   return Address(AddressType.C)
def UD(i): return Address(AddressType.UD, index=i)
def WRAP(a): return Address(AddressType.WRAP, sub_addr=a)
def IO(fd):
    a = Address(AddressType.IO); a.dispatch_depth = fd + 1; a.has_depth = True; return a
def IOB(fd):
    a = Address(AddressType.IO_BYTE); a.dispatch_depth = fd + 1; a.has_depth = True; return a

def inters(a, b, d): return Instruction(Opcode.INTERSECTION, addr_a=a, addr_b=b, addr_dest=d)
def union_(a, b, d): return Instruction(Opcode.UNION, addr_a=a, addr_b=b, addr_dest=d)
def diff_(a, b, d):  return Instruction(Opcode.DIFFERENCE, addr_a=a, addr_b=b, addr_dest=d)
def subset(n):       return Instruction(Opcode.SUBSET_SELECT, n=n)
def subset_addr(a):  return Instruction(Opcode.SUBSET_SELECT, addr_b=a)
def subr_decl(body, loc=None): return Instruction(Opcode.SUBR, subr_body=body, addr_a=loc)
def subr_call(loc=None, cond=None): return Instruction(Opcode.SUBR, addr_a=loc, addr_b=cond)

def copy(src, dst):     return inters(UD(src), UD(src), UD(dst))
def emit(i):            _out.append(i)


class _Body:
    pass


def body(make_fn):
    b = _Body()
    b.body = []
    b.build = make_fn
    return b


class Struct:
    def __init__(self, slot):
        self.slot = slot
        self.n = 0
    def add(self, body):
        global _out
        if isinstance(body, _Body):
            save = _out
            _out = body.body
            try:
                body.build()
            finally:
                _out = save
            body_list = body.body
        else:
            body_list = body
        emit(subr_decl(body_list))
        emit(union_(UD(self.slot), WRAP(C()), UD(self.slot)))
        idx = self.n
        self.n += 1
        return idx
    def call(self, idx, cond=None):
        emit(inters(UD(self.slot), UD(self.slot), C()))
        emit(subset(idx))
        emit(subr_call(cond=cond))


def call_succ():
    emit(inters(UD(SUCC), UD(SUCC), C()))
    emit(subset(0))
    emit(subr_call())


def materialize_const(c, slot):
    body = [inters(UD(0), UD(0), UD(0)) for _ in range(c)]
    emit(subr_decl(body))
    emit(inters(C(), C(), IO(0)))          # write C to fd0 (normalize)
    emit(diff_(C(), C(), C()))
    emit(union_(IO(0), C(), C()))          # read back
    emit(inters(C(), C(), UD(slot)))


def materialize_table(values, slot):
    emit(diff_(UD(slot), UD(slot), UD(slot)))
    for v in values:
        materialize_const(v, MCONST)
        emit(inters(UD(MCONST), UD(MCONST), C()))
        emit(union_(UD(slot), WRAP(C()), UD(slot)))


# ===========================================================================
# Primitive: table lookup TAB[INDEX] -> dst
# ===========================================================================
def lookup(table_slot, index_slot, dst_slot):
    emit(inters(UD(table_slot), UD(table_slot), C()))
    emit(subset_addr(UD(index_slot)))
    emit(inters(C(), C(), UD(dst_slot)))


# ===========================================================================
# ADD(a,b) -> ADDDST   (canonical values)
# ===========================================================================
ADD = Struct(ADDSTR)
def build_ADD():
    def mk_main():
        emit(copy(ADDA, ADDDST))
        emit(inters(UD(ZERO), UD(ZERO), C())); emit(inters(C(), C(), UD(ADDI)))   # i=0
        emit(copy(ADDB, ADDBOUND))
        ADD.call(1, cond=UD(ADDB))
    def mk_step():
        emit(copy(ADDDST, IN_A)); call_succ(); emit(copy(OUT, ADDDST))
        emit(copy(ADDI, IN_A)); call_succ(); emit(copy(OUT, ADDI))
        emit(diff_(WRAP(UD(ADDBOUND)), WRAP(UD(ADDI)), UD(ADDCOND)))
        ADD.call(1, cond=UD(ADDCOND))
    ADD.add(body(mk_main))
    ADD.add(body(mk_step))

def emit_ADD(a_slot, b_slot, dst_slot):
    emit(copy(a_slot, ADDA))
    emit(copy(b_slot, ADDB))
    ADD.call(0)
    emit(copy(ADDDST, dst_slot))


def emit_MUL10(x_slot, dst_slot):
    emit(copy(x_slot, dst_slot))
    emit(copy(x_slot, XCPY))
    for _ in range(9):
        emit_ADD(dst_slot, XCPY, dst_slot)


# ===========================================================================
# PLUT pred LUT: PLUT[k] = k-1 for k=0..N  (runtime succ-march)
# ===========================================================================
PLB = Struct(PLBSTR)
def build_PLUT(N):
    materialize_const(N + 1, STOP)
    def mk_build():
        emit(diff_(UD(PLUT), UD(PLUT), UD(PLUT)))
        emit(inters(UD(ZERO), UD(ZERO), C())); emit(inters(C(), C(), UD(MCONST)))
        emit(inters(UD(MCONST), UD(MCONST), C()))
        emit(union_(UD(PLUT), WRAP(C()), UD(PLUT)))          # PLUT[0] = 0
        emit(inters(UD(ZERO), UD(ZERO), C())); emit(inters(C(), C(), UD(PREV)))   # prev=0
        emit(inters(UD(ONE), UD(ONE), C())); emit(inters(C(), C(), UD(CUR)))      # cur=1
        PLB.call(1, cond=UD(CUR))
    def mk_loop():
        emit(inters(UD(PREV), UD(PREV), C()))
        emit(union_(UD(PLUT), WRAP(C()), UD(PLUT)))          # append prev
        emit(copy(CUR, PREV))
        emit(copy(CUR, IN_A)); call_succ(); emit(copy(OUT, CUR))
        emit(diff_(WRAP(UD(STOP)), WRAP(UD(CUR)), UD(PLB2)))
        PLB.call(1, cond=UD(PLB2))
    PLB.add(body(mk_build))
    PLB.add(body(mk_loop))
    PLB.call(0)                       # run the PLUT build now


# ===========================================================================
# VarSUB(a,b)->VSR : max(0, a-b) via PLUT pred steps (variable b, canonical)
# ===========================================================================
VS = Struct(VSSTR)
def build_VS():
    def mk_main():
        emit(copy(VSA, VSR))
        emit(inters(UD(ZERO), UD(ZERO), C())); emit(inters(C(), C(), UD(VSI)))   # i=0
        emit(diff_(WRAP(UD(VSB)), WRAP(UD(ZERO)), UD(VSC)))             # b != 0 ?
        VS.call(1, cond=UD(VSC))
    def mk_step():
        lookup(PLUT, VSR, VSR)      # R = pred(R)
        emit(copy(VSI, IN_A)); call_succ(); emit(copy(OUT, VSI))        # i++
        emit(diff_(WRAP(UD(VSB)), WRAP(UD(VSI)), UD(VSC)))              # i != b ?
        VS.call(1, cond=UD(VSC))
    VS.add(body(mk_main))
    VS.add(body(mk_step))

def emit_VarSUB(a_slot, b_slot, dst_slot):
    emit(copy(a_slot, VSA))
    emit(copy(b_slot, VSB))
    VS.call(0)
    emit(copy(VSR, dst_slot))


# ===========================================================================
# GE(r,d): r>=d  iff  VarSUB(r, d-1) != 0 ;  d-1 via PLUT
# ===========================================================================
def emit_GE(r_slot, d_slot, out_slot):
    lookup(PLUT, d_slot, TMP)              # TMP = d-1
    emit_VarSUB(r_slot, TMP, GESCR)
    emit(diff_(UD(GESCR), UD(ZERO), C()))      # nonempty check (GESCR \ ZERO)
    emit(inters(C(), C(), UD(out_slot)))


# ===========================================================================
# DIVMOD(a,d) -> (q,r) in DMR/DMQ
# ===========================================================================
DM = Struct(DMSTR)
def build_DM():
    def mk_main():
        emit(inters(UD(ZERO), UD(ZERO), C())); emit(inters(C(), C(), UD(DMQ)))   # q=0
        emit(copy(DMA, DMR))
        emit_GE(DMR, DMD, DMGE)
        DM.call(1, cond=UD(DMGE))
    def mk_loop():
        emit_VarSUB(DMR, DMD, DMR)
        emit_ADD(DMQ, ONE, DMQ)
        emit_GE(DMR, DMD, DMGE)
        DM.call(1, cond=UD(DMGE))
    DM.add(body(mk_main))
    DM.add(body(mk_loop))

def emit_DIVMOD(a_slot, d_slot, q_slot, r_slot):
    emit(copy(a_slot, DMA))
    emit(copy(d_slot, DMD))
    DM.call(0)
    emit(copy(DMQ, q_slot))
    emit(copy(DMR, r_slot))


# ===========================================================================
# Booleans: ZEROQ(src)=1 iff src==0 ; EQ_bool(a,const)=1 iff a==const
# ===========================================================================
ZR = Struct(ZRSTR)
def build_ZR():
    ZR.add([ inters(UD(ZERO), UD(ZERO), C()), inters(C(), C(), UD(FLAG)) ])  # FLAG=0

def emit_ZEROQ(src_slot, out_slot):
    emit(inters(UD(ONE), UD(ONE), C())); emit(inters(C(), C(), UD(FLAG)))   # FLAG=1
    emit(diff_(WRAP(UD(src_slot)), WRAP(UD(ZERO)), UD(SCR1)))             # src!=0?
    ZR.call(0, cond=UD(SCR1))
    emit(copy(FLAG, out_slot))

def emit_EQ_bool(a_slot, const_slot, out_slot):
    emit(inters(UD(ONE), UD(ONE), C())); emit(inters(C(), C(), UD(FLAG)))   # FLAG=1
    emit(diff_(WRAP(UD(a_slot)), WRAP(UD(const_slot)), UD(SCR1)))
    ZR.call(0, cond=UD(SCR1))
    emit(copy(FLAG, out_slot))


# ===========================================================================
# Output
# ===========================================================================
def print_val(slot):
    emit(inters(UD(slot), UD(slot), C()))
    emit(inters(C(), C(), IO(1)))

PR = Struct(PRSTR)
def build_PR():
    def mk_normal():
        print_val(SEAS); print_val(DIN); print_val(WD); print_val(YOLDNUM)
    def mk_tib():
        print_val(ZERO); print_val(ZERO); print_val(ZERO); print_val(YOLDNUM)
    PR.add(body(mk_normal))
    PR.add(body(mk_tib))


# ===========================================================================
# Override struct: OV[0] = [ LEAP = F2 ]  (used for leap default/override)
# ===========================================================================
OV = Struct(OVSTR)
def build_OV():
    OV.add([ copy(F2, LEAP) ])


# ===========================================================================
def grow_u():
    for _ in range(3):
        emit(union_(U(), U(), U()))


# ===========================================================================
def build_constants():
    materialize_const(73, C73)
    materialize_const(5, C5)
    materialize_const(4, C4)
    materialize_const(2, C2)
    materialize_const(29, C29)
    materialize_const(10, C10)
    materialize_const(6, C6)
    materialize_const(1, CST1)


def build_tables():
    # digit LUT: ascii char -> digit (0..57 range; valid 48..57)
    materialize_table([0]*48 + [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], DIGLUT)
    # tens LUT: digit -> digit*10
    materialize_table([0, 10, 20, 30, 40, 50, 60, 70, 80, 90], TENSLUT)
    # cum days before month m (0..12)
    materialize_table([0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334], CUMLEN)


def read_byte_into(slot):
    emit(union_(IOB(0), UD(0), UD(slot)))


# ===========================================================================
# Main driver
# ===========================================================================
def drive():
    # read 8 bytes, convert to digits
    for i in range(8):
        read_byte_into(SCR1)
        lookup(DIGLUT, SCR1, DIGITS[i])

    # MONTH = 10*d5 + d6 ;  DDAY = 10*d7 + d8
    lookup(TENSLUT, DIGITS[4], TMP); emit_ADD(TMP, DIGITS[5], MONTH)
    lookup(TENSLUT, DIGITS[6], TMP); emit_ADD(TMP, DIGITS[7], DDAY)

    # DAY0 = CUMLEN[MONTH] + (DDAY-1)
    lookup(CUMLEN, MONTH, DAY0)
    lookup(PLUT, DDAY, TMP)
    emit_ADD(DAY0, TMP, DAY0)

    # season/day/weeks
    emit_DIVMOD(DAY0, C73, S0, D0)
    emit_DIVMOD(DAY0, C5, TMP, W0)
    emit_ADD(S0, ONE, SEAS)
    emit_ADD(D0, ONE, DIN)
    emit_ADD(W0, ONE, WD)

    # leap
    lookup(TENSLUT, DIGITS[2], TMP); emit_ADD(TMP, DIGITS[3], Y2)    # last 2 digits
    lookup(TENSLUT, DIGITS[0], TMP); emit_ADD(TMP, DIGITS[1], A12)   # first 2 digits
    emit_DIVMOD(Y2, C4, TMP, REM2)
    emit_DIVMOD(A12, C4, TMP, REM4)
    emit_ZEROQ(REM2, F2)   # F2 = (Y%100 part %4==0)
    emit_ZEROQ(REM4, FA)   # FA = (first2 %4==0)
    emit(copy(FA, LEAP))
    emit(diff_(WRAP(UD(Y2)), WRAP(UD(ZERO)), UD(SCR1)))  # Y2 != 0 ?
    OV.call(0, cond=UD(SCR1))                            # if so LEAP=F2

    # St. Tib's detection
    emit_EQ_bool(MONTH, C2, BM2)
    emit_EQ_bool(DDAY, C29, BD29)
    emit(inters(UD(LEAP), UD(BM2), UD(TB1)))
    emit(inters(UD(TB1), UD(BD29), UD(TIB)))

    # yold = year + 1166
    compute_yold()

    # output, branching on St. Tib's
    emit_ZEROQ(TIB, TNORM)     # TNORM = 1 iff not St. Tib's
    emit(copy(TIB, TTIB))
    PR.call(1, cond=UD(TTIB))   # St. Tib's:  0 0 0 yold
    PR.call(0, cond=UD(TNORM))  # normal:     season din weekday yold


def compute_yold():
    c = CARR
    emit(inters(UD(ZERO), UD(ZERO), C())); emit(inters(C(), C(), UD(c)))   # carry=0

    def add_col(d_slot, bias_slot, out_digit_slot):
        # COLSUM = d + bias + carry ; digit = COLSUM%10 ; carry = COLSUM//10
        emit_ADD(d_slot, bias_slot, TMP)
        emit_ADD(TMP, c, COLSUM)
        emit_DIVMOD(COLSUM, C10, c, out_digit_slot)   # q -> carry(c), r -> digit

    add_col(DIGITS[3], C6, O_ONES)   # ones  (d4 + 6)
    add_col(DIGITS[2], C6, O_TENS)   # tens  (d3 + 6)
    add_col(DIGITS[1], CST1, O_HUND) # hundreds (d2 + 1)
    add_col(DIGITS[0], CST1, O_THOU) # thousands (d1 + 1)

    # yoldnum = carry (5th/Msb digit) then Horner-recombine
    emit(copy(c, YOLDNUM))
    emit_MUL10(YOLDNUM, YOLDNUM); emit_ADD(YOLDNUM, O_THOU, YOLDNUM)
    emit_MUL10(YOLDNUM, YOLDNUM); emit_ADD(YOLDNUM, O_HUND, YOLDNUM)
    emit_MUL10(YOLDNUM, YOLDNUM); emit_ADD(YOLDNUM, O_TENS, YOLDNUM)
    emit_MUL10(YOLDNUM, YOLDNUM); emit_ADD(YOLDNUM, O_ONES, YOLDNUM)


def generate(N=364):
    global _out
    _out = all_instrs
    grow_u()
    build_constants()
    build_tables()
    build_ADD()
    build_PLUT(N)
    build_VS()
    build_DM()
    build_ZR()
    build_OV()
    build_PR()
    drive()


def write_ddate(out_path):
    generate()
    text = pretty_print(all_instrs)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Wrote {out_path}  ({len(all_instrs)} instrs)")


if __name__ == "__main__":
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddate.s5")
    write_ddate(path)
