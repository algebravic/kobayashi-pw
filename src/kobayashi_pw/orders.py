"""Many pathwidth-optimal orderings, and exact optimisation of a secondary cost.

Two directions are used below.

* sigma (kpw direction): prefixes S, width max |N(S_i)|, with N(S) the
  in-neighbours of S lying outside S.  The relevant-set DAG lives here: nodes are
  relevant sets S, and an arc S -> (S u {x})* carries the *block*
  [x, e_1, ..., e_m], meaning x followed by its expansion vertices in the order
  they were added.
* tau (frontier-DP direction): tau = reverse(sigma), a prefix T = V \\ S, and
  frontier F(T) = {u in T : u has a neighbour outside T} (Kinnersley's V_L).
  For an undirected graph, max_i |F(T_i)| over tau equals the sigma width of
  sigma, so tau is pw-optimal for a left-to-right frontier DP.  A sigma arc
  S -> T* becomes the tau block that takes the prefix from V \\ T* to V \\ S by
  adding e_m, ..., e_1, x.

``OrderDAG.build`` (or ``OrderDAG.load`` for a ``kpw -c -o`` dump) gives the DAG
in which every path from (empty)* to V is a pw-optimal ordering, possibly with
the second greedy rule (see ``core.expand``).  ``optimize`` minimises a
step-local cost exactly over all those orderings.

Step-local costs.  A *model* maps the features of one tau step (prefix T, then
vertex v) to a triple (a, e, k), applied as

    cost  += a + p * e
    p     <- max(p * e * k, 1)          (p starts at 1)

Additive costs use e = 0, so p stays 1.  The proxy costs of the hampath code
(V5-V7) use a = 0.001 * fw for the profile term, e = expand, and k = compress.
For a fixed prefix the cost-to-go is nondecreasing in p (induction on the
recursion J(T, p) = min_v [a + p e + J(T', max(p e k, 1))]).  So keeping, per
node, the labels (cost, p) that are not dominated in both coordinates is
exact.
"""

from __future__ import annotations

import math
import os
import random
import struct
from dataclasses import dataclass, field
from typing import Callable, Hashable, Iterable, Sequence

from .core import Graph, _bits, _union_nin, decide, expand, pathwidth
from .io import _INT

BELL = [1, 1, 2, 5, 15, 52, 203, 877, 4140, 21147, 115975, 678570, 4213597,
        27644437, 190899322, 1382958545, 10480142147, 82864869804,
        682076806159, 5832742205057, 51724158235372]


# ---------------------------------------------------------------------------
# The DAG
# ---------------------------------------------------------------------------

