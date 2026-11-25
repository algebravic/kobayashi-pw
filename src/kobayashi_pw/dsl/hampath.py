"""Secondary costs of the hampath frontier DP, as DSL specs (doc/dsl_secondary_design.md §A8).

The features are those of ``kobayashi_pw.orders.tau_block_features``, written in
the IR.  T is the placed prefix (τ direction) and v the vertex placed:

    F(T)   = {u ∈ T : u has a neighbour outside T}     (Kinnersley's frontier)
    fw     = |F(T + v)|,   fw_before = |F(T)|
    n_back = |N(v) ∩ T ∩ F(T + v)|
    n_elim = |F(T) ∖ F(T + v)| + [v isolated]
    e_bag  = Σ_{u ∈ F(T+v)} |N(u) ∩ F(T+v)| / 2
    lbc    = Σ over components C of G[F(T+v)] of log Bell(|C|)

``orders.model_v2``, ``orders.make_model_v7`` and ``orders.make_model_loglin``
remain the reference semantics; tests/test_dsl_secondary.py checks that these
specs give the same step values and the same optima.
"""
from __future__ import annotations

import math

from . import lemma
from .ir import (FULL, N, SetE, bigunion, card, comp_sum, isum, param, real, rexp, rmax, rpow, single,
                 table, where, width, nverts)
from .problem import Problem
from ..orders import BELL, WORK_FEATURES

LOGBELL = [math.log(b) for b in BELL]


def frontier(T):
    """F(T) = T ∩ ⋃_{u ∉ T} N(u)."""
    return T & bigunion(SetE(FULL) - T, N)


def step_features(T, v):
    """(fw, fw_before, n_back, n_elim, e_bag, lbc) of one τ-step, as IR values."""
    T1 = T | single(v)
    F0, F1 = frontier(T), frontier(T1)
    fw, fw0 = card(F1), card(F0)
    nb = card(N(v) & T & F1)
    nelim = card(F0 - F1) + where(card(N(v)) == 0, 1, 0)
    ebag = isum(F1, lambda u: card(N(u) & F1)) // 2
    lbc = comp_sum(F1, lambda s: table("logbell", s))
    return fw, fw0, nb, nelim, ebag, lbc


def add_v2(P: Problem, name: str = "v2") -> Problem:
    """V2 (additive): Σ 2^nb (fw/pw)^2 + 0.001 fw."""
    def step(T, v):
        fw, _, nb, *_ = step_features(T, v)
        q = real(fw) / real(imax1(width()))
        return rpow(2.0, nb) * q * q + 0.001 * real(fw), 0.0, 0.0
    return P.secondary(step, name=name, by=lemma.additive)


def imax1(x):
    from .ir import imax
    return imax(x, 1)


def add_v7(P: Problem, name: str = "v7") -> Problem:
    """V7 (ham_ordering._dp_cost): parameters base (expand_base) and alpha (density_alpha)."""
    P.table("logbell", LOGBELL)
    P.param("base", 1, nonneg=True)
    P.param("alpha", 1, nonneg=True)

    def step(T, v):
        fw, _, nb, nelim, ebag, lbc = step_features(T, v)
        q = real(fw) / real(imax1(width()))
        corr = rexp(0.5 * (rmax(lbc, 0.0) - rmax(table("logbell", fw), 0.0)))
        dens = where(fw > 0, 1.0 + param("alpha") * real(ebag) / real(imax1(fw)), 1.0)
        e = rpow(param("base"), nb) * q * q * corr * dens
        return 0.001 * real(fw), e, rmax(rpow(0.5, nelim), 0.01)
    return P.secondary(step, name=name, by=lemma.pareto_monotone)


def add_loglin(P: Problem, name: str = "work", pname: str = "beta") -> Problem:
    """Predicted DP work: a = 0, e = 2^nb, k = exp(β·x)/2^nb with x = orders.WORK_FEATURES;
    β is the runtime parameter vector `pname` (11 values)."""
    P.table("logbell", LOGBELL)
    P.param(pname, len(WORK_FEATURES))

    def step(T, v):
        fw, fw0, nb, nelim, ebag, lbc = step_features(T, v)
        x = [1.0, nb, nelim, fw, fw0, ebag, lbc, nb * fw, nelim * fw0, nb * nb,
             real(card(T)) / real(imax1(nverts() - 1))]
        g = sum(param(pname, i) * x[i] for i in range(len(WORK_FEATURES)))
        e = rpow(2.0, nb)
        return 0.0, e, rexp(g) / e
    return P.secondary(step, name=name, by=lemma.pareto_monotone)


def hampath_costs(greedy2: bool = False, costs=("v2", "v7", "work")) -> Problem:
    """vertex_separation with the hampath secondary costs attached."""
    from .specs import vertex_separation
    P = vertex_separation(greedy2)
    if "v2" in costs:
        add_v2(P)
    if "v7" in costs:
        add_v7(P)
    if "work" in costs:
        add_loglin(P)
    return P
