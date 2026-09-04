"""pytest harness: s5 ddate.s5 vs reference.ddate across a date set.

Runs init.s5 + succ.s5 + ddate.s5 in a single executor pass.  ddate.s5 reads
8 ASCII bytes YYYYMMDD from stdin and prints 4 lines (season din weekday yold;
St. Tib's Day prints the sentinel 0 0 0 yold).  The output is compared line-
by-line against the canonical `reference.ddate`.

init.s5 normalizes COUNTER via an fd 0 buffer round-trip (no stdout side
effect), so stdout during the run is exactly ddate's 4-field output.  ddate.s5
grows U 32->256 itself via three self-unions.

A high recursion limit is required: the SUCC/ADD/PLUT machinery runs nested
subroutine frames up to ~hundreds deep.
"""
import io
import sys
import random
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from s5 import tokenize_files, Parser, Executor
import reference

sys.setrecursionlimit(40000)

FILES = [
    str(HERE / ".." / "arithmetic" / "init.s5"),
    str(HERE / ".." / "arithmetic" / "succ.s5"),
    str(HERE / "ddate.s5"),
]


def run_ddate(date_bytes):
    """Run the full pipeline for an 8-byte date, return the 4 output lines."""
    tokens = list(tokenize_files(FILES))
    instructions = Parser(tokens).parse_program()
    ex = Executor(buf_sizes={0: 64, 1: 64, 2: 64})
    out = io.StringIO()
    old_out, old_in = sys.stdout, sys.stdin
    sys.stdin = io.TextIOWrapper(io.BytesIO(date_bytes), encoding="latin-1")
    sys.stdout = out
    try:
        status = ex.run(instructions)
    finally:
        sys.stdout = old_out
        sys.stdin = old_in
    assert status == "finished", f"run failed: {status}"
    return out.getvalue().strip().split("\n")


def _date_to_bytes(yyyymmdd: int) -> bytes:
    return f"{yyyymmdd:08d}".encode("ascii")


DATE_CASES = [
    20260903,   # main case
    20240229,   # St. Tib's Day
    20240301,   # day after St. Tib's
    20200101,
    20201231,
    19001231,   # century non-leap (1900)
    20001231,   # century leap (2000)
    20000229,   # century-leap Feb 29 -> St. Tib's Day
    20240101,
    20241231,
    19991231,
    20040229,   # regular leap Feb 29 -> St. Tib's Day
    20260731,
    99991231,
    10000101,
    20381231,   # late-year date
]


@pytest.mark.parametrize("yyyymmdd", DATE_CASES)
def test_ddate_matches_reference(yyyymmdd):
    expected = reference.format_fields(reference.ddate(yyyymmdd)).split("\n")
    got = run_ddate(_date_to_bytes(yyyymmdd))
    assert got == expected, f"{yyyymmdd}: s5={got} ref={expected}"


def _random_valid_dates(seed, n, lo_year=1000, hi_year=9999):
    """Generate `n` valid random YYYYMMDD dates (widely-spaced years)."""
    rng = random.Random(seed)
    MONTHS = reference.MONTHS
    out = set()
    attempts = 0
    while len(out) < n and attempts < n * 40:
        attempts += 1
        year = rng.randint(lo_year, hi_year)
        month = rng.randint(1, 12)
        dim = MONTHS[month - 1]
        if month == 2 and reference.is_leap(year):
            dim = 29
        day = rng.randint(1, dim)
        out.add(year * 10000 + month * 100 + day)
    return sorted(out)


RANDOM_DATES = _random_valid_dates(seed=1234, n=60)


@pytest.mark.parametrize("yyyymmdd", RANDOM_DATES)
def test_ddate_random_matches_reference(yyyymmdd):
    expected = reference.format_fields(reference.ddate(yyyymmdd)).split("\n")
    got = run_ddate(_date_to_bytes(yyyymmdd))
    assert got == expected, f"{yyyymmdd}: s5={got} ref={expected}"
