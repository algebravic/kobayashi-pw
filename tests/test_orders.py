import itertools
import math
import os
import random
import subprocess

import pytest

from kobayashi_pw import from_edges, ordering_width, pathwidth
from kobayashi_pw.orders import (OrderDAG, evaluate, k_best, model_v2, model_v7,
                                 optimize, optimize_all, tau_features)

from .test_core import brute

KPW = os.path.join(os.path.dirname(__file__), "..", "src", "C", "kpw")


def frontier_widths(g, tau):
    """Reference frontier: placed vertices with an unplaced neighbour."""
    idx = {l: i for i, l in enumerate(g.labels)}
    placed, out = set(), []
    for lab in tau:
        placed.add(idx[lab])
        out.append(sum(1 for u in placed
                       if any(g.nin[u] >> w & 1 and w not in placed for w in range(g.n))))
    return out


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


def random_graph(rng, n, p):
    E = [(i, j) for i, j in itertools.combinations(range(n), 2) if rng.random() < p]
    return from_edges(E, range(n))


@pytest.mark.parametrize("directed", [False, True])
def test_greedy2_against_brute(directed):
    rng = random.Random(77 + directed)
    for _ in range(600):
        n = rng.randint(0, 10)
        E = [(i, j) for i, j in itertools.permutations(range(n), 2)
             if (directed or i < j) and rng.random() < rng.random()]
        g = from_edges(E, range(n), directed)
        r = pathwidth(g, greedy2=True)
        assert r.width == brute(g)
        assert ordering_width(g, r.order) == r.width


@pytest.mark.parametrize("greedy2", [False, True])
def test_dag_paths_are_optimal_and_optimizer_exact(greedy2):
    rng = random.Random(3 + greedy2)
    tested = 0
    while tested < 60:
        g = random_graph(rng, rng.randint(3, 10), rng.uniform(0.2, 0.6))
        dag = OrderDAG.build(g, greedy2=greedy2)
        if dag.num_orderings() > 2000:
            continue
        taus = list(all_paths(dag))
        assert len(taus) == dag.num_orderings()
        for tau in taus:
            assert max(frontier_widths(g, tau), default=0) == dag.pw
            assert [f.fw for f in tau_features(g, tau)] == frontier_widths(g, tau)
        for model in (model_v2, model_v7):
            best = min(evaluate(g, tau, model, max(dag.pw, 1)) for tau in taus)
            r = optimize(dag, model)
            assert r.exact and abs(r.cost - best) <= 1e-9 * max(1.0, best)
            assert abs(evaluate(g, r.tau, model, max(dag.pw, 1)) - r.cost) <= 1e-9 * max(1.0, best)
        kb = k_best(dag, model_v2, 4)
        costs = sorted(evaluate(g, tau, model_v2, max(dag.pw, 1)) for tau in taus)[:4]
        assert [round(c, 9) for c, _ in kb] == [round(c, 9) for c in costs]
        tested += 1


def test_relevant_dag_never_beats_all_orderings():
    rng = random.Random(11)
    for _ in range(40):
        g = random_graph(rng, rng.randint(3, 9), rng.uniform(0.2, 0.6))
        dag = OrderDAG.build(g)
        if dag.pw == 0:
            continue
        for model in (model_v2, model_v7):
            assert optimize_all(g, model, dag.pw).cost <= optimize(dag, model).cost + 1e-9


def test_sampling_is_optimal():
    E = [(i, j) for i in range(1, 36) for j in range(i + 1, 36) if math.isqrt(i + j) ** 2 == i + j]
    g = from_edges(E, range(1, 36))
    dag = OrderDAG.build(g)
    for tau in dag.sample(random.Random(0), k=100):
        assert sorted(tau) == list(range(1, 36))
        assert max(frontier_widths(g, tau)) == dag.pw == 5


@pytest.mark.skipif(not os.access(KPW, os.X_OK), reason="C binary not built (make)")
def test_c_dump_matches_python(tmp_path):
    rng = random.Random(5)
    for _ in range(25):
        n = rng.randint(4, 14)
        g = random_graph(rng, n, rng.uniform(0.15, 0.5))
        ef, df = tmp_path / "g.txt", tmp_path / "g.dag"
        lines = [str(v) for v in range(n)]
        lines += [f"{u} {v}" for v in range(n) for u in range(v) if g.nin[v] >> u & 1]
        ef.write_text("\n".join(lines) + "\n")
        for greedy2 in (False, True):
            subprocess.run([KPW, "-q", "-c", "-o", str(df)] + (["-g"] if greedy2 else []) + [str(ef)],
                           check=True, capture_output=True)
            a, b = OrderDAG.load(str(df)), OrderDAG.build(g, greedy2=greedy2)
            assert a.pw == b.pw and set(a.arcs) == set(b.arcs)
            assert a.num_orderings() == b.num_orderings()
