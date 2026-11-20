"""Core algorithms.

Notation (Kobayashi, IPL 115 (2015) 310-312):

* ``N(U) = (union of nin[u] for u in U) minus U``  -- in-neighbours of U.
* x not in U is *subsumed* by U if ``nin[x] <= U | N(U)``.
* ``U*`` (expansion): repeatedly add subsumed vertices.  U is *relevant*
  if ``U* == U``.
* Step cost ``w(U, x) = |N(U | {x})|``.

Key fact: if x is subsumed by U then ``N(U | {x}) <= N(U)``.  Hence the
expansion vertices never increase the boundary, and every edge
``U -> (U | {x})*`` of the relevant-set DAG has the single, k-independent
cost w(U, x).  The vertex separation number is the min over paths from
``(empty)*`` to V of the max edge cost (bottleneck path), and Lemma 2 of the
paper (applied at k = pw) shows the optimum is attained inside the
relevant-set DAG.

``pathwidth`` finds that bottleneck path with a bucketed Dijkstra (levels
c = 0, 1, 2, ...).  A set first reached at level c has optimal bottleneck
exactly c, because all lower levels were exhausted first.  So the first
time V is reached, c = pw, and the parent pointers give an optimal
ordering.  Every set it expands has bottleneck <= pw, so it does no more
expansion work than one run of Algorithm 1 at k = pw.

Memory refinement: rather than storing every rejected pair (S, x) in the
bucket of its width, each discovered set S is stored once, in the bucket of
min{w(S, x) : w(S, x) > current level}.  When that level is reached, S is
rescanned and the pairs of exactly that width are released; S is then
rescheduled at its next larger width.  This trades O(n) recomputation per
rescan for one bucket entry per set instead of up to n.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable, Sequence


@dataclass
class Graph:
    """Digraph via in-neighbour masks.  Undirected graphs: symmetric masks."""

    n: int
    nin: list[int]
    labels: list[Hashable] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.labels:
            self.labels = list(range(self.n))
        if len(self.nin) != self.n or len(self.labels) != self.n:
            raise ValueError("nin/labels length must equal n")
        for v, m in enumerate(self.nin):
            if m >> v & 1:
                raise ValueError(f"self-loop at vertex {self.labels[v]!r}")
            if m >> self.n:
                raise ValueError("neighbour mask out of range")


@dataclass
class Result:
    width: int | None              # None: pw > upper (decision mode)
    order: list[Hashable] | None   # optimal ordering (labels) if requested
    sets_expanded: int = 0         # relevant sets discovered
    pairs_popped: int = 0          # (S, x) steps taken from the work stack
    rescans: int = 0
    per_level: dict[int, int] = field(default_factory=dict)  # level -> sets discovered


def _bits(m: int):
    while m:
        b = m & -m
        yield b.bit_length() - 1
        m ^= b


def _union_nin(nin: Sequence[int], U: int) -> int:
    nb = 0
    for u in _bits(U):
        nb |= nin[u]
    return nb


def boundary(g: Graph, U: int) -> int:
    """Mask of N^-(U)."""
    return _union_nin(g.nin, U) & ~U


def expand(nin: Sequence[int], full: int, U: int, nb: int,
           greedy2: bool = False) -> tuple[int, int, list[int]]:
    """Compute the expansion of U one vertex at a time.

    ``nb`` must equal the union of nin[u] over u in U.  Returns
    (U', union of nin over U', vertices in the order added).

    Rule 1 (Kobayashi subsumption): add x with nin[x] <= U | N(U).  The
    result of applying rule 1 to a fixpoint is U*.

    Rule 2 (only if ``greedy2``; Coudert, Mazauric and Nisse 2014, Lemma 6,
    stated there for out-neighbours and mirrored here): add x in N(U) with
    exactly one in-neighbour outside U | N(U).  The boundary keeps its size.

    Each added vertex satisfies a rule with respect to the set at the moment it
    is added, so every prefix of the returned order has boundary size at most
    |N(U)|.  (The order matters: a vertex may qualify only after other
    vertices have been added.)
    """
    added: list[int] = []
    while True:
        closed = U | nb
        changed = True
        while changed:
            changed = False
            for x in _bits(full & ~U):
                if nin[x] & ~closed == 0:
                    U |= 1 << x
                    nb |= nin[x]
                    closed = U | nb
                    added.append(x)
                    changed = True
        if not greedy2:
            return U, nb, added
        hit = -1
        for x in _bits(nb & ~U):
            if (nin[x] & ~closed).bit_count() == 1:
                hit = x
                break
        if hit < 0:
            return U, nb, added
        U |= 1 << hit
        nb |= nin[hit]
        added.append(hit)


def pathwidth(g: Graph, upper: int | None = None, want_order: bool = True,
              greedy2: bool = False) -> Result:
    """Vertex separation number (= pathwidth) of g, with an optimal ordering.

    If ``upper`` is given and pw > upper, returns Result(width=None, ...)
    without exploring any level above ``upper`` (decision version).
    ``greedy2`` enables the second expansion rule (see ``expand``); the result
    is the same, usually with fewer sets visited.
    """
    n, nin = g.n, g.nin
    full = (1 << n) - 1
    res = Result(width=None, order=None)
    if n == 0:
        res.width, res.order = 0, []
        return res

    parent: dict[int, tuple[int, int] | None] = {}
    buckets: list[list[tuple[int, int]]] = [[] for _ in range(n + 1)]
    stack: list[tuple[int, int, int]] = []

    def scan(S: int, nb: int, lo: int, c: int) -> None:
        """Push pairs with lo < w <= c; reschedule S at its next width > c."""
        nxt = n + 1
        for x in _bits(full & ~S):
            b = 1 << x
            w = ((nb | nin[x]) & ~(S | b)).bit_count()
            if w <= c:
                if w > lo:
                    stack.append((S, nb, x))
            elif w < nxt:
                nxt = w
        if nxt <= n:
            buckets[nxt].append((S, nb))

    S0, nb0, _ = expand(nin, full, 0, 0, greedy2)
    parent[S0] = None
    res.sets_expanded = 1
    res.per_level[0] = 1
    found = S0 == full
    c = 0
    if not found:
        scan(S0, nb0, -1, 0)

    while not found:
        while stack:
            P, nbP, x = stack.pop()
            res.pairs_popped += 1
            T = P | (1 << x)
            if T in parent:           # T relevant and already seen => T* = T seen
                continue
            T, nbT, _ = expand(nin, full, T, nbP | nin[x], greedy2)
            if T in parent:
                continue
            parent[T] = (P, x)
            res.sets_expanded += 1
            res.per_level[c] = res.per_level.get(c, 0) + 1
            if T == full:
                found = True
                break
            scan(T, nbT, -1, c)
        if found:
            break
        c += 1
        if c > n or (upper is not None and c > upper):
            return res                # pw > upper
        for S, nb in buckets[c]:
            res.rescans += 1
            scan(S, nb, c - 1, c)
        buckets[c] = []

    res.width = c
    if want_order:
        res.order = [g.labels[v] for v in _extract(nin, full, parent, greedy2)]
    return res


def _extract(nin: Sequence[int], full: int, parent: dict, greedy2: bool = False) -> list[int]:
    """Chase parent pointers from V back to (empty)*; recompute expansions."""
    segments: list[list[int]] = []
    S = full
    while True:
        link = parent[S]
        if link is None:
            segments.append(expand(nin, full, 0, 0, greedy2)[2])
            break
        P, x = link
        _, _, added = expand(nin, full, P | (1 << x), _union_nin(nin, P) | nin[x], greedy2)
        segments.append([x] + added)
        S = P
    order: list[int] = []
    for seg in reversed(segments):
        order.extend(seg)
    return order


def decide(g: Graph, k: int) -> bool:
    """Algorithm 1 of the paper, literally (size-ordered DP).  For cross-checks."""
    n, nin = g.n, g.nin
    full = (1 << n) - 1
    R: list[set[int]] = [set() for _ in range(n + 1)]
    S0, _, _ = expand(nin, full, 0, 0)
    R[S0.bit_count()].add(S0)
    for i in range(n):
        for U in R[i]:
            nbU = _union_nin(nin, U)
            for v in _bits(full & ~U):
                b = 1 << v
                if ((nbU | nin[v]) & ~(U | b)).bit_count() <= k:
                    T, _, _ = expand(nin, full, U | b, nbU | nin[v])
                    R[T.bit_count()].add(T)
    return bool(R[n])


def ordering_width(g: Graph, order: Sequence[Hashable]) -> int:
    """max_i |N^-(first i vertices)| for an ordering given by labels."""
    idx = {lab: i for i, lab in enumerate(g.labels)}
    if sorted(idx[l] for l in order) != list(range(g.n)):
        raise ValueError("order is not a permutation of the vertices")
    U = nb = 0
    best = 0
    for lab in order:
        v = idx[lab]
        U |= 1 << v
        nb |= g.nin[v]
        best = max(best, (nb & ~U).bit_count())
    return best
