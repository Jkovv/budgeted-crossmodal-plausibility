import numpy as np
import pytest

from bcp import inject as I


def outcomes(fn, *args, n=200):
    rng = np.random.default_rng(0)
    return {fn(*args, rng) for _ in range(n)}


@pytest.mark.parametrize("value,dec,expected", [
    (142, 0, {124.0, 412.0}),
    (4.6, 1, {6.4}),
    (0.9, 1, {9.0}),
    (1.25, 2, {2.15, 1.52}),
    (37.2, 1, {73.2, 32.7}),
])
def test_transpose_digits(value, dec, expected):
    assert outcomes(I.transpose_digits, value, dec) == expected


@pytest.mark.parametrize("value,dec", [(11, 0), (1.1, 1), (5, 0), (2.22, 2)])
def test_transpose_digits_not_applicable(value, dec):
    assert outcomes(I.transpose_digits, value, dec) == {None}


def test_transpose_digits_keeps_the_decimal_point():
    rng = np.random.default_rng(1)
    for v, dec in [(123.4, 1), (9.87, 2), (45.6, 1), (0.45, 2)]:
        new = I.transpose_digits(v, dec, rng)
        assert new is not None and new != v
        assert len(f"{new:.{dec}f}") == len(f"{v:.{dec}f}")      # same digits, same position of the point


@pytest.mark.parametrize("value,dec,expected", [
    (4.1, 1, {41.0, 0.41}),
    (98, 0, {980.0, 9.8}),
    (1.25, 2, {12.5, 0.125}),
])
def test_decimal_slip(value, dec, expected):
    assert outcomes(I.decimal_slip, value, dec) == expected


def test_decimal_slip_directions_are_balanced():
    rng = np.random.default_rng(2)
    ups = sum(I.decimal_slip(10.0, 0, rng) == 100.0 for _ in range(4000))
    assert 1850 < ups < 2150
