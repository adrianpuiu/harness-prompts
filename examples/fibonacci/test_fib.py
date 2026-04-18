from __future__ import annotations

import pytest

from fib import fib


@pytest.mark.parametrize(
    ("n", "expected"),
    [(0, 0), (1, 1), (2, 1), (3, 2), (10, 55)],
)
def test_fib_values(n: int, expected: int) -> None:
    assert fib(n) == expected


def test_fib_negative_raises() -> None:
    with pytest.raises(ValueError):
        fib(-1)
