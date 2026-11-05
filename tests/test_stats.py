import numpy as np
import pytest

from src import stats


def test_srm_exact_split_has_p_one():
    chi2, p = stats.srm(500, 500)
    assert chi2 == 0
    assert p == pytest.approx(1)


def test_srm_known_value():
    # (550 - 500)^2 / 500 + (450 - 500)^2 / 500 = 10
    chi2, p = stats.srm(550, 450)
    assert chi2 == pytest.approx(10)
    assert p == pytest.approx(0.001565, abs=1e-6)


def test_smd():
    assert stats.smd(1.0, 0.0, 4.0, 4.0) == pytest.approx(0.5)
    assert stats.smd(0.5, 0.4, 0.25, 0.24) == pytest.approx(0.1 / np.sqrt(0.245))


def test_diff_props_ci():
    d, lo, hi = stats.diff_props_ci(60, 100, 50, 100)
    se = np.sqrt(0.6 * 0.4 / 100 + 0.5 * 0.5 / 100)
    assert d == pytest.approx(0.1)
    assert lo == pytest.approx(0.1 - 1.959964 * se, rel=1e-6)
    assert hi == pytest.approx(0.1 + 1.959964 * se, rel=1e-6)


def test_prop_ci():
    p, lo, hi = stats.prop_ci(25, 100)
    assert p == 0.25
    assert hi - lo == pytest.approx(2 * 1.959964 * np.sqrt(0.25 * 0.75 / 100), rel=1e-6)


def test_bootstrap_matches_normal_on_large_sample():
    rng = np.random.default_rng(0)
    y_t = rng.random(20_000) < 0.64
    y_c = rng.random(20_000) < 0.60
    d, lo, hi = stats.bootstrap_diff(y_t, y_c, n_boot=500, seed=1)
    _, nlo, nhi = stats.diff_props_ci(y_t.sum(), y_t.size, y_c.sum(), y_c.size)
    assert d == pytest.approx(y_t.mean() - y_c.mean())
    assert lo == pytest.approx(nlo, abs=0.002)
    assert hi == pytest.approx(nhi, abs=0.002)
