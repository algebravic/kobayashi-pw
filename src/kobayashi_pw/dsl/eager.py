"""Reference semantics: an evaluator for the IR on Python ints, the engine E,
a 2^n brute force, and the obligation checker used by Problem.check()."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .ir import BINDERS, Node


def bits(m: int):
    while m:
        b = m & -m
        yield b.bit_length() - 1
        m ^= b


@dataclass
class GData:
    """Graph data seen by a specification: masks over [0, n)."""
    n: int
    nin: list[int]
    nout: list[int]
    labels: list
    csets: dict = field(default_factory=dict)     # name -> mask
    vfuns: dict = field(default_factory=dict)     # name -> list[mask]
    tables: dict = field(default_factory=dict)    # name -> list[float]  (secondary costs)
    params: dict = field(default_factory=dict)    # name -> list[float]  (runtime parameters)
    width: int | None = None                      # B*, once known

    @property
    def full(self) -> int:
        return (1 << self.n) - 1

    @property
    def nb(self) -> list[int]:
        return [self.nin[v] | self.nout[v] for v in range(self.n)]

    @classmethod
    def from_graph(cls, g) -> "GData":
        n = g.n
        nout = [0] * n
        for v in range(n):
            for u in bits(g.nin[v]):
                nout[u] |= 1 << v
        return cls(n, list(g.nin), nout, list(g.labels))

    def sub(self, verts: list[int]) -> "GData":
        """Induced subgraph on verts (in this order)."""
        idx = {v: i for i, v in enumerate(verts)}
        def m(mask):
            r = 0
            for u in bits(mask):
                if u in idx:
                    r |= 1 << idx[u]
            return r
        return GData(len(verts), [m(self.nin[v]) for v in verts], [m(self.nout[v]) for v in verts],
                     [self.labels[v] for v in verts])


def evaluate(node: Node, env: dict, g: GData):
    """Value of an IR node: sets are int masks, vertices ints, seqs lists."""
    op, a = node.op, node.args
    ev = lambda x: evaluate(x, env, g)
    if op == "var":
        return env[a[0]]
    if op in ("int", "bool", "real"):
        return a[0]
    if op == "toreal":
        return float(ev(a[0]))
    if op in ("radd", "rsub", "rmul", "rdiv", "rlt", "rle"):
        x, y = ev(a[0]), ev(a[1])
        if op == "radd": return x + y
        if op == "rsub": return x - y
        if op == "rmul": return x * y
        if op == "rdiv": return x / y if y != 0 else (math.copysign(math.inf, x) if x != 0 else math.nan)
        if op == "rlt": return x < y
        return x <= y
    if op == "rexp":
        x = ev(a[0]); return math.exp(x) if x < 709.0 else math.inf
    if op == "rlog":
        x = ev(a[0]); return math.log(x) if x > 0 else (-math.inf if x == 0 else math.nan)
    if op == "rpow":
        x, y = ev(a[0]), ev(a[1])
        try:
            return math.pow(x, y)
        except (OverflowError, ValueError):
            return math.inf if x > 0 else math.nan
    if op == "rmin":
        return min(ev(a[0]), ev(a[1]))
    if op == "rmax":
        return max(ev(a[0]), ev(a[1]))
    if op == "table":
        t = g.tables[a[0]]; i = ev(a[1]); return t[min(max(i, 0), len(t) - 1)]
    if op == "param":
        return g.params[a[0]][a[1]]
    if op == "bwidth":
        if g.width is None:
            raise ValueError("width() is only defined once the width is known (secondary costs)")
        return g.width
    if op == "nverts":
        return g.n
    if op == "comp_sum":
        A, k, body = ev(a[0]), a[1].args[0], a[2]
        tbl, total, rest = g.nb, 0.0, A
        while rest:
            comp = rest & -rest
            front = comp
            while front:
                nxt = 0
                for u in bits(front):
                    nxt |= tbl[u]
                nxt &= A & ~comp
                comp |= nxt
                front = nxt
            env2 = dict(env); env2[k] = comp.bit_count()
            total += evaluate(body, env2, g)
            rest &= ~comp
        return total
    if op == "full":
        return g.full
    if op == "empty":
        return 0
    if op == "or":
        return ev(a[0]) | ev(a[1])
    if op == "and":
        return ev(a[0]) & ev(a[1])
    if op == "sub":
        return ev(a[0]) & ~ev(a[1])
    if op == "single":
        return 1 << ev(a[0])
    if op == "N":
        v = ev(a[0]); return g.nin[v] | g.nout[v]
    if op == "Nin":
        return g.nin[ev(a[0])]
    if op == "Nout":
        return g.nout[ev(a[0])]
    if op == "deg":
        v = ev(a[0]); return (g.nin[v] | g.nout[v]).bit_count()
    if op == "cset":
        return g.csets[a[0]]
    if op == "vfun":
        return g.vfuns[a[0]][ev(a[1])]
    if op == "card":
        x = ev(a[0]); return len(x) if isinstance(x, list) else x.bit_count()
    if op == "member":
        return bool(ev(a[1]) >> ev(a[0]) & 1)
    if op == "subset":
        return ev(a[0]) & ~ev(a[1]) == 0
    if op == "cut":
        A = ev(a[0])
        tbl = g.nb
        return sum((tbl[u] & ~A).bit_count() for u in bits(A))
    if op == "bigunion":
        A, name = ev(a[0]), a[1]
        tbl = {"N": g.nb, "Nin": g.nin, "Nout": g.nout}.get(name) or g.vfuns[name]
        r = 0
        for u in bits(A):
            r |= tbl[u]
        return r
    if op in BINDERS:
        A, u, body = ev(a[0]), a[1].args[0], a[2]
        vals = []
        for x in bits(A):
            env2 = dict(env); env2[u] = x
            vals.append((x, evaluate(body, env2, g)))
        if op == "filter":
            r = 0
            for x, b in vals:
                if b:
                    r |= 1 << x
            return r
        if op == "seq":
            return [x for x, b in vals if b]
        if op == "sum":
            return sum(b for _, b in vals)
        if op == "forall":
            return all(b for _, b in vals)
        return any(b for _, b in vals)
    if op == "take":
        return ev(a[0])[: max(0, ev(a[1]))]
    if op == "add":
        return ev(a[0]) + ev(a[1])
    if op == "isub":
        return ev(a[0]) - ev(a[1])
    if op == "mul":
        return ev(a[0]) * ev(a[1])
    if op == "fdiv":
        return ev(a[0]) // ev(a[1])
    if op == "min":
        return min(ev(a[0]), ev(a[1]))
    if op == "max":
        return max(ev(a[0]), ev(a[1]))
    if op == "where":
        return ev(a[1]) if ev(a[0]) else ev(a[2])
    if op == "lt":
        return ev(a[0]) < ev(a[1])
    if op == "le":
        return ev(a[0]) <= ev(a[1])
    if op == "eq":
        return ev(a[0]) == ev(a[1])
    if op == "not":
        return not ev(a[0])
    if op == "land":
        return bool(ev(a[0])) and bool(ev(a[1]))
    if op == "lor":
        return bool(ev(a[0])) or bool(ev(a[1]))
    if op == "odd":
        return ev(a[0]) % 2 == 1
    if op == "qset":
        S, v = ev(a[0]), ev(a[1])
        tbl = g.nb
        seen, st, out = 1 << v, [v], 0
        while st:
            x = st.pop()
            for y in bits(tbl[x] & ~seen):
                seen |= 1 << y
                if S >> y & 1:
                    st.append(y)
                else:
                    out |= 1 << y
        return out
    raise NotImplementedError(f"eager evaluation of {op}")


class Eager:
    """A Problem bound to graph data, evaluated by the IR interpreter."""

    def __init__(self, prob, g: GData):
        self.p, self.g = prob, g
        S, v, x = prob.S_name, prob.v_name, prob.x_name
        self.Sn, self.vn, self.xn = S, v, x

    # -- primitive pieces -------------------------------------------------
    def w(self, S: int, v: int) -> int:
        return evaluate(self.p.w_node, {self.Sn: S, self.vn: v}, self.g)

    def f(self, S: int) -> int:
        return evaluate(self.p.f_node, {self.Sn: S}, self.g)

    def closure_rule(self, S: int, v: int):
        """Index of the first closure rule that adds v at S, or None."""
        for k, c in enumerate(self.p.closures):
            if evaluate(c.pred, {self.Sn: S, self.vn: v}, self.g):
                return k
        return None

    def close(self, S: int, seqout: list | None = None) -> int:
        """Closure fixpoint by repeated sweeps in increasing vertex order."""
        changed = True
        while changed:
            changed = False
            for v in bits(self.g.full & ~S):
                if self.closure_rule(S, v) is not None:
                    S |= 1 << v
                    if seqout is not None:
                        seqout.append(v)
                    changed = True
        return S

    def choices(self, S: int) -> list[int]:
        over = evaluate(self.p.move.over, {self.Sn: S}, self.g) & ~S
        out = []
        for x in bits(over):
            ok = all(evaluate(f, {self.Sn: S, self.xn: x}, self.g) for f in self.p.choice_filters)
            if ok:
                out.append(x)
        return out

    def prefix(self, S: int, x: int) -> list[int]:
        if self.p.move.prefix is None:
            return []
        return evaluate(self.p.move.prefix, {self.Sn: S, self.xn: x}, self.g)

    def apply(self, S: int, x: int) -> tuple[int, list[int]]:
        seq = list(self.prefix(S, x)) + [x]
        T = S
        for u in seq:
            T |= 1 << u
        T = self.close(T, seq)
        return T, seq

    def derived_cost(self, S: int, seq: list[int]) -> int:
        """O1: max over the block of w(prefix set, vertex)."""
        c, T = 0, S
        for u in seq:
            c = max(c, self.w(T, u))
            T |= 1 << u
        return c

    def cost(self, S: int, x: int) -> tuple[int, int, list[int]]:
        T, seq = self.apply(S, x)
        if self.p.move.cost is not None:
            c = evaluate(self.p.move.cost, {self.Sn: S, self.xn: x}, self.g)
        else:
            c = self.derived_cost(S, seq)
        return c, T, seq

    def key(self, S: int) -> int:
        return evaluate(self.p.key_node, {self.Sn: S}, self.g)

    def decode(self, k: int) -> int:
        return self.close(k)

    # -- engine E ---------------------------------------------------------
    def solve(self, max_states: int | None = None, check: bool = False, complete: bool = False):
        """Engine E.  With complete=True, level B* is finished instead of stopping at V, and
        (B*, table, root_seq) is returned: the table then holds every state of bottleneck <= B*."""
        g = self.g
        root_seq: list[int] = []
        s0 = self.close(0, root_seq)
        T = {self.key(s0): None}
        B0 = self.derived_cost(0, root_seq)          # the root block's own cost (0 for greedy closures)
        if s0 == g.full:
            if complete:
                return B0, T, root_seq
            return B0, self._order(T, s0, root_seq), dict(states=1)
        B, stack, buckets = B0, [s0], {}
        stats = dict(states=1, expansions=0)
        found = False
        while True:
            while stack:
                s = stack.pop()
                stats["expansions"] += 1
                nxt = None
                for x in self.choices(s):
                    c, t, seq = self.cost(s, x)
                    if check:
                        self._check_arc(s, x, c, t, seq)
                    if c > B:
                        nxt = c if nxt is None else min(nxt, c)
                        continue
                    k = self.key(t)
                    if k not in T:
                        T[k] = (self.key(s), x)
                        stats["states"] += 1
                        if t == g.full:
                            if not complete:
                                return B, self._order(T, t, root_seq), stats
                            found = True
                            continue
                        stack.append(t)
                        if max_states and stats["states"] > max_states:
                            return None, B, stats
                if nxt is not None:
                    buckets.setdefault(nxt, []).append(s)
            if found:
                return B, T, root_seq
            if not buckets:
                raise RuntimeError("engine: V unreachable (a choose clause is too restrictive)")
            B = min(buckets)
            stack = buckets.pop(B)

    # -- engine E2: secondary costs over the optimal move graph ----------
    def sec_step(self, sec, T: int, v: int) -> tuple[float, float, float]:
        env = {"T": T, self.vn: v}
        return (evaluate(sec.a, env, self.g), evaluate(sec.e, env, self.g), evaluate(sec.k, env, self.g))

    def sec_block(self, sec, S: int, seq: list[int]) -> list[tuple[float, float, float]]:
        """(a, e, k) of the τ-steps realising the σ-arc S -> S ∪ seq: τ adds seq reversed,
        the placed prefix before adding seq[j-1] being V ∖ (S ∪ seq[:j])."""
        full = self.g.full
        C = [S]
        for u in seq:
            C.append(C[-1] | 1 << u)
        return [self.sec_step(sec, full & ~C[j], seq[j - 1]) for j in range(len(seq), 0, -1)]

    @staticmethod
    def fold(cost: float, p: float, steps) -> tuple[float, float]:
        for a, e, k in steps:
            cost += a + p * e
            p = max(p * e * k, 1.0)
        return cost, p

    def sec_cost_of_order(self, sec, tau: list[int]) -> float:
        """Obligation S2's reference: the cost of a full τ ordering, step by step."""
        cost, p, T = 0.0, 1.0, 0
        for v in tau:
            a, e, k = self.sec_step(sec, T, v)
            if self.p.secondaries[sec.name].by.name == "pareto_monotone" and (e < 0 or e * k < 0):
                raise AssertionError(f"pareto_monotone hypothesis fails: e={e}, k={k} at T={T:#x}, v={v}")
            cost += a + p * e
            p = max(p * e * k, 1.0)
            T |= 1 << v
        return cost

    def graph_of_optima(self):
        """(B*, nodes in decreasing size, arcs) of the optimal move graph Γ, and the root block.
        nodes: list of states; arcs[s] = [(x, t, seq)] with cost <= B* and t co-reachable."""
        B, T, root_seq = self.solve(complete=True)
        full = self.g.full
        states = sorted((self.decode(k) for k in T), key=lambda s: -s.bit_count())
        good, arcs = {full}, {}
        for s in states:
            if s == full:
                continue
            out = []
            for x in self.choices(s):
                c, t, seq = self.cost(s, x)
                if c <= B and t in good:
                    out.append((x, t, seq))
            if out:
                good.add(s)
                arcs[s] = out
        return B, [s for s in states if s in arcs], arcs, root_seq

    def dagopt(self, sec, max_labels: int | None = None):
        """Engine E2 (Pareto labels).  Returns (B*, τ, cost, exact, stats)."""
        g = self.g
        B, nodes, arcs, root_seq = self.graph_of_optima()
        g.width = B
        full = g.full
        # label: (cost, p, prev label, x, seq)
        labels = {full: [(0.0, 1.0, None, None, None)]}
        biggest, exact, total = 1, True, 1
        for s in nodes:
            cand = []
            for x, t, seq in arcs[s]:
                if not labels.get(t):
                    continue
                steps = self.sec_block(sec, s, seq)
                for L in labels[t]:
                    c, p = self.fold(L[0], L[1], steps)
                    cand.append((c, p, L, x, seq))
            cand.sort(key=lambda r: (r[0], r[1]))            # stable: ties keep generation order
            front, best_p = [], math.inf
            for r in cand:
                if r[1] < best_p:
                    if max_labels is not None and len(front) >= max_labels:
                        exact = False
                        break
                    front.append(r)
                    best_p = r[1]
            labels[s] = front
            biggest = max(biggest, len(front))
            total += len(front)
        s0 = self.close(0)
        steps0 = self.sec_block(sec, 0, root_seq)
        best, best_c = None, math.inf
        for L in labels.get(s0, []):
            c, _ = self.fold(L[0], L[1], steps0)
            if c < best_c:
                best, best_c = L, c
        if best is None:
            raise RuntimeError("E2: no path from the root (internal error)")
        sigma = list(root_seq)
        L = best
        while L[2] is not None:
            sigma += L[4]
            L = L[2]
        if len(sigma) != g.n:
            raise RuntimeError("E2: traceback length mismatch")
        stats = dict(nodes=len(nodes) + 1, arcs=sum(len(a) for a in arcs.values()),
                     max_labels=biggest, labels_total=total)
        return B, sigma[::-1], best_c, exact, stats

    def all_path_costs(self, sec):
        """Brute force for check(): the cost of every path of Γ, each evaluated on its full
        τ ordering with sec_cost_of_order (independent of the fold)."""
        B, nodes, arcs, root_seq = self.graph_of_optima()
        self.g.width = B
        full = self.g.full
        out = []
        def rec(s, sigma):
            if s == full:
                out.append(self.sec_cost_of_order(sec, sigma[::-1]))
                return
            for x, t, seq in arcs[s]:
                rec(t, sigma + seq)
        s0 = self.close(0)
        if s0 == full:
            out.append(self.sec_cost_of_order(sec, root_seq[::-1]))
        else:
            rec(s0, list(root_seq))
        return out

    def _order(self, T, t, root_seq):
        chain = []
        k = self.key(t)
        while T[k] is not None:
            pk, x = T[k]
            chain.append((pk, x))
            k = pk
        order = list(root_seq)
        for pk, x in reversed(chain):
            s = self.decode(pk)
            _, seq = self.apply(s, x)
            order += seq
        return order

    def _check_arc(self, s, x, c, t, seq):
        # O1: given cost equals the derived block cost
        d = self.derived_cost(s, seq)
        if c != d:
            raise AssertionError(f"O1 fails: cost {c} != derived {d} at S={s:#x}, x={x}")
        # O3: decode(key(t)) == t
        if self.decode(self.key(t)) != t:
            raise AssertionError(f"O3 fails at T={t:#x}")
        # O4: replay
        if self.apply(s, x) != (t, seq):
            raise AssertionError("O4 fails")


def brute(e: Eager) -> int:
    """min over orderings of the bottleneck of w, by DP over all subsets."""
    g = e.g
    full = g.full
    F = {full: 0}
    for S in sorted(range(full), key=lambda m: -m.bit_count()):
        F[S] = min(max(e.w(S, v), F[S | 1 << v]) for v in bits(full & ~S))
    return F[0] if g.n else 0


def ordering_width(e: Eager, order: list[int]) -> int:
    S, c = 0, 0
    for v in order:
        c = max(c, e.w(S, v))
        S |= 1 << v
    return c