@dataclass
class OrderDAG:
    g: Graph
    pw: int
    greedy2: bool
    S0: int                                  # (empty)*
    a0: list[int]                            # expansion order of the empty set
    arcs: dict[int, list[tuple[int, tuple[int, ...]]]] = field(default_factory=dict)
    # arcs[S] = [(T, block), ...] with T = V (full mask) or a DAG node

    @property
    def full(self) -> int:
        return (1 << self.g.n) - 1

    def nodes_by_size_desc(self) -> list[int]:
        return sorted(self.arcs, key=lambda S: -S.bit_count())

    def __len__(self) -> int:
        return len(self.arcs) + 1             # + V

    # -- construction -------------------------------------------------------
    @classmethod
    def build(cls, g: Graph, greedy2: bool = False) -> "OrderDAG":
        """Compute pw, then all relevant sets of bottleneck <= pw (Kobayashi's
        Algorithm 1 at k = pw; equivalently, kpw with level pw completed), then
        keep only the sets from which V is reachable."""
        pw = pathwidth(g, want_order=False, greedy2=greedy2).width
        n, nin = g.n, g.nin
        full = (1 << n) - 1
        S0, nb0, a0 = expand(nin, full, 0, 0, greedy2)
        R: list[dict[int, int]] = [dict() for _ in range(n + 1)]
        R[S0.bit_count()][S0] = nb0
        succ: dict[int, list[tuple[int, tuple[int, ...]]]] = {}
        for i in range(n):
            for S, nb in R[i].items():
                out = []
                for x in _bits(full & ~S):
                    b = 1 << x
                    if ((nb | nin[x]) & ~(S | b)).bit_count() <= pw:
                        T, nbT, added = expand(nin, full, S | b, nb | nin[x], greedy2)
                        if T != full:
                            R[T.bit_count()].setdefault(T, nbT)
                        out.append((T, (x, *added)))
                succ[S] = out
        return cls._prune(g, pw, greedy2, S0, a0, succ)

    @classmethod
    def _prune(cls, g, pw, greedy2, S0, a0, succ) -> "OrderDAG":
        full = (1 << g.n) - 1
        good = {full}
        arcs: dict[int, list] = {}
        for S in sorted(succ, key=lambda S: -S.bit_count()):
            out = [(T, blk) for T, blk in succ[S] if T in good]
            if out:
                good.add(S)
                arcs[S] = out
        if S0 != full and S0 not in arcs:
            raise RuntimeError("V not reachable at level pw (internal error)")
        return cls(g, pw, greedy2, S0, list(a0), arcs)

    @classmethod
    def load(cls, path: str) -> "OrderDAG":
        """Load a DAG written by ``kpw -c -o FILE`` or ``kpw2 -c -o FILE``.

        Formats (doc/dag_format.md): KPWDAG3 (current; carries the vertex
        names, which become the labels, as ints if they are all integers) and
        the older KPWDAG1/KPWDAG2, whose labels are the bit indices."""
        with open(path, "rb") as f:
            magic = f.read(8)
            if magic == b"KPWDAG1\n":
                n, pw, greedy2, _ = struct.unpack("<4i", f.read(16))
                words = 1
            elif magic in (b"KPWDAG2\n", b"KPWDAG3\n"):
                n, pw, greedy2, words = struct.unpack("<4i", f.read(16))
            else:
                raise ValueError("not a kpw DAG file")

            def masks(count: int) -> list[int]:
                raw = struct.unpack(f"<{count * words}Q", f.read(8 * count * words))
                return [sum(raw[i * words + j] << (64 * j) for j in range(words))
                        for i in range(count)]

            nin = masks(n)
            (cnt,) = struct.unpack("<Q", f.read(8))
            sets = masks(cnt)
            labels: list[Hashable] = list(range(n))
            if magic == b"KPWDAG3\n":
                (nbytes,) = struct.unpack("<Q", f.read(8))
                names = f.read(nbytes).split(b"\0")[:n]
                labels = [t.decode("utf-8", "surrogateescape") for t in names]
                if labels and all(_INT.fullmatch(t) for t in labels) \
                        and len({int(t) for t in labels}) == len(labels):
                    labels = [int(t) for t in labels]
        g = Graph(n, nin, labels)
        full = (1 << n) - 1
        node = set(sets) | {full}
        S0, _, a0 = expand(nin, full, 0, 0, bool(greedy2))
        arcs = {}
        for S in sets:                        # arcs are recomputed, not stored
            nb = _union_nin(nin, S)
            out = []
            for x in _bits(full & ~S):
                b = 1 << x
                if ((nb | nin[x]) & ~(S | b)).bit_count() <= pw:
                    T, _, added = expand(nin, full, S | b, nb | nin[x], bool(greedy2))
                    if T in node:
                        out.append((T, (x, *added)))
            arcs[S] = out
        return cls(g, pw, bool(greedy2), S0, list(a0), arcs)

    # -- orderings ---------------------------------------------------------
    def path_counts(self) -> dict[int, int]:
        """Number of paths from each node to V (one ordering per arc sequence;
        the order inside a block is the canonical expansion order)."""
        cnt = {self.full: 1}
        for S in self.nodes_by_size_desc():
            cnt[S] = sum(cnt[T] for T, _ in self.arcs[S])
        return cnt

    def num_orderings(self) -> int:
        return 1 if self.S0 == self.full else self.path_counts()[self.S0]

    def _sigma_from_path(self, path: Iterable[tuple[int, ...]]) -> list[int]:
        sigma = list(self.a0)
        for blk in path:
            sigma.extend(blk)
        return sigma

    def sample(self, rng: random.Random | None = None, k: int = 1,
               tau: bool = True) -> list[list[Hashable]]:
        """k orderings drawn uniformly from the DAG's paths (labels).  ``tau``
        selects the frontier-DP direction (default) instead of kpw's."""
        rng = rng or random.Random()
        cnt = self.path_counts()
        out = []
        for _ in range(k):
            S, path = self.S0, []
            while S != self.full:
                arcs = self.arcs[S]
                r = rng.randrange(cnt[S])
                for T, blk in arcs:
                    r -= cnt[T]
                    if r < 0:
                        break
                path.append(blk)
                S = T
            sigma = self._sigma_from_path(path)
            seq = sigma[::-1] if tau else sigma
            out.append([self.g.labels[v] for v in seq])
        return out


