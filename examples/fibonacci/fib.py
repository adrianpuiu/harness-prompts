"""Deliberately wrong seed for the harness example."""

from __future__ import annotations


def fib(n: int) -> int:
    if n < 0:
        raise ValueError("n must be non-negative")
    # BUG: base case should be 0 for n == 0.
    if n <= 1:
        return 1
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
