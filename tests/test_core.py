import itertools
import random
from functools import lru_cache

import pytest

from kobayashi_pw import Graph, decide, from_edges, ordering_width, pathwidth, read_graph6


def brute(g: Graph) -> int:
    """Exact vertex separation by DP over all 2^n subsets."""
    n, nin = g.n, g.nin

    @lru_cache(None)
    def f(m: int) -> int:
        if m == 0:
            return 0
        nb = 0
        for v in range(n):
            if m >> v & 1:
                nb |= nin[v]
        here = (nb & ~m).bit_count()
        return max(here, min(f(m & ~(1 << v)) for v in range(n) if m >> v & 1))

    return f((1 << n) - 1)


def random_graph(rng, n, p, directed):
    edges = [(i, j) for i, j in itertools.permutations(range(n), 2)
             if (directed or i < j) and rng.random() < p]
    return from_edges(edges, range(n), directed)


@pytest.mark.parametrize("directed", [False, True])
def test_random_against_brute(directed):
    rng = random.Random(12345 + directed)
    for _ in range(1500):
        n = rng.randint(0, 10)
        g = random_graph(rng, n, rng.random(), directed)
        pw = brute(g)
        r = pathwidth(g)
        assert r.width == pw
        assert ordering_width(g, r.order) == pw
        assert pathwidth(g, upper=pw - 1, want_order=False).width is None if pw > 0 else True
        assert decide(g, pw) and (pw == 0 or not decide(g, pw - 1))


def test_known_values():
    # paths: 1, cycles: 2, K_n: n-1, star: 1, 3x3 grid: 3
    P = from_edges([(i, i + 1) for i in range(9)])
    C = from_edges([(i, (i + 1) % 9) for i in range(9)])
    K = from_edges(itertools.combinations(range(7), 2))
    S = from_edges([(0, i) for i in range(1, 9)])
    G = from_edges([((i, j), (i + di, j + dj)) for i in range(3) for j in range(3)
                    for di, dj in ((0, 1), (1, 0)) if i + di < 3 and j + dj < 3])
    for g, pw in [(P, 1), (C, 2), (K, 6), (S, 1), (G, 3)]:
        assert pathwidth(g).width == pw


def test_directed_dag_is_zero():
    # Acyclic digraph: topological order has N^- empty at every prefix.
    g = from_edges([(i, j) for i, j in itertools.combinations(range(8), 2)], directed=True)
    assert pathwidth(g).width == 0


def test_graph6_petersen():
    g = read_graph6("IheA@GUAo")   # Petersen graph, pathwidth 5
    assert g.n == 10 and all(m.bit_count() == 3 for m in g.nin)
    assert pathwidth(g).width == brute(g) == 5