# ---------------------------------------------------------------------------
# Step features in the frontier-DP (tau) direction
# ---------------------------------------------------------------------------

@dataclass
class StepFeatures:
    step: int            # 0-based position of v in tau
    v: int               # vertex index
    fw: int              # frontier size after introducing v and eliminating
    fw_before: int
    n_back: int          # neighbours of v placed earlier and still in the frontier
    n_elim: int          # as in hampath's _dp_cost: frontier vertices whose last neighbour
                         # is v, plus v itself only if v is isolated (a vertex whose
                         # neighbours all precede it enters and leaves at once, uncounted)
    e_bag: int           # edges inside the frontier
    comp_sizes: tuple[int, ...]   # component sizes of G[frontier]
    frontier: int        # mask


def _components(nin: Sequence[int], F: int) -> tuple[int, ...]:
    sizes = []
    rest = F
    while rest:
        seed = rest & -rest
        comp = seed
        frontier = seed
        while frontier:
            nxt = 0
            for u in _bits(frontier):
                nxt |= nin[u]
            nxt &= F & ~comp
            comp |= nxt
            frontier = nxt
        sizes.append(comp.bit_count())
        rest &= ~comp
    return tuple(sizes)


def tau_block_features(g: Graph, S_after: int, sigma_block: Sequence[int]) -> list[StepFeatures]:
    """Features of the tau steps that realise the sigma arc S -> S u block.

    In tau the prefix goes from V \\ (S u block) to V \\ S, adding the block in
    reverse.  ``S_after`` is S (the sigma set before the block)."""
    nin = g.nin
    full = (1 << g.n) - 1
    # sigma prefixes C_0 = S, C_j = S u {b_1..b_j}; their complements are the tau prefixes
    C = [S_after]
    for v in sigma_block:
        C.append(C[-1] | (1 << v))
    nbu = [_union_nin(nin, C[0])]
    for v in sigma_block:
        nbu.append(nbu[-1] | nin[v])
    feats = []
    m = len(sigma_block)
    T_before = full & ~C[m]
    F_before = T_before & nbu[m]
    for j in range(m, 0, -1):                 # tau adds b_j, ..., b_1
        v = sigma_block[j - 1]
        T_after = full & ~C[j - 1]
        F_after = T_after & nbu[j - 1]
        fw = F_after.bit_count()
        n_back = (nin[v] & T_before & F_after).bit_count()
        n_elim = (F_before & ~F_after).bit_count() + (1 if nin[v] == 0 else 0)
        e2 = 0
        for u in _bits(F_after):
            e2 += (nin[u] & F_after).bit_count()
        feats.append(StepFeatures(T_before.bit_count(), v, fw, F_before.bit_count(), n_back,
                                  n_elim, e2 // 2, _components(nin, F_after), F_after))
        T_before, F_before = T_after, F_after
    return feats


def tau_features(g: Graph, tau: Sequence[Hashable]) -> list[StepFeatures]:
    """Features of every step of a full ordering tau (labels)."""
    idx = {lab: i for i, lab in enumerate(g.labels)}
    sigma = [idx[l] for l in reversed(tau)]
    return tau_block_features(g, 0, sigma)


# ---------------------------------------------------------------------------
# Cost models
# ---------------------------------------------------------------------------

Model = Callable[[StepFeatures, int], tuple[float, float, float]]   # (feat, pw) -> (a, e, k)


def model_v2(f: StepFeatures, pw: int) -> tuple[float, float, float]:
    """hampath paper V2: sum_s 2^nb (fw/pw)^2 + 0.001 * profile (additive)."""
    return 2.0 ** f.n_back * (f.fw / max(pw, 1)) ** 2 + 0.001 * f.fw, 0.0, 0.0


def make_model_v7(expand_base: float = 1.55, density_alpha: float = 0.25) -> Model:
    """hampath ham_ordering._dp_cost (V7): proxy compounding with the
    connected-component Bell correction and density amplifier (no spike
    penalty, since every DAG ordering has fw <= pw)."""
    def model(f: StepFeatures, pw: int) -> tuple[float, float, float]:
        fw = f.fw
        bell_prod = math.prod(BELL[min(s, len(BELL) - 1)] for s in f.comp_sizes)
        bell_fw = BELL[min(fw, len(BELL) - 1)]
        corr = math.exp(0.5 * (math.log(max(bell_prod, 1)) - math.log(max(bell_fw, 1))))
        fw_weight = (fw / max(pw, 1)) ** 2 * corr
        dens = (1.0 + density_alpha * (f.e_bag / fw)) if fw > 0 else 1.0
        e = (expand_base ** f.n_back) * fw_weight * dens
        k = max(0.5 ** f.n_elim, 0.01)
        return 0.001 * fw, e, k
    return model


model_v7 = make_model_v7()


# The step features of the hampath work model (hamiltonian/claude/work_model.py):
# log(states_out / states_in) is predicted as beta . work_features(f, n).
WORK_FEATURES = ["const", "n_back", "n_elim", "fw", "fw_before", "e_bag",
                 "log_bell_components", "n_back*fw", "n_elim*fw_before",
                 "n_back^2", "step/(n-1)"]


def work_features(f: StepFeatures, n: int) -> list[float]:
    """Values of WORK_FEATURES for one tau step of an n-vertex graph."""
    log_bell = sum(math.log(BELL[min(s, len(BELL) - 1)]) for s in f.comp_sizes)
    return [1.0, f.n_back, f.n_elim, f.fw, f.fw_before, f.e_bag, log_bell,
            f.n_back * f.fw, f.n_elim * f.fw_before, f.n_back ** 2,
            f.step / max(n - 1, 1)]


def make_model_loglin(beta: Sequence[float], n: int) -> Model:
    """Predicted DP work sum_t s_t 2^nb_t with s_{t+1} = s_t exp(beta . x_t):
    a = 0, e = 2^nb, k = exp(beta . x) / 2^nb.  Exact over the DAG (e >= 0)."""
    beta = [float(b) for b in beta]
    if len(beta) != len(WORK_FEATURES):
        raise ValueError(f"need {len(WORK_FEATURES)} coefficients")

    def model(f: StepFeatures, pw: int) -> tuple[float, float, float]:
        g = sum(b * x for b, x in zip(beta, work_features(f, n)))
        e = 2.0 ** f.n_back
        return 0.0, e, math.exp(g) / e
    return model


def evaluate(g: Graph, tau: Sequence[Hashable], model: Model, pw: int) -> float:
    """Cost of a full ordering tau under ``model`` (same recursion as optimize)."""
    cost, p = 0.0, 1.0
    for f in tau_features(g, tau):
        a, e, k = model(f, pw)
        cost += a + p * e
        p = max(p * e * k, 1.0)
    return cost


# ---------------------------------------------------------------------------
# Exact optimisation over the DAG
# ---------------------------------------------------------------------------

@dataclass
class _Label:
    cost: float
    p: float
    prev: "_Label | None"
    block: tuple[int, ...]      # tau vertices appended by this label's last block


def _pareto(labels: list[_Label]) -> list[_Label]:
    labels.sort(key=lambda L: (L.cost, L.p))
    out, best_p = [], math.inf
    for L in labels:
        if L.p < best_p:
            out.append(L)
            best_p = L.p
    return out


def _apply(L: _Label, feats: list[StepFeatures], model: Model, pw: int) -> tuple[float, float]:
    cost, p = L.cost, L.p
    for f in feats:
        a, e, k = model(f, pw)
        cost += a + p * e
        p = max(p * e * k, 1.0)
    return cost, p


@dataclass
class OptResult:
    cost: float
    tau: list[Hashable]
    max_labels: int             # largest Pareto front at any node
    exact: bool


def optimize(dag: OrderDAG, model: Model, max_labels: int | None = None) -> OptResult:
    """Minimise the cost of the tau ordering over all paths of ``dag``.

    Exact unless ``max_labels`` truncates a Pareto front (it keeps the
    lowest-cost labels); ``OptResult.exact`` reports which happened."""
    g, pw, full = dag.g, dag.pw, dag.full
    labels: dict[int, list[_Label]] = {full: [_Label(0.0, 1.0, None, ())]}
    biggest, exact = 1, True
    for S in dag.nodes_by_size_desc():
        cand: list[_Label] = []
        for T, blk in dag.arcs[S]:
            feats = tau_block_features(g, S, blk)
            tau_blk = tuple(reversed(blk))
            for L in labels[T]:
                c, p = _apply(L, feats, model, pw)
                cand.append(_Label(c, p, L, tau_blk))
        front = _pareto(cand)
        if max_labels is not None and len(front) > max_labels:
            front, exact = front[:max_labels], False
        biggest = max(biggest, len(front))
        labels[S] = front
    # final block: the vertices of (empty)*, added last in tau
    feats0 = tau_block_features(g, 0, dag.a0) if dag.a0 else []
    tau0 = tuple(reversed(dag.a0))
    best, best_c = None, math.inf
    for L in labels[dag.S0]:
        c, _ = _apply(L, feats0, model, pw)
        if c < best_c:
            best, best_c = L, c
    # Blocks are collected from S0 back towards V; tau starts on V's side
    # (empty tau prefix) and ends with the vertices of (empty)*.
    blocks = [tau0]
    while best is not None and best.prev is not None:
        blocks.append(best.block)
        best = best.prev
    tau_idx = [v for blk in blocks[::-1] for v in blk]
    return OptResult(best_c, [g.labels[v] for v in tau_idx], biggest, exact)


# ---------------------------------------------------------------------------
# The same optimisation in C (src/C/kopt.c), on a DAG file
# ---------------------------------------------------------------------------

def find_kopt(explicit: str | None = None, n: int | None = None) -> str | None:
    """kopt for n vertices, compiled on first use (native.py); None if it cannot be built."""
    from .native import try_program
    return try_program("kopt", n, explicit=explicit)


def _dag_n(path: str) -> int:
    with open(path, "rb") as f:
        if f.read(6) != b"KPWDAG":
            raise RuntimeError(f"{path}: not a kpw DAG file")
        f.read(2)
        return struct.unpack("<i", f.read(4))[0]


def optimize_file(path: str, cost: str, *, beta: Sequence[float] | None = None,
                  expand_base: float = 1.55, density_alpha: float = 0.25,
                  max_labels: int | None = None, kopt: str | None = None) -> OptResult:
    """``optimize`` in C on a DAG file written by kpw/kpw2 -c -o.

    cost: "v2", "v7" (with expand_base, density_alpha) or "loglin" (with the
    11 coefficients ``beta`` of WORK_FEATURES).  Same recursion, arcs, blocks
    and tie-breaking as ``optimize``; the tau labels come from the file's
    vertex names (ints if they are all integers)."""
    import subprocess
    if not os.path.isfile(path):
        raise RuntimeError(f"kopt failed: no such DAG file {path}")
    exe = find_kopt(kopt, _dag_n(path))
    if exe is None:
        raise FileNotFoundError("kopt unavailable: no C compiler or sources (see native.py)")
    cmd = [exe, "-m", cost]
    if cost == "v7":
        cmd += ["-b", repr(float(expand_base)), "-a", repr(float(density_alpha))]
    elif cost == "loglin":
        if beta is None or len(beta) != len(WORK_FEATURES):
            raise ValueError(f"loglin needs {len(WORK_FEATURES)} coefficients")
        cmd += ["-B", ",".join(repr(float(b)) for b in beta)]
    elif cost != "v2":
        raise ValueError(f"unknown cost {cost!r}")
    if max_labels is not None:
        cmd += ["-L", str(int(max_labels))]
    r = subprocess.run(cmd + [path], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"kopt failed: {r.stderr.strip()}")
    return _parse_kopt(r.stdout)


def _parse_kopt(out: str) -> OptResult:
    head = order = None
    for line in out.splitlines():
        if line.startswith("kopt:"):
            head = dict(t.split("=", 1) for t in line.split()[1:])
        elif line.startswith("order:"):
            order = line.split()[1:]
    if head is None or order is None:
        raise RuntimeError(f"unexpected kopt output: {out[:200]!r}")
    if all(_INT.fullmatch(t) for t in order) and len({int(t) for t in order}) == len(order):
        order = [int(t) for t in order]
    return OptResult(float(head["cost"]), order, int(head["max_labels"]), head["exact"] == "1")


def k_best(dag: OrderDAG, model: Model, k: int) -> list[tuple[float, list[Hashable]]]:
    """The k cheapest tau orderings of the DAG for an *additive* model (e = 0
    at every step; checked).  Exact: keeps the k best partial costs per node."""
    g, pw, full = dag.g, dag.pw, dag.full
    labels: dict[int, list[_Label]] = {full: [_Label(0.0, 1.0, None, ())]}
    for S in dag.nodes_by_size_desc():
        cand = []
        for T, blk in dag.arcs[S]:
            feats = tau_block_features(g, S, blk)
            add = 0.0
            for f in feats:
                a, e, _ = model(f, pw)
                if e != 0.0:
                    raise ValueError("k_best needs an additive model (e == 0)")
                add += a
            tau_blk = tuple(reversed(blk))
            cand.extend(_Label(L.cost + add, 1.0, L, tau_blk) for L in labels[T])
        cand.sort(key=lambda L: L.cost)
        labels[S] = cand[:k]
    feats0 = tau_block_features(g, 0, dag.a0) if dag.a0 else []
    add0 = sum(model(f, pw)[0] for f in feats0)
    tau0 = tuple(reversed(dag.a0))
    out = []
    for L in labels[dag.S0]:
        blocks, M = [tau0], L
        while M.prev is not None:
            blocks.append(M.block)
            M = M.prev
        tau_idx = [v for blk in blocks[::-1] for v in blk]
        out.append((L.cost + add0, [g.labels[v] for v in tau_idx]))
    return out


# ---------------------------------------------------------------------------
# Reference: optimum over ALL pw-optimal orderings (no relevant-set restriction)
# ---------------------------------------------------------------------------

def optimize_all(g: Graph, model: Model, pw: int | None = None) -> OptResult:
    """Exact minimum over every ordering tau with max frontier <= pw, by a
    forward DP over all feasible prefixes with Pareto labels.  Exponential;
    for validation on small graphs."""
    if pw is None:
        pw = pathwidth(g, want_order=False).width
    n, nin = g.n, g.nin
    full = (1 << n) - 1
    layer: dict[int, list[_Label]] = {0: [_Label(0.0, 1.0, None, ())]}
    biggest = 1
    for _ in range(n):
        nxt: dict[int, list[_Label]] = {}
        for T, labs in layer.items():
            for v in _bits(full & ~T):
                feats = tau_block_features(g, full & ~(T | (1 << v)), [v])
                if feats[0].fw > pw:
                    continue
                T2 = T | (1 << v)
                for L in labs:
                    c, p = _apply(L, feats, model, pw)
                    nxt.setdefault(T2, []).append(_Label(c, p, L, (v,)))
        layer = {T: _pareto(L) for T, L in nxt.items()}
        biggest = max([biggest] + [len(L) for L in layer.values()])
    best = min(layer[full], key=lambda L: L.cost)
    seq, M = [], best
    while M.prev is not None:
        seq.append(M.block[0])
        M = M.prev
    return OptResult(best.cost, [g.labels[v] for v in reversed(seq)], biggest, True)
