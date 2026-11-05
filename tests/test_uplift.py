import numpy as np
import pytest

from src import uplift

# Четыре клиента по убыванию скора: A (t=1, y=1), B (t=0, y=0), C (t=1, y=0), D (t=0, y=1).
# Q(1) = 1, Q(2) = 1 - 0 * 1/1 = 1, Q(3) = 1 - 0 * 2/1 = 1, Q(4) = 1 - 1 * 2/2 = 0.
Y = np.array([1, 0, 0, 1])
T = np.array([1, 0, 1, 0])
S = np.array([4, 3, 2, 1])


def test_qini_curve_by_hand():
    x, q = uplift.qini_curve(Y, T, S)
    assert x.tolist() == [0, 1, 2, 3, 4]
    assert q.tolist() == [0, 1, 1, 1, 0]


def test_qini_curve_groups_ties():
    x, q = uplift.qini_curve(Y, T, np.array([2, 2, 1, 1]))
    assert x.tolist() == [0, 2, 4]
    assert q.tolist() == [0, 1, 0]


def test_qini_area_by_hand():
    # площадь под [0, 1, 1, 1, 0] = 3, случайная линия идёт в (4, 0) и площади не даёт: 3 / 4
    assert uplift.qini_area(Y, T, S) == pytest.approx(0.75)


def test_perfect_score_gives_qini_one():
    rng = np.random.default_rng(0)
    y, t = rng.integers(0, 2, 500), rng.integers(0, 2, 500)
    assert uplift.qini_coef(y, t, y * t - y * (1 - t)) == pytest.approx(1)


def test_uplift_at_k_by_hand():
    u, n_t, n_c = uplift.uplift_at_k(Y, T, S, 0.5)
    assert (u, n_t, n_c) == (1.0, 1, 1)
    u, n_t, n_c = uplift.uplift_at_k(Y, T, S, 0.75)
    assert u == pytest.approx(0.5) and (n_t, n_c) == (2, 1)


def test_random_score_has_qini_near_zero():
    rng = np.random.default_rng(1)
    n = 50_000
    t = rng.integers(0, 2, n)
    y = (rng.random(n) < 0.6 + 0.03 * t).astype(int)
    assert abs(uplift.qini_coef(y, t, rng.random(n))) < 0.05


def test_matches_sklift():
    sklift = pytest.importorskip("sklift.metrics")
    rng = np.random.default_rng(2)
    n = 5_000
    x = rng.normal(size=n)
    t = rng.integers(0, 2, n)
    y = (rng.random(n) < 0.5 + 0.1 * t * (x > 0)).astype(int)
    score = np.round(x + rng.normal(scale=0.5, size=n), 1)  # с повторами скоров
    x1, q1 = uplift.qini_curve(y, t, score)
    x2, q2 = sklift.qini_curve(y, score, t)
    assert np.array_equal(x1, x2) and np.allclose(q1, q2)
    assert uplift.qini_coef(y, t, score) == pytest.approx(sklift.qini_auc_score(y, score, t))
    for k in (0.1, 0.2, 0.3):
        assert uplift.uplift_at_k(y, t, score, k)[0] == pytest.approx(
            sklift.uplift_at_k(y, score, t, strategy="overall", k=k)
        )


def test_bootstrap_is_paired_and_keeps_group_sizes():
    rng = np.random.default_rng(3)
    n = 2_000
    t = rng.integers(0, 2, n)
    y = rng.integers(0, 2, n)
    s = rng.random(n)
    boot = uplift.bootstrap(y, t, {"a": s, "b": s}, n_boot=20, seed=0)
    a = boot[boot.model == "a"].set_index("rep")
    b = boot[boot.model == "b"].set_index("rep")
    assert np.allclose(a.qini, b.qini)
    assert boot.rep.nunique() == 20
