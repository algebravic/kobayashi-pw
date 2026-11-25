"""kopt (src/C/kopt.c) against the Python optimiser and brute force."""

import itertools
import math
import os
import random
import subprocess

import pytest

from kobayashi_pw import from_edges
from kobayashi_pw.orders import (OrderDAG, WORK_FEATURES, evaluate, find_kopt,
                                 make_model_loglin, make_model_v7, model_v2, optimize,
                                 optimize_file)

from kobayashi_pw.native import try_program
KPW = try_program("kpw") or os.path.join(os.path.dirname(__file__), "..", "src", "C", "kpw")
pytestmark = pytest.mark.skipif(find_kopt() is None or not os.path.isfile(KPW),
                                reason="kopt or kpw unavailable (no C compiler)")


def random_graph(rng, n, p):
    E = [(i, j) for i, j in itertools.combinations(range(n), 2) if rng.random() < p]
    return from_edges(E, range(n))


def dump(g, tmp_path, greedy2=False):
    ef, df = tmp_path / "g.txt", tmp_path / "g.dag"
    lines = [str(v) for v in range(g.n)]
    lines += [f"{u} {v}" for v in range(g.n) for u in range(v) if g.nin[v] >> u & 1]
    ef.write_text("\n".join(lines) + "\n")
    subprocess.run([KPW, "-q", "-c", "-o", str(df)] + (["-g"] if greedy2 else []) + [str(ef)],
                   check=True, capture_output=True)
    return str(df)


def models(rng, n):
    beta = [rng.uniform(-0.5, 0.5) for _ in WORK_FEATURES]
    return [("v2", model_v2, {}),
            ("v7", make_model_v7(1.7, 0.4), {"expand_base": 1.7, "density_alpha": 0.4}),
            ("loglin", make_model_loglin(beta, n), {"beta": beta})]


def all_paths(dag):
    def rec(S):
        if S == dag.full:
            yield []
            return
        for T, blk in dag.arcs[S]:
            for rest in rec(T):
                yield [blk] + rest
    for p in rec(dag.S0):
        yield [dag.g.labels[v] for v in dag._sigma_from_path(p)[::-1]]


@pytest.mark.parametrize("greedy2", [False, True])
def test_kopt_equals_python_and_brute_force(tmp_path, greedy2):
    rng = random.Random(11 + greedy2)
    checked = 0
    for _ in range(60):
        n = rng.randint(4, 13)
        g = random_graph(rng, n, rng.uniform(0.15, 0.5))
        path = dump(g, tmp_path, greedy2)
        dag = OrderDAG.load(path)
        paths = list(all_paths(dag)) if dag.num_orderings() <= 2000 else None
        for name, model, kw in models(rng, n):
            rc = optimize_file(path, name, **kw)
            rp = optimize(dag, model)
            assert rc.exact and rp.exact
            assert rc.cost == pytest.approx(rp.cost, rel=1e-9, abs=1e-12)
            assert evaluate(dag.g, rc.tau, model, dag.pw) == pytest.approx(rc.cost, rel=1e-9, abs=1e-12)
            if paths is not None:
                best = min(evaluate(dag.g, t, model, dag.pw) for t in paths)
                assert rc.cost == pytest.approx(best, rel=1e-9, abs=1e-12)
                checked += 1
    assert checked >= 50


def test_kopt_truncation_flag(tmp_path):
    rng = random.Random(3)
    for _ in range(30):
        n = rng.randint(10, 16)
        g = random_graph(rng, n, 0.3)
        path = dump(g, tmp_path)
        beta = [rng.uniform(-0.5, 0.5) for _ in WORK_FEATURES]
        full = optimize_file(path, "loglin", beta=beta)
        if full.max_labels > 1:
            cut = optimize_file(path, "loglin", beta=beta, max_labels=1)
            assert not cut.exact and cut.max_labels == 1
            assert cut.cost >= full.cost * (1 - 1e-12)
            return
    pytest.skip("no graph with more than one label")


def test_kopt_rejects_bad_arguments(tmp_path):
    g = random_graph(random.Random(1), 8, 0.4)
    path = dump(g, tmp_path)
    with pytest.raises(ValueError):
        optimize_file(path, "loglin", beta=[1.0, 2.0])
    with pytest.raises(RuntimeError):
        optimize_file(str(tmp_path / "missing.dag"), "v2")
