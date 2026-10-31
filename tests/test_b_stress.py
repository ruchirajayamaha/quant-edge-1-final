"""Stress known-answer buy-and-hold path, attribution and explicit failure checks."""

import numpy as np
import pandas as pd
import pytest

from quantedge.contracts import CANONICAL_TICKERS, StressScenarioSpec
from quantedge.stress import run_stress_tests


def sample():
    dates=pd.to_datetime(["2015-01-02","2015-01-05","2015-01-06"])
    x=pd.DataFrame(0.,index=dates,columns=CANONICAL_TICKERS)
    x.SPY=[-.2,.1,-.1];x.AGG=[.1,-.1,.1]
    w=pd.Series([.5,0,0,.5,0,0,0],index=CANONICAL_TICKERS,name="test")
    return x,w


def test_actual_buy_hold_drift_start_day_anchor_and_asset_pnl_add_up():
    x,w=sample();copy=x.copy();before=w.copy()
    s=StressScenarioSpec("toy","toy","historical","2015-01-02","2015-01-06")
    out=run_stress_tests(x,w,[s],nav=100)
    wealth=np.array([.5*.8+.5*1.1,.5*.8*1.1+.5*1.1*.9,.5*.8*1.1*.9+.5*1.1*.9*1.1])
    row=out.iloc[0]
    assert row.status=="ok"
    assert row.total_return==pytest.approx(wealth[-1]-1)
    assert row.usd_loss==pytest.approx(100*(1-wealth[-1]))
    assert row.max_drawdown==pytest.approx(min(wealth/np.maximum.accumulate(np.r_[1.,wealth])[1:]-1))
    assert row.worst_day_return==pytest.approx(min(wealth/np.r_[1.,wealth[:-1]]-1))
    assert not np.allclose(wealth,np.cumprod(1+x.to_numpy()@w.to_numpy())) # catches daily rebalancing
    attr=out.attrs['attributions']['toy']
    assert attr.return_contribution.sum()==pytest.approx(row.total_return)
    assert attr.usd_pnl.sum()==pytest.approx(-row.usd_loss)
    pd.testing.assert_frame_equal(x,copy);pd.testing.assert_series_equal(w,before)


@pytest.mark.parametrize("defect",["missing_day","nonfinite","below_minus_one","holiday_endpoint","truncated"])
def test_invalid_historical_scenario_is_unavailable_without_filling(defect):
    x,w=sample();start="2015-01-02";end="2015-01-06"
    if defect=="missing_day":x=x.drop(x.index[1])
    if defect=="nonfinite":x.iloc[1,0]=np.nan
    if defect=="below_minus_one":x.iloc[0,0]=-1.01
    if defect=="holiday_endpoint":start="2015-01-01"
    if defect=="truncated":end="2015-01-07"
    out=run_stress_tests(x,w,[StressScenarioSpec("toy","toy","historical",start,end)])
    assert out.iloc[0].status=="unavailable" and out.iloc[0].total_return is None
    assert out.iloc[0].note


def test_hypothetical_signed_pnl_and_all_seven_shocks_are_required():
    x,w=sample();shocks={t:0. for t in CANONICAL_TICKERS};shocks.update(SPY=-.25,AGG=.1)
    s=StressScenarioSpec("hyp","hyp","hypothetical",shocks=shocks,provisional=True)
    out=run_stress_tests(x,w,[s],nav=100)
    assert out.iloc[0].total_return==pytest.approx(-.075)
    assert out.iloc[0].usd_loss==pytest.approx(7.5)
    assert out.iloc[0].max_drawdown==pytest.approx(-.075)
    assert out.iloc[0].status=="warning" and "not ES" in out.iloc[0].note
    missing=StressScenarioSpec("bad","bad","hypothetical",shocks={"SPY":-.1})
    assert run_stress_tests(x,w,[missing]).iloc[0].status=="unavailable"


def test_scenario_gain_preserves_negative_usd_loss_and_zero_initial_drawdown():
    x,w=sample();s=StressScenarioSpec("gain","gain","hypothetical",shocks={t:.1 for t in CANONICAL_TICKERS})
    row=run_stress_tests(x,w,[s],nav=100).iloc[0]
    assert row.usd_loss==pytest.approx(-10) and row.max_drawdown==0
    with pytest.raises(ValueError):run_stress_tests(x,w,[s,s])
    with pytest.raises(ValueError):run_stress_tests(x,w,[s],nav=0)
