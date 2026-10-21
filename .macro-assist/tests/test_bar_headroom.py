"""The bar-headroom harness (KB-038). What it must never do: read a sealed
day. What it must do: a rho of 1 is foresight, and a rho of 0 is noise."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import bar_headroom as bh


def test_perfect_foresight_fires_on_the_top_share_of_the_target():
    target = np.arange(100, dtype=float)
    fire = bh.synthetic(target, rho=1.0, share=0.2, seed=0)
    assert fire.sum() == 20 and fire[80:].all()


def test_no_foresight_is_unrelated_to_the_target():
    target = np.arange(5000, dtype=float)
    fire = bh.synthetic(target, rho=0.0, share=0.2, seed=0)
    assert abs(fire[:2500].mean() - fire[2500:].mean()) < 0.03


def test_forward_targets_look_only_after_the_month_end():
    eq = np.zeros(30)
    eq[10] = -0.2                                     # one fall, on day 10
    ends = np.array([5, 15])
    assert bh.forward_drop(eq, ends, horizon=10)[0] == pytest.approx(0.2)
    assert bh.forward_drop(eq, ends, horizon=10)[1] == 0.0
    assert bh.forward_return(eq, ends, horizon=10)[0] == pytest.approx(np.log(0.8))


def test_the_market_never_reaches_the_seal(tmp_path, monkeypatch):
    idx = pd.bdate_range("2017-12-20", "2018-01-10")
    fac = pd.DataFrame({"Mkt-RF": 0.001, "RF": 0.0001}, index=idx)
    (tmp_path / "inputs.pkl").write_bytes(pd.io.pickle.pickle.dumps({"factors": fac}))
    monkeypatch.setattr(bh, "RESULTS_DIR", tmp_path)
    dates, eq, rf = bh.load_market()
    assert dates[-1] < bh.SEAL_START.isoformat() and len(eq) == len(rf) == len(dates)
