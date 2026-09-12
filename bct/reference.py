"""Reference Bitwise-Cyclic-Tag (BCT) simulator, independent of S5.

BCT (Cook 2004; the system behind Rule 110's universality proof):

  A machine is a finite, non-empty *program string* of bits (treated as a
  cyclic string) together with an initial *data string* of bits.  One tick:

    * if the data string is empty, halt;
    * read and delete its first bit `b`;
    * if b == 1, append the *current program bit* to the data string;
    * advance the program head one position, cyclically.

  Equivalently (see PLAN.md) BCT is the subclass of cyclic-tag machines whose
  productions all have length 1: the program bit at position k is the single
  production P[k] = program[k], and the production index advances every tick.

  This module provides the definitional simulator used to compute expected
  results for the runtime in-S5 interpreter (see _gen_bct.py and PLAN.md).
"""

from collections import deque


def simulate(program, data, max_ticks=None):
    """Return the full trace of data words (as lists of bits).

    The trace always begins with the initial data word; each subsequent entry
    is the data word after one tick.  The final entry is the empty word (the
    halting state).  If `max_ticks` is given, raise ValueError when the word
    has not emptied within that many ticks.
    """
    if not program:
        raise ValueError("a BCT program must be non-empty")
    n = len(program)
    word = deque(data)
    trace = [list(word)]
    m = 0
    while word:
        if max_ticks is not None and len(trace) - 1 >= max_ticks:
            raise ValueError(f"did not halt within {max_ticks} ticks")
        bit = word.popleft()
        if bit == "1":
            word.append(program[m])
        m = (m + 1) % n
        trace.append(list(word))
    return trace


def steps(program, data, max_ticks=None):
    """Number of ticks before the data string empties.

    Raises ValueError when the machine does not halt within `max_ticks` ticks.
    """
    return len(simulate(program, data, max_ticks=max_ticks)) - 1


def peak_word_length(program, data, max_ticks=None):
    """Largest data length reached during the run (>= len(data))."""
    return max(len(w) for w in simulate(program, data, max_ticks=max_ticks))