"""Euler/derivative and bounded feasible-sizing known-answer checks."""

from dataclasses import replace
import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from quantedge.contracts import CANONICAL_TICKERS, PortfolioConstraints, StrategySpec
from quantedge.es import empirical_var_and_es
from quantedge.risk_budget import risk_contributions, compare_feasible_allocations
from quantedge.var import estimate_risk, get_risk_forecaster


def inputs():
    rng = np.random.default_rng(871)
    a = rng.normal(0, .01, (240, 7)) + np.arange(7)*.0001
    return pd.DataFrame(a, index=pd.bdate_range("2010-01-04", periods=240), columns=CANONICAL_TICKERS), pd.Series(1/7, index=CANONICAL_TICKERS)


@pytest.mark.parametrize("method", ["normal_var", "normal_es", "historical_es"])
def test_euler_total_and_separate_finite_difference_derivatives(method):
    x, w = inputs()
    before_x, before_w = x.copy(), w.copy()
    out = risk_contributions(x, w, confidence=.95, method=method)
    mean = np.mean(x.to_numpy(), axis=0)
    covariance = np.cov(x.to_numpy(), rowvar=False, ddof=1)
    def oracle(v):
        if method == "historical_es":
            losses = sorted(-(x.to_numpy() @ v), reverse=True)
            return math.fsum(losses[:12])/12
        factor = norm.ppf(.95) if method == "normal_var" else norm.pdf(norm.ppf(.95))/.05
        return -mean@v + factor*math.sqrt(v@covariance@v)
    assert float(out.component_risk.sum()) == pytest.approx(oracle(w.to_numpy()), abs=1e-13)
    assert float(out.pct_contribution.sum()) == pytest.approx(1, abs=1e-12)
    for i in range(7):
        h = 1e-7
        plus, minus = w.to_numpy().copy(), w.to_numpy().copy()
        plus[i] += h
        minus[i] -= h
        derivative = (oracle(plus)-oracle(minus))/(2*h)
        assert out.iloc[i].marginal_risk == pytest.approx(derivative, abs=2e-9)
    pd.testing.assert_frame_equal(x,before_x)
    pd.testing.assert_series_equal(w,before_w)


def test_historical_ties_fractional_tail_and_negative_hedge_components():
    a = np.zeros((10,7));a[:,0]=[-.03,-.02,-.02,.01,.01,.02,.01,.01,.01,.01];a[:,3]=-a[:,0]*.5
    x=pd.DataFrame(a,index=pd.bdate_range("2010-01-04",periods=10),columns=CANONICAL_TICKERS)
    w=pd.Series(0.,index=CANONICAL_TICKERS);w.SPY=.8;w.AGG=.2
    out=risk_contributions(x,w,confidence=.85,method="historical_es")
    assert out.loc[out.ticker=="AGG","component_risk"].iloc[0]<0
    total=empirical_var_and_es(-(x@w),.85)[1]
    assert float(out.component_risk.sum())==pytest.approx(total,abs=1e-14)
    assert float(out.loc[out.ticker=="SPY","pct_contribution"].iloc[0])>1


@pytest.mark.parametrize("method", ["normal_var","normal_es","historical_es"])
def test_nonpositive_risk_does_not_invent_percentages(method):
    x,w=inputs();x.iloc[:,:]=.001
    out=risk_contributions(x,w,confidence=.99,method=method)
    assert out.total_risk.iloc[0]==pytest.approx(-.001)
    assert out.pct_contribution.isna().all()
    assert out.component_risk.sum()==pytest.approx(-.001)


def test_risky_assets_cancelling_zero_variance_do_not_claim_a_gradient():
    x,w=inputs();v=np.linspace(-.01,.01,len(x));x.iloc[:,:]=0;x.SPY=v;x.AGG=-v
    w[:]=0;w.SPY=.5;w.AGG=.5
    out=risk_contributions(x,w,confidence=.99,method="normal_es")
    assert out.marginal_risk.isna().all() and out.status.eq("unavailable").all()


def test_sizing_feasibility_null_limits_and_actual_cap_breaches():
    x,w=inputs()
    base=pd.Series([.2,0,0,.4,.4,0,0],index=CANONICAL_TICKERS)
    alt=pd.Series([.35,0,0,.4,.25,0,0],index=CANONICAL_TICKERS)
    candidates={"baseline":base,"alt":alt,"invalid_reference":w}
    limits={"constraints":PortfolioConstraints(),"baseline_id":"baseline","confidence":.99}
    out=compare_feasible_allocations(x,candidates,limits,get_risk_forecaster("historical"))
    assert list(out.constraint_feasible)==[True,True,False]
    assert out.risk_limits_met.isna().all()
    assert out.iloc[0].weight_change=={t:0. for t in CANONICAL_TICKERS}
    assert out.iloc[0].reduction_es_loss==0
    for i,weights in enumerate([base,alt,w]):
        est=estimate_risk(x,weights,model="historical",confidence=.99)
        assert out.iloc[i].es_loss==est.es_loss
        assert out.iloc[i].expected_annual_return_proxy==pytest.approx(252*float(x.mean()@weights))
    capped=compare_feasible_allocations(x,candidates,{**limits,"max_es_loss":0.0},get_risk_forecaster("historical"))
    assert capped.feasible_under_supplied_tests.eq(False).all()
    assert capped.risk_limits_met.eq(False).all()


def test_sizing_handles_bad_candidate_and_preserves_constraint_authority():
    x,w=inputs();good=pd.Series([.2,0,0,.4,.4,0,0],index=CANONICAL_TICKERS)
    conflict=StrategySpec("bad","equal_weight",constraints=replace(PortfolioConstraints(),max_weight_per_etf=.8))
    out=compare_feasible_allocations(x,{"good":good,"wrong_order":w.iloc[::-1],"conflict":conflict},
        {"constraints":PortfolioConstraints()},get_risk_forecaster("historical"))
    assert list(out.status)==["ok","unavailable","unavailable"]
    with pytest.raises(ValueError):
        compare_feasible_allocations(x,{"good":good},{"max_es_loss":.01},get_risk_forecaster("historical"))
    with pytest.raises(ValueError):
        risk_contributions(x,w,confidence=.95,method="unsupported")
