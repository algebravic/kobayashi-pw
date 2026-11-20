"""The specifications of doc/dsl_design.md §4–§6, written in the embedded DSL."""
from __future__ import annotations

from . import lemma
from .eager import GData, bits
from .ir import N, Nin, bigunion, card, cut, deg, forall, imax, imin, member, odd, qset, seq, single, subset
from .problem import Problem


def vertex_separation(greedy2: bool = False) -> Problem:
    """kpw: Kobayashi's relevant-set search (rule 1; rule 2 with greedy2)."""
    P = Problem("vertex_separation", directed=True)
    nb = lambda S: bigunion(S, Nin)                              # N⁻(S) ∪ (part of S)
    P.cost_f(lambda S: card(nb(S) - S), by=lemma.submod_coverage)
    P.closure(lambda S, v: subset(Nin(v), S | nb(S)), by=lemma.greedy)
    if greedy2:
        P.closure(lambda S, v: member(v, nb(S)) & (card(Nin(v) - (S | nb(S))) == 1), by=lemma.greedy)
    P.choose(by=lemma.trivial)                                   # x ∈ V ∖ S
    P.key(lambda S: S, by=lemma.trivial)
    P.components()
    P.impl(maintain=[nb], probe=True)
    return P


def vertex_cover_twin_closed(g: GData) -> int:
    """A vertex cover: exact (König) on bipartite graphs, greedy otherwise; then
    closed under twins (required by lemma.twins)."""
    n, nb = g.n, g.nb
    col, bip = [-1] * n, True
    for s in range(n):
        if col[s] >= 0:
            continue
        col[s], st = 0, [s]
        while st:
            v = st.pop()
            for u in bits(nb[v]):
                if col[u] < 0:
                    col[u] = 1 - col[v]; st.append(u)
                elif col[u] == col[v]:
                    bip = False
    C = 0
    if bip:
        mate = [-1] * n
        def aug(v, seen):
            for u in bits(nb[v]):
                if not seen >> u & 1:
                    seen |= 1 << u
                    if mate[u] < 0:
                        mate[u], mate[v] = v, u
                        return True, seen
                    ok, seen = aug(mate[u], seen)
                    if ok:
                        mate[u], mate[v] = v, u
                        return True, seen
            return False, seen
        for v in range(n):
            if col[v] == 0 and mate[v] < 0:
                aug(v, 0)
        Z, st = 0, [v for v in range(n) if col[v] == 0 and mate[v] < 0]
        for v in st:
            Z |= 1 << v
        while st:
            v = st.pop()
            for u in bits(nb[v]):
                if mate[v] != u and not Z >> u & 1:
                    Z |= 1 << u
                    w = mate[u]
                    if w >= 0 and not Z >> w & 1:
                        Z |= 1 << w; st.append(w)
        for v in range(n):
            if (col[v] == 0) != bool(Z >> v & 1):
                C |= 1 << v
    else:
        d = [m.bit_count() for m in nb]
        while True:
            best = max((v for v in range(n) if not C >> v & 1 and d[v] > 0), key=lambda v: d[v], default=-1)
            if best < 0:
                break
            C |= 1 << best
            for u in bits(nb[best]):
                d[u] -= 1
            d[best] = 0
        for v in range(n):
            if C >> v & 1 and not nb[v] & ~C:
                C &= ~(1 << v)
    cls = g.vfuns["_twclass"]
    for v in range(n):
        if C >> v & 1:
            C |= cls[v]
    return C


def cutwidth(cover: bool = True, twins: bool = True, counters: bool = True) -> Problem:
    """kcw: rank closure, vertex-cover normal form, twin symmetry."""
    P = Problem("cutwidth")
    f = P.cost_f(lambda S: cut(S), by=lemma.submod_cut)
    D = lambda S, v: deg(v) - 2 * card(N(v) & S)                 # Δ(S, v) = f(S+v) − f(S)
    P.closure(lambda S, v: D(S, v) <= 0, by=lemma.greedy)
    if cover:
        C = P.const_set("C", vertex_cover_twin_closed)
        Y = lambda S, x: seq(N(x) - C - S, lambda u: odd(deg(u)) & (D(S, u) == 1))
        i = lambda S, x: imin(card(Y(S, x)), imax(0, D(S, x) // 2))
        P.choose(over=lambda S: C - S,
                 prefix=lambda S, x: Y(S, x)[: i(S, x)],
                 cost=lambda S, x: f(S) + imax(i(S, x), D(S, x) - i(S, x)),
                 by=lemma.cover_normal_form)
        P.key(lambda S: S & C, by=lemma.normal_key)
        if twins:
            P.symmetry(lemma.twins, preserves=[P.consts["C"]])
    else:
        P.choose(by=lemma.trivial)
        if twins:
            P.symmetry(lemma.twins)
    P.components()
    if counters:                                                 # Layer D: a[v] = |N(v) ∩ S|, in place + undo
        P.impl(maintain=[lambda S, v: card(N(v) & S)])
    return P


def treewidth() -> Problem:
    """Elimination orderings; simplicial closure (eager mode only)."""
    P = Problem("treewidth")
    Q = qset                                                     # Q(S, v): neighbours of v in G_S
    P.cost_w(lambda S, v: card(Q(S, v)))
    P.closure(lambda S, v: forall(Q(S, v), lambda u: subset(Q(S, v) - single(u), Q(S, u))),
              by=lemma.simplicial)                               # v simplicial in G_S
    P.choose(by=lemma.trivial)
    P.key(lambda S: S, by=lemma.trivial)
    P.components()
    return P
