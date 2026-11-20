"""Prototype: the one-pass bottleneck search applied to other linear widths.

All three problems below are min-max problems over vertex orderings whose step
cost depends only on (the set S placed so far, the next vertex v):

    vertex separation  cost(S, v) = f(S + v),   f(S) = |N(S)|           (submodular)
    cutwidth           cost(S, v) = f(S + v),   f(S) = |E(S, V - S)|     (submodular)
    treewidth          cost(S, v) = |Q(S, v)|   (elimination orderings;
                       Q = vertices outside S + v reachable from v through S)

so the value is a minimum-bottleneck path in the DAG of prefix sets, found in
one pass by a Dijkstra-type search that only settles states of bottleneck
<= the optimum (no width parameter, no binary search).

Greedy closure (applied after every step, deterministic):
  * vs / cutwidth: add any vertex whose addition does not increase f
    ("rank <= 0").  For submodular f this is safe: moving such a vertex to the
    front of an optimal completion does not increase any prefix value.  For
    vs, this rule is exactly Kobayashi's subsumption plus Coudert-Mazauric-
    Nisse's second rule.
  * cutwidth, optionally (cover=...): only vertices of a vertex cover C are
    ever chosen; vertices outside C enter only through the closure.  Valid by
    Cygan et al. (Algorithmica 68, 2014, Lemmas 1-2); the states are then
    determined by S & C, so there are at most 2^|C| of them.
  * treewidth: eliminate simplicial vertices of the current elimination graph
    (safe: deg <= tw of the remaining elimination graph).

This is a prototype (Python, heap-based); the counts it reports are the
point, not its speed.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Callable, Hashable

from .core import Graph, _bits


@dataclass
class WidthResult:
    width: int
    order: list[Hashable]       # an optimal ordering (labels); for treewidth an elimination order
    settled: int                # states settled (popped with final value)
    generated: int              # distinct states ever generated


def _search(n: int, closure: Callable[[int], tuple[int, list[int], int]],
            arcs: Callable[[int], list]) -> tuple[int, list[int], int, int]:
    """Generic bottleneck Dijkstra over prefix sets.

    closure(T) -> (T', added vertices in order, max step cost of the added
    vertices, or 0); arcs(S) -> [(pre, x, w)]: place the vertices of the list
    ``pre`` and then x, at maximum step cost w.  The value of a state is the
    least possible maximum step cost of a path to it."""
    full = (1 << n) - 1
    S0, a0, c0 = closure(0)
    best = {S0: c0}
    parent: dict[int, tuple[int, int, list[int]] | None] = {S0: None}
    heap = [(c0, S0)]
    settled = set()
    while heap:
        d, S = heapq.heappop(heap)
        if S in settled or d > best[S]:
            continue
        settled.add(S)
        if S == full:
            seq, T = [], S
            while parent[T] is not None:
                P, x, pre, added = parent[T]
                seq[:0] = pre + [x] + added
                T = P
            return d, a0 + seq, len(settled), len(best)
        for pre, x, w in arcs(S):
            T0 = S | 1 << x
            for u in pre:
                T0 |= 1 << u
            T, added, cm = closure(T0)
            nd = max(d, w, cm)
            if nd < best.get(T, math.inf):
                best[T] = nd
                parent[T] = (S, x, list(pre), added)
                heapq.heappush(heap, (nd, T))
    raise RuntimeError("unreachable")


def _adj(g: Graph) -> list[int]:
    for v in range(g.n):
        for u in _bits(g.nin[v]):
            if not g.nin[u] >> v & 1:
                raise ValueError("cutwidth/treewidth prototypes need an undirected graph")
    return list(g.nin)


# ---------------------------------------------------------------------------
# vertex separation (for comparison with the same engine)
# ---------------------------------------------------------------------------

def vertex_separation(g: Graph, greedy: bool = True) -> WidthResult:
    n, nin = g.n, g.nin
    full = (1 << n) - 1

    def nb(S: int) -> int:
        m = 0
        for u in _bits(S):
            m |= nin[u]
        return m

    def f(S: int) -> int:
        return (nb(S) & ~S).bit_count()

    def closure(T: int):
        added = []
        if greedy:
            fT = f(T)
            changed = True
            while changed:
                changed = False
                for v in _bits(full & ~T):
                    fv = f(T | 1 << v)
                    if fv <= fT:
                        T |= 1 << v; fT = fv; added.append(v); changed = True
        return T, added, 0

    def arcs(S: int):
        return [((), x, f(S | 1 << x)) for x in _bits(full & ~S)]

    w, order, s, gen = _search(n, closure, arcs)
    return WidthResult(w, [g.labels[v] for v in order], s, gen)


# ---------------------------------------------------------------------------
# cutwidth
# ---------------------------------------------------------------------------

def min_vertex_cover(g: Graph) -> int:
    """Exact minimum vertex cover (simple branching on max degree); mask."""
    adj = _adj(g)
    best = [(1 << g.n) - 1]

    def rec(alive: int, cover: int) -> None:
        if cover.bit_count() >= best[0].bit_count():
            return
        v, dv = -1, 0
        for u in _bits(alive):
            d = (adj[u] & alive).bit_count()
            if d > dv:
                v, dv = u, d
        if dv == 0:
            best[0] = cover
            return
        rec(alive & ~(1 << v), cover | 1 << v)                       # v in cover
        nbr = adj[v] & alive
        rec(alive & ~nbr & ~(1 << v), cover | nbr)                    # N(v) in cover
    rec((1 << g.n) - 1, 0)
    return best[0]


def cutwidth(g: Graph, greedy: bool = True, cover: int | str | None = "auto") -> WidthResult:
    """Exact cutwidth.  ``cover``: None (all vertices may be chosen), a mask of
    a vertex cover, or "auto" (a minimum vertex cover); only used if greedy."""
    adj = _adj(g)
    n = g.n
    full = (1 << n) - 1
    deg = [m.bit_count() for m in adj]
    if cover == "auto":
        cover = min_vertex_cover(g)
    if not greedy:
        cover = None
    allowed = full if cover is None else cover

    def delta(S: int, v: int) -> int:             # rank: change of the cut when v joins S
        return deg[v] - 2 * (adj[v] & S).bit_count()

    def cut(S: int) -> int:
        return sum((adj[u] & ~S).bit_count() for u in _bits(S))

    def closure(T: int):
        added = []
        if greedy:
            changed = True
            while changed:
                changed = False
                for v in _bits(full & ~T):
                    if delta(T, v) <= 0:
                        T |= 1 << v; added.append(v); changed = True
        return T, added, 0

    odd = [d % 2 == 1 for d in deg]

    def arcs(S: int):
        c = cut(S)
        if cover is None:
            return [((), x, c + delta(S, x)) for x in _bits(full & ~S)]
        out = []
        for x in _bits(full & ~S & cover):
            # Cygan et al.: odd-degree non-cover neighbours of x that are balanced
            # (rank +1 now, -1 once x is placed) may go just before x; only
            # their number i matters: the two cuts are c + i and c + delta - i.
            Y = [u for u in _bits(adj[x] & ~S & ~cover) if odd[u] and delta(S, u) == 1]
            dx = delta(S, x)
            i = min(range(len(Y) + 1), key=lambda i: max(i, dx - i))
            out.append((Y[:i], x, c + max(i, dx - i)))
        return out

    w, order, s, gen = _search(n, closure, arcs)
    return WidthResult(w, [g.labels[v] for v in order], s, gen)


# ---------------------------------------------------------------------------
# treewidth (elimination orderings)
# ---------------------------------------------------------------------------

def treewidth(g: Graph, greedy: bool = True) -> WidthResult:
    adj = _adj(g)
    n = g.n
    full = (1 << n) - 1

    def Q(S: int, v: int) -> int:
        R = 1 << v
        while True:
            nb = 0
            for u in _bits(R):
                nb |= adj[u]
            grow = nb & S & ~R
            if not grow:
                return nb & ~S & ~(1 << v) & ~R
            R |= grow

    def closure(T: int):
        added, cm = [], 0
        if greedy:
            changed = True
            while changed:
                changed = False
                for v in _bits(full & ~T):
                    q = Q(T, v)
                    if all((Q(T, u) | 1 << u) & q == q for u in _bits(q)):   # simplicial in G_T
                        cm = max(cm, q.bit_count())
                        T |= 1 << v; added.append(v); changed = True
                        break
        return T, added, cm

    def arcs(S: int):
        return [((), x, Q(S, x).bit_count()) for x in _bits(full & ~S)]

    w, order, s, gen = _search(n, closure, arcs)
    return WidthResult(w, [g.labels[v] for v in order], s, gen)


# ---------------------------------------------------------------------------
# references
# ---------------------------------------------------------------------------

def brute_cutwidth(g: Graph) -> int:
    from functools import lru_cache
    adj, n = _adj(g), g.n
    full = (1 << n) - 1

    def cut(S: int) -> int:
        return sum((adj[u] & ~S).bit_count() for u in _bits(S))

    @lru_cache(None)
    def F(S: int) -> int:
        if S == full:
            return 0
        return min(max(cut(S | 1 << v), F(S | 1 << v)) for v in _bits(full & ~S))
    return F(0)


def brute_treewidth(g: Graph) -> int:
    from functools import lru_cache
    adj, n = _adj(g), g.n
    full = (1 << n) - 1

    def Q(S: int, v: int) -> int:
        R = 1 << v
        while True:
            nb = 0
            for u in _bits(R):
                nb |= adj[u]
            grow = nb & S & ~R
            if not grow:
                return nb & ~S & ~(1 << v) & ~R
            R |= grow

    @lru_cache(None)
    def F(S: int) -> int:
        if S == full:
            return 0
        return min(max(Q(S, v).bit_count(), F(S | 1 << v)) for v in _bits(full & ~S))
    return F(0) if n else 0


def cutwidth_of_order(g: Graph, order) -> int:
    idx = {l: i for i, l in enumerate(g.labels)}
    adj, S, w = _adj(g), 0, 0
    for l in order:
        S |= 1 << idx[l]
        w = max(w, sum((adj[u] & ~S).bit_count() for u in _bits(S)))
    return w


def width_of_elimination(g: Graph, order) -> int:
    """max over v of the degree of v when eliminated (fill-in graph)."""
    idx = {l: i for i, l in enumerate(g.labels)}
    adj = [set(_bits(m)) for m in _adj(g)]
    w = 0
    for l in order:
        v = idx[l]
        nb = adj[v]
        w = max(w, len(nb))
        for a in nb:
            adj[a] |= nb - {a}
            adj[a].discard(v)
        adj[v] = set()
    return w
