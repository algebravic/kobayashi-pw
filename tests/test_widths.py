import itertools
import random

from kobayashi_pw import from_edges, ordering_width, pathwidth
from kobayashi_pw.widths import (brute_cutwidth, brute_treewidth, cutwidth, cutwidth_of_order,
                                 treewidth, vertex_separation, width_of_elimination)


def graphs(seed, count, nmin, nmax):
    rng = random.Random(seed)
    for t in range(count):
        n = rng.randint(nmin, nmax)
        if t % 3 == 2:      # bipartite
            a = rng.randint(1, max(1, n // 2))
            E = [(i, j) for i in range(a) for j in range(a, n) if rng.random() < 0.5]
        else:
            p = rng.random()
            E = [(i, j) for i, j in itertools.combinations(range(n), 2) if rng.random() < p]
        yield from_edges(E, range(n))


def test_cutwidth_against_brute():
    for g in graphs(1, 150, 1, 10):
        cw = brute_cutwidth(g)
        for kw in ({"cover": None}, {"cover": "auto"}, {"greedy": False}):
            r = cutwidth(g, **kw)
            assert r.width == cw and cutwidth_of_order(g, r.order) == cw


def test_treewidth_against_brute():
    for g in graphs(2, 120, 1, 9):
        tw = brute_treewidth(g)
        for greedy in (True, False):
            r = treewidth(g, greedy=greedy)
            assert r.width == tw and width_of_elimination(g, r.order) == tw


def test_vertex_separation_same_engine():
    for g in graphs(3, 120, 1, 10):
        pw = pathwidth(g, want_order=False).width
        for greedy in (True, False):
            r = vertex_separation(g, greedy=greedy)
            assert r.width == pw and ordering_width(g, r.order) == pw


def test_greedy_rule_is_exactly_rule1_or_rule2():
    """For vs, 'adding v does not increase |N(S)|' equals Kobayashi's subsumption
    or the second rule of Coudert-Mazauric-Nisse."""
    rng = random.Random(4)
    for _ in range(40):
        n = rng.randint(2, 8)
        nin = [0] * n
        for i, j in itertools.permutations(range(n), 2):
            if rng.random() < 0.4:
                nin[j] |= 1 << i
        for S in range(1 << n):
            nb = 0
            for u in range(n):
                if S >> u & 1:
                    nb |= nin[u]
            NS = nb & ~S
            closed = S | NS
            for v in range(n):
                if S >> v & 1:
                    continue
                T = S | 1 << v
                fT = ((nb | nin[v]) & ~T).bit_count()
                r1 = nin[v] & ~closed == 0
                r2 = bool(NS >> v & 1) and (nin[v] & ~closed).bit_count() == 1
                assert (r1 or r2) == (fT <= NS.bit_count())
