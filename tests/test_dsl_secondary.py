"""Secondary costs in the DSL: engine E2 (doc/dsl_secondary_design.md, Part A)."""

import itertools
import json
import math
import random
import subprocess

import pytest

from kobayashi_pw import from_edges, native
from kobayashi_pw.dsl import lemma
from kobayashi_pw.dsl.hampath import add_loglin, add_v2, add_v7, hampath_costs
from kobayashi_pw.dsl.ir import N, card, param, real, rpow
from kobayashi_pw.dsl.specs import vertex_separation
from kobayashi_pw.orders import (OrderDAG, WORK_FEATURES, make_model_loglin, make_model_v7, model_v2,
                                 optimize, optimize_file)

C_OK = native.compiler() is not None
MODES = ["eager", "c"] if C_OK else ["eager"]
RNG = random.Random(11)
BETA = [RNG.uniform(-0.3, 0.6) for _ in WORK_FEATURES]
PARAMS = {"base": [1.55], "alpha": [0.25], "beta": BETA}


def sq(n):
    E = [(u, v) for u in range(1, n + 1) for v in range(u + 1, n + 1) if math.isqrt(u + v) ** 2 == u + v]
    return from_edges(E, range(1, n + 1))


def random_graph(rng, n, p):
    E = [(i, j) for i, j in itertools.combinations(range(n), 2) if rng.random() < p]
    return from_edges(E, range(n))


@pytest.fixture(scope="module")
def P():
    return hampath_costs()


def references(n):
    return {"v2": model_v2, "v7": make_model_v7(1.55, 0.25), "work": make_model_loglin(BETA, n)}


@pytest.mark.parametrize("seed", [1, 2])
def test_e2_equals_brute_force_over_all_paths(P, seed):
    rng = random.Random(seed)
    beta = [rng.uniform(-0.3, 0.8) for _ in WORK_FEATURES]
    params = {"base": [rng.uniform(1.0, 2.5)], "alpha": [rng.uniform(0, 1)], "beta": beta}
    assert P.check_secondary(params, n_max=10, trials=40, seed=seed, modes=MODES) >= 100


def test_pareto_fronts_are_exercised(P):
    """The brute-force test is only meaningful if fronts with several labels occur."""
    rng = random.Random(4)
    seen = 0
    for _ in range(40):
        g = random_graph(rng, rng.randint(8, 12), rng.uniform(0.2, 0.5))
        s = P.solve(g, mode="eager", output="pareto", secondary="work", params=PARAMS)
        seen = max(seen, s.stats["max_labels"])
    assert seen > 1


@pytest.mark.parametrize("n", [16, 20, 25, 30])
@pytest.mark.parametrize("mode", MODES)
def test_equals_orders_optimize(P, n, mode):
    g = sq(n)
    dag = OrderDAG.build(g)
    for name, model in references(n).items():
        r = optimize(dag, model)
        s = P.solve(g, mode=mode, output="pareto", secondary=name, params=PARAMS)
        assert s.width == dag.pw
        assert s.secondary_cost == pytest.approx(r.cost, rel=1e-12)
        assert s.order == r.tau


@pytest.mark.skipif(not C_OK, reason="no C compiler")
@pytest.mark.parametrize("n", [40, 45])
def test_equals_kopt(P, n, tmp_path):
    g = sq(n)
    ef, df = tmp_path / "g.txt", tmp_path / "g.dag"
    ef.write_text("\n".join(f"{u} {v}" for v in range(g.n) for u in range(v) if g.nin[v] >> u & 1) + "\n")
    subprocess.run([native.program("kpw", n), "-q", "-c", "-o", str(df), str(ef)], check=True, capture_output=True)
    for name, kc in (("v2", "v2"), ("v7", "v7"), ("work", "loglin")):
        rk = optimize_file(str(df), kc, beta=BETA)
        s = P.solve(g, mode="c", output="pareto", secondary=name, params=PARAMS)
        assert s.secondary_cost == pytest.approx(rk.cost, rel=1e-12)
        assert s.order == [g.labels[v] for v in rk.tau]


@pytest.mark.parametrize("mode", MODES)
def test_truncation_is_flagged(P, mode):
    rng = random.Random(8)
    for _ in range(40):
        g = random_graph(rng, 11, 0.35)
        full = P.solve(g, mode=mode, output="pareto", secondary="work", params=PARAMS)
        if full.stats["max_labels"] > 1:
            cut = P.solve(g, mode=mode, output="pareto", secondary="work", params=PARAMS, max_labels=1)
            assert not cut.exact and cut.secondary_cost >= full.secondary_cost * (1 - 1e-12)
            return
    pytest.skip("no graph with a front of several labels")


def test_lemma_checks():
    P = vertex_separation()
    with pytest.raises(ValueError):                                   # additive needs e = 0
        P.secondary(lambda T, v: (0.0, real(card(T)), 1.0), name="bad", by=lemma.additive)
    P.param("c", 1)                                                    # sign unknown
    P.secondary(lambda T, v: (0.0, param("c"), 1.0), name="unknown", by=lemma.pareto_monotone)
    assert P.secondaries["unknown"].status.startswith("assumed")
    P2 = hampath_costs()
    for name in ("v2", "v7", "work"):
        assert P2.secondaries[name].status == "checked"
    assert "secondary" in P2.report() and "secondary v7" in P2.pretty()


def test_parameter_validation(P):
    g = sq(15)
    with pytest.raises(ValueError):
        P.solve(g, mode="eager", output="pareto", secondary="v7", params={"base": [1.5], "alpha": [0.2]})
    with pytest.raises(ValueError):
        P.solve(g, mode="eager", output="pareto", secondary="v7", params=dict(PARAMS, base=[1.5, 2.0]))
    with pytest.raises(ValueError):
        P.solve(g, mode="eager", output="pareto", secondary="v7", params=dict(PARAMS, alpha=[-0.1]))


@pytest.mark.skipif(not C_OK, reason="no C compiler")
def test_parameters_do_not_recompile(P):
    from kobayashi_pw.dsl import jit
    g = sq(30)
    P.solve(g, mode="c", output="pareto", secondary="work", params=PARAMS)
    before = len(jit._loaded)
    P.solve(g, mode="c", output="pareto", secondary="work", params=dict(PARAMS, beta=[b * 0.9 for b in BETA]))
    assert len(jit._loaded) == before
