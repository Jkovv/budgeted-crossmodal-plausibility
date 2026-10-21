import numpy as np
import pandas as pd
import pytest

from bcp.delta import DeltaCheck, robust_sd


def _series(values, field="sodium", subject=1):
    return pd.DataFrame(dict(subject_id=subject, field=field, modality="lab", visit_idx=range(len(values)),
                             value=values))


def test_robust_sd_of_normal_data():
    x = np.random.default_rng(0).normal(0, 3, 20000)
    assert robust_sd(x) == pytest.approx(3, rel=0.03)


def test_delta_scores_change_over_sd():
    train = pd.concat([_series([140, 141, 139, 140, 142], subject=s) for s in range(5)], ignore_index=True)
    test = _series([140, 150, 150])
    d = DeltaCheck().fit(train)
    sd = d.sd["sodium"]
    s = d.score(test)
    assert np.isnan(s[0])                                   # no previous value
    assert s[1] == pytest.approx(10 / sd) and s[2] == 0


def test_dates_are_not_scored():
    c = _series([1000, 1001]).assign(field="lab_date", modality="date")
    d = DeltaCheck().fit(_series([140, 141]))
    assert np.isnan(d.score(c)).all()
