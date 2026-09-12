"""Reference Cyclic Tag simulator (machine model), independent of S5.

Cyclic Tag (Minsky-style tag completion / the standard definition):

  A machine is a finite list of productions P[0..n-1], each a string of
  bits, together with a data word (initial string of bits).  A computation
  is a sequence of instantaneous descriptions (data words) obtained by
  repeatedly executing one tick:

    * let m be the current production index (initially 0);
    * if the data word is empty, halt;
    * read and delete its first bit `b`;
    * if b == 1, append production P[m] to the end of the data word;
    * advance m to (m + 1) mod n.

  This module provides the definitional simulator used to compute expected
  results for the in-S5 implementation (see _gen_ctag.py and PLAN.md).
"""

from collections import deque


def simulate(productions, data):
    """Return the full trace of data words (as lists of bits).

    The trace always begins with the initial data word; each subsequent
    entry is the data word after one tick.  The final entry is the empty
    word (the halting state).
    """
    if len(productions) == 0:
        raise ValueError("a cyclic tag machine needs at least one production")
    word = deque(data)
    trace = [list(word)]
    m = 0
    while word:
        bit = word.popleft()
        if bit == "1":
            word.extend(productions[m])
        m = (m + 1) % len(productions)
        trace.append(list(word))
    return trace


def steps(productions, data):
    """Number of ticks before the data word empties."""
    return len(simulate(productions, data)) - 1


def buffer_usage(productions, data):
    """Total number of buffer slots the linear-buffer model needs.

    The linear-buffer model in _gen_ctag.py never wraps or reuses a slot:
    the head pointer only advances when a bit is deleted, and the tail
    pointer only advances when a production bit is appended.  The highest
    slot ever written is therefore the length of the initial word plus
    every production bit ever appended.  The generator refuses to emit a
    program when this exceeds the buffer capacity.
    """
    word = deque(data)
    tail = len(word)
    m = 0
    while word:
        bit = word.popleft()
        if bit == "1":
            word.extend(productions[m])
            tail += len(productions[m])
        m = (m + 1) % len(productions)
    return tail