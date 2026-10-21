import numpy as np
import pytest
from scipy import stats as sps

from bcp import stats as S


def test_rank_order_sorts_and_breaks_ties_at_random():
    score = np.array([1.0, 3.0, np.nan, 3.0, 0.5])
    orders = {tuple(S.rank_order(score, np.random.default_rng(i))) for i in range(30)}
    assert orders == {(1, 3, 0, 4), (3, 1, 0, 4)}


def _brute_force(order, patient, err, visits, budget, w):
    """Expand duplicated patients and take the top Q cells literally."""
    expanded = [c for c in order for _ in range(int(w[patient[c]]))]
    Q = int(round(budget * (w @ visits)))
    top = expanded[:Q]
    return Q, len(top), sum(err[c] for c in top)


@pytest.mark.parametrize("seed", range(8))
def test_budget_counts_match_brute_force_resampling(seed):
    rng = np.random.default_rng(seed)
    n_pat, n_cells = 12, 80
    patient = rng.integers(n_pat, size=n_cells)
    err = rng.random(n_cells) < 0.2
    score = np.where(rng.random(n_cells) < 0.2, np.nan, rng.normal(size=n_cells) + 2 * err)
    visits = rng.integers(1, 5, size=n_pat).astype(float)
    order = S.rank_order(score, rng)
    W = S.patient_weights(n_pat, 6, rng)
    budgets = (0.1, 0.5, 2.0, 10.0)
    out = S.budget_counts(order, patient, {"err": err}, visits, budgets, W)
    for r in range(len(W)):
        for j, b in enumerate(budgets):
            Q, raised, tp = _brute_force(order, patient, err, visits, b, W[r])
            assert out["Q"][r, j] == Q
            assert out["raised"][r, j] == raised
            assert out["tp_err"][r, j] == pytest.approx(tp)
        assert out["n_err"][r, 0] == pytest.approx((W[r][patient] * err).sum())


def test_patient_weights_first_row_is_the_sample():
    W = S.patient_weights(10, 100, np.random.default_rng(0))
    assert (W[0] == 1).all() and W.shape == (101, 10)
    assert (W.sum(axis=1) == 10).all()


def test_conformal_pvalues():
    cal = np.array([0.1, 0.5, 0.5, 2.0])
    p = S.conformal_pvalues(cal, np.array([0.0, 0.5, 1.0, 5.0, np.nan]))
    assert p.tolist() == [1.0, 4 / 5, 2 / 5, 1 / 5, 1.0]


def test_conformal_pvalues_are_valid_for_exchangeable_inliers():
    rng = np.random.default_rng(1)
    hits = []
    for _ in range(400):
        cal, test = rng.normal(size=200), rng.normal(size=50)
        hits.append((S.conformal_pvalues(cal, test) <= 0.1).mean())
    assert np.mean(hits) <= 0.1 + 0.01


def _bh_reference(p, alpha):
    m = len(p)
    order = np.argsort(p)
    ok = np.flatnonzero(p[order] <= alpha * np.arange(1, m + 1) / m)
    rej = np.zeros(m, bool)
    if len(ok):
        rej[order[: ok.max() + 1]] = True
    return rej


@pytest.mark.parametrize("seed", range(6))
def test_bh_matches_the_textbook_procedure(seed):
    rng = np.random.default_rng(seed)
    p = np.concatenate([rng.uniform(size=60), rng.uniform(0, 0.01, size=10)])
    err = np.r_[np.zeros(60, bool), np.ones(10, bool)]
    out = S.bh_counts(p, {"err": err}, 0.1, np.ones((1, len(p))))
    ref = _bh_reference(p, 0.1)
    assert out["raised"][0] == ref.sum() and out["tp_err"][0] == (ref & err).sum()


def test_bh_with_weights_equals_duplicated_cells():
    rng = np.random.default_rng(7)
    p = rng.uniform(0, 0.2, size=30)
    w = rng.integers(0, 3, size=30)
    out = S.bh_counts(p, {"all": np.ones(30, bool)}, 0.2, w[None, :].astype(float))
    dup = np.repeat(p, w)
    assert out["raised"][0] == _bh_reference(dup, 0.2).sum()


def test_bh_controls_fdr_on_conformal_pvalues():
    rng = np.random.default_rng(3)
    fdp = []
    for _ in range(300):
        cal = rng.normal(size=500)
        inl, out = rng.normal(size=180), rng.normal(3.5, 1, size=20)
        p = S.conformal_pvalues(cal, np.r_[inl, out])
        is_out = np.r_[np.zeros(180, bool), np.ones(20, bool)]
        r = S.bh_counts(p, {"false": ~is_out}, 0.1, np.ones((1, 200)))
        fdp.append(r["tp_false"][0] / max(r["raised"][0], 1))
    assert np.mean(fdp) <= 0.1 + 0.015


def test_spearman_permutation():
    rng = np.random.default_rng(4)
    x = np.arange(20.0)
    rho, p = S.spearman_permutation(x, -x + rng.normal(0, 3, 20), 2000, rng)
    assert rho == pytest.approx(sps.spearmanr(x, -x + 0).statistic, abs=0.3) and p < 0.01
    _, p_null = S.spearman_permutation(x, rng.normal(size=20), 2000, rng)
    assert p_null > 0.05


def test_index_of_individuality():
    rng = np.random.default_rng(5)
    patient = np.repeat(np.arange(200), 6)
    tight = np.repeat(rng.normal(0, 10, 200), 6) + rng.normal(0, 1, 1200)   # within 1, between 10
    loose = np.repeat(rng.normal(0, 1, 200), 6) + rng.normal(0, 3, 1200)
    assert S.index_of_individuality(tight, patient) == pytest.approx(0.1, abs=0.03)
    assert S.index_of_individuality(loose, patient) > 1.5
