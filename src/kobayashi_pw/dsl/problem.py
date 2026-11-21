"""Problem: the user-facing embedded DSL (Layer P plus Layer D annotations)."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import lemma as L
from .eager import Eager, GData, bits, brute, ordering_width
from .ir import (FULL, SET, VERT, ConstSet, Node, SetE, VFun, VertE, _n, pretty, subst, var, wrap)
from .rewrite import rewrite


@dataclass
class Closure:
    pred: Node
    by: L.Lemma
    status: str = ""


@dataclass
class Choose:
    over: Node
    prefix: Node | None
    cost: Node | None
    by: L.Lemma
    over_minus_S: Node | None = None
    status: str = ""


@dataclass
class Symmetry:
    by: L.Lemma
    preserves: list
    vfun: str = "_tw"


@dataclass
class Solution:
    width: int | None
    order: list | None
    lower_bound: int
    stats: dict = field(default_factory=dict)
    mode: str = ""


class Problem:
    def __init__(self, name: str, directed: bool = False):
        self.name, self.directed = name, directed
        self.S_name, self.v_name, self.x_name = "S", "v", "x"
        self.S = SetE(var("S", SET))
        self.v = VertE(var("v", VERT))
        self.x = VertE(var("x", VERT))
        self.f_node = self.w_node = None
        self.cost_by = None
        self.closures: list[Closure] = []
        self.move: Choose | None = None
        self.choice_filters: list[Node] = []
        self.symmetries: list[Symmetry] = []
        self.key_node = self.S.node
        self.key_by = L.trivial
        self.split_components = False
        self.consts: dict[str, ConstSet] = {}
        self.vfuns: dict[str, VFun] = {}
        self.ann: dict = {"maintain": [], "probe": False, "closure": "auto"}
        self.maintained: list[Node] = []
        self.families: list[str] = []

    # ------------------------------------------------------------ Layer P
    def cost_f(self, fn, by):
        """Step cost w(S, v) = f(S + v); returns f as a symbolic function."""
        self.f_node = _n(fn(self.S))
        T = Node("or", (self.S.node, Node("single", (self.v.node,), SET)), SET)
        self.w_node = subst(self.f_node, {"S": T})
        self.cost_by = by
        f_node = self.f_node
        return lambda A: wrap(subst(f_node, {"S": _n(A)}))

    def cost_w(self, fn, by=L.trivial):
        """General step cost w(S, v)."""
        self.w_node = _n(fn(self.S, self.v))
        self.cost_by = by

    def const_set(self, name, fn):
        c = ConstSet(name, fn)
        self.consts[name] = c
        return c.sym

    def const_vfun(self, name, fn):
        f = VFun(name, fn)
        self.vfuns[name] = f
        return f

    def closure(self, fn, by):
        self.closures.append(Closure(_n(fn(self.S, self.v)), by))

    def choose(self, over=None, prefix=None, cost=None, by=L.trivial):
        o = _n(over(self.S)) if over is not None else Node("sub", (FULL, self.S.node), SET)
        self.move = Choose(o, _n(prefix(self.S, self.x)) if prefix else None,
                             _n(cost(self.S, self.x)) if cost else None, by)
        self.move.over_minus_S = o if (o.op == "sub" and o.args[1] is self.S.node) else Node("sub", (o, self.S.node), SET)

    def symmetry(self, by, preserves=()):
        if by is not L.twins:
            raise ValueError("only lemma.twins is implemented")
        sym = Symmetry(by, list(preserves))
        self.symmetries.append(sym)
        tw = Node("vfun", ("_tw", self.x.node), SET)
        self.choice_filters.append(Node("subset", (tw, self.S.node), "Bool"))

    def key(self, fn, by):
        self.key_node = _n(fn(self.S))
        self.key_by = by

    def components(self, by=L.components):
        self.split_components = True

    # ------------------------------------------------------------ Layer D
    def impl(self, maintain=(), probe=False, closure="auto", carry=False):
        """Layer D.  maintain: quantities kept incrementally, each either
          S -> ⋃_{u∈S} F(u)          (a set; children copy it), or
          (S, v) -> |F(v) ∩ S|      (a vertex-indexed counter family; moves are
                                     applied in place and undone).
        F ∈ {N, Nin, Nout}."""
        import inspect
        self.ann = {"maintain": list(maintain), "probe": probe, "closure": closure, "carry": carry}
        self.maintained, self.families = [], []
        for m in maintain:
            if len(inspect.signature(m).parameters) == 2:
                node = _n(m(self.S, self.v))
                ok = (node.op == "card" and node.args[0].op == "and" and node.args[0].args[1] is self.S.node
                      and node.args[0].args[0].op in ("N", "Nin", "Nout") and node.args[0].args[0].args[0] is self.v.node)
                if not ok:
                    raise ValueError(f"counter families must be |F(v) ∩ S|; got {pretty(node)}")
                self.families.append(node.args[0].args[0].op)
                continue
            node = _n(m(self.S))
            if node.op != "bigunion" or node.args[0] is not self.S.node:
                raise ValueError(f"set-valued maintenance supports ⋃_{{u∈S}} F(u); got {pretty(node)}")
            self.maintained.append(node)
        if self.families and self.maintained:
            raise ValueError("milestone 1: counter families and maintained sets cannot be combined")
        return self

    # ------------------------------------------------------------ derived
    @property
    def derived_cost(self) -> Node:
        """f(S + x), rewritten in terms of S (x ∉ S)."""
        if self.f_node is None:
            raise ValueError("derived cost needs cost_f (or give choose(cost=...))")
        T = Node("or", (self.S.node, Node("single", (self.x.node,), SET)), SET)
        return rewrite(subst(self.f_node, {"S": T}), self.S.node, self.x.node)

    def _prepare(self):
        if self.w_node is None:
            raise ValueError("no cost clause")
        if self.move is None:
            self.choose(by=L.trivial)

    # ------------------------------------------------------------ binding
    def bind(self, g) -> GData:
        gd = g if isinstance(g, GData) else GData.from_graph(g)
        gd = GData(gd.n, gd.nin, gd.nout, gd.labels, dict(gd.csets), dict(gd.vfuns))
        tw, cls = twin_tables(gd)
        gd.vfuns["_tw"], gd.vfuns["_twclass"] = tw, cls
        for name, c in self.consts.items():
            gd.csets[name] = c.fn(gd)
        for name, f in self.vfuns.items():
            gd.vfuns[name] = f.fn(gd)
        for cl in [self.move] + self.symmetries:
            if cl is not None and cl.by.runtime:
                cl.by.runtime(self, cl, gd)
        return gd

    @property
    def const_order(self):
        return sorted(self.consts)

    @property
    def vfun_order(self):
        return ["_tw", "_twclass"] + sorted(self.vfuns)

    def compile_ok(self) -> str | None:
        """Reason why compiled mode is unavailable, or None."""
        for c in self.closures:
            if c.by is not L.greedy:
                return f"closure justified by {c.by.name}, not greedy: its cost may exceed the move's"
        if self.move.prefix is not None and self.move.cost is None:
            return "a prefix move needs a closed-form cost in compiled mode"
        if self.move.cost is None and self.f_node is None:
            return "derived cost needs cost_f"
        return None

    # ------------------------------------------------------------ solving
    def solve(self, g, mode="auto", time_limit=None, max_states=None, debug=False) -> Solution:
        self._prepare()
        gd0 = g if isinstance(g, GData) else GData.from_graph(g)
        comps = components(gd0) if self.split_components else [list(range(gd0.n))]
        width, order, lb, stats, used = 0, [], 0, {"states": 0, "expansions": 0}, mode
        for comp in comps:
            gd = self.bind(gd0.sub(comp))
            if len(comp) == 1 and self.split_components:
                order.append(gd.labels[0]); continue
            m = mode
            if m == "auto":
                from .jit import compiler
                m = "c" if compiler() and self.compile_ok() is None else "eager"
            used = m
            if m == "eager":
                w, o, st = Eager(self, gd).solve(max_states=max_states)
                if w is None:
                    return Solution(None, None, max(lb, o), stats, m)
                stats["states"] += st["states"]; stats["expansions"] += st.get("expansions", 0)
            else:
                why = self.compile_ok()
                if why:
                    raise ValueError(f"compiled mode unavailable: {why}")
                from . import jit
                from .codegen import generate
                W = jit.w_bucket(gd.n)
                so = jit.build(generate(self), W, debug)
                R, o = jit.run(so, gd, W, self.const_order, self.vfun_order, time_limit, max_states)
                stats["states"] += int(R.states); stats["expansions"] += int(R.expansions)
                stats["seconds"] = stats.get("seconds", 0) + R.seconds
                if R.status != 0:
                    if R.status >= 3:
                        raise RuntimeError({3: "out of memory", 4: "V unreachable (spec error)",
                                            5: "replay mismatch (O4)"}.get(R.status, R.status))
                    return Solution(None, None, max(lb, width, R.lower_bound), stats, m)
                w = R.width
                chk = ordering_width(Eager(self, gd), o)
                if chk != w:
                    raise AssertionError(f"compiled ordering has width {chk}, search said {w}")
            width = max(width, w)
            order += [gd.labels[v] for v in o]
        return Solution(width, order, width, stats, used)

    # ------------------------------------------------------------ checking
    def check(self, n_max=9, trials=200, seed=0, modes=("eager", "c"), density=None, verbose=False):
        """Randomised obligation checks: O1/O3/O4 on every eager arc, closure
        hypotheses (f(S+v) ≤ f(S), monotonicity), widths vs brute force in
        every mode.  Returns the number of graphs checked; raises on failure."""
        from .jit import compiler
        self._prepare()
        rng = random.Random(seed)
        modes = [m for m in modes if m != "c" or (compiler() and self.compile_ok() is None)]
        for t in range(trials):
            n = rng.randint(1, n_max)
            p = density if density is not None else rng.random()
            nin = [0] * n
            for a in range(n):
                for b in range(n):
                    if a != b and (self.directed or a < b) and rng.random() < p:
                        nin[b] |= 1 << a
                        if not self.directed:
                            nin[a] |= 1 << b
            if not self.directed and t % 4 == 1 and n < n_max:       # add a twin
                v = rng.randrange(n); w_ = n; n += 1
                nb = nin[v]; nin.append(nb | ((1 << v) if rng.random() < 0.5 else 0))
                for u in bits(nin[w_]):
                    nin[u] |= 1 << w_
            gd0 = GData.from_graph(type("G", (), {"n": n, "nin": nin, "labels": list(range(n))})())
            ref = brute(Eager(self, self.bind(gd0)))
            for comp in (components(gd0) if self.split_components else [list(range(n))]):
                gd = self.bind(gd0.sub(comp))
                e = Eager(self, gd)
                self._check_closure(e, rng)
                e.solve(check=True)
            for m in modes:
                s = self.solve(gd0, mode=m)
                if s.width != ref:
                    raise AssertionError(f"{m}: width {s.width} != brute {ref} on n={n}, nin={nin}")
                if ordering_width(Eager(self, self.bind(gd0)), [gd0.labels.index(x) for x in s.order]) != ref:
                    raise AssertionError(f"{m}: ordering width wrong on nin={nin}")
            if verbose:
                print(t, n, ref)
        return trials

    def _check_closure(self, e: Eager, rng):
        g = e.g
        for _ in range(20):
            S = rng.getrandbits(g.n) & g.full if g.n else 0
            for v in bits(g.full & ~S):
                k = e.closure_rule(S, v)
                if k is None:
                    continue
                if self.closures[k].by is L.greedy and e.f(S | 1 << v) > e.f(S):
                    raise AssertionError(f"greedy hypothesis fails: f(S+v) > f(S) at S={S:#x}, v={v}")
                S2 = S | (rng.getrandbits(g.n) & g.full & ~(1 << v))
                if not S2 >> v & 1 and e.closure_rule(S2, v) is None:
                    raise AssertionError("closure predicate is not monotone in S")

    # ------------------------------------------------------------ reporting
    def report(self) -> str:
        self._prepare()
        rows = []
        def row(what, lem, chk):
            status = "assumed" if chk is None else ("checked" if chk(self, None) is None else "FAILS: " + chk(self, None))
            rows.append(f"  {what:<10} by {lem.name:<18} [{status}]  {lem.hypothesis}")
        if self.f_node is None:
            rows.append(f"  {'cost':<10} given directly as w(S, v){'':<6} [no lemma needed]")
        elif self.cost_by:
            row("cost", self.cost_by, self.cost_by.syntactic)
        for c in self.closures:
            r = c.by.syntactic(self, c) if c.by.syntactic else "assumed"
            rows.append(f"  {'closure':<10} by {c.by.name:<18} [{'checked' if r is None else ('assumed' if r == 'assumed' else 'FAILS: ' + r)}]  {c.by.hypothesis}")
        ch = self.move
        if ch.by is L.trivial:
            r = L._chk_choose_trivial(self, ch)
        else:
            r = ch.by.syntactic(self, ch) if ch.by.syntactic else "assumed"
        extra = " + run-time check" if ch.by.runtime else ""
        rows.append(f"  {'choose':<10} by {ch.by.name:<18} [{'checked' + extra if r is None else ('assumed' + extra if r == 'assumed' else 'FAILS: ' + r)}]  {ch.by.hypothesis}")
        for s in self.symmetries:
            rows.append(f"  {'symmetry':<10} by {s.by.name:<18} [run-time check]  {s.by.hypothesis}")
        kb = self.key_by
        r = L._chk_key_trivial(self, None) if kb is L.trivial else (kb.syntactic(self, None) if kb.syntactic else "assumed")
        rows.append(f"  {'key':<10} by {kb.name:<18} [{'checked' if r is None else 'FAILS: ' + r}]  {kb.hypothesis}")
        if self.split_components:
            rows.append(f"  {'components':<10} by components{'':<8} [assumed]  {L.components.hypothesis}")
        rows.append("  engine     Theorem E (doc/dsl_design.md §1.2) given O1–O4; "
                    "O1, O3, O4 and the closure hypotheses are tested by check()")
        return f"problem {self.name}:\n" + "\n".join(rows)

    def pretty(self) -> str:
        self._prepare()
        L_ = [f"problem {self.name}({'Digraph' if self.directed else 'Graph'}) {{"]
        if self.f_node is not None:
            L_.append(f"  cost     f(S) = {pretty(self.f_node)}   by {self.cost_by.name}")
        else:
            L_.append(f"  cost     w(S, v) = {pretty(self.w_node)}")
        for name in self.consts:
            L_.append(f"  const    {name} = {self.consts[name].fn.__name__}(G)")
        for c in self.closures:
            L_.append(f"  closure  {pretty(c.pred)}   by {c.by.name}")
        ch = self.move
        L_.append(f"  choose   x ∈ {pretty(ch.over)}   by {ch.by.name}")
        if ch.prefix is not None:
            L_.append(f"    prefix {pretty(ch.prefix)}")
        if ch.cost is not None:
            L_.append(f"    cost   {pretty(ch.cost)}")
        for s in self.symmetries:
            L_.append(f"  symmetry twins preserving {', '.join(c.name for c in s.preserves)}   by {s.by.name}")
        L_.append(f"  key      {pretty(self.key_node)}   by {self.key_by.name}")
        if self.split_components:
            L_.append("  components   by components")
        L_.append("}")
        if self.maintained:
            L_.append(f"impl {{ maintain {', '.join(pretty(m) for m in self.maintained)}"
                      f"{'; probe before-closure' if self.ann.get('probe') else ''} }}")
        return "\n".join(L_)


# ---------------------------------------------------------------- helpers
def components(g: GData) -> list[list[int]]:
    nb, seen, out = g.nb, 0, []
    for s in range(g.n):
        if seen >> s & 1:
            continue
        comp, st = 1 << s, [s]
        while st:
            x = st.pop()
            for y in bits(nb[x] & ~comp):
                comp |= 1 << y; st.append(y)
        seen |= comp
        out.append(list(bits(comp)))
    return out


def twin_tables(g: GData):
    """(_tw[v] = smaller twins of v, _twclass[v] = whole twin class of v).
    Twins: same in- and out-neighbourhoods, either closed (adjacent both ways) or open."""
    groups: dict = {}
    for v in range(g.n):
        b = 1 << v
        groups.setdefault(("c", g.nin[v] | b, g.nout[v] | b), []).append(v)
        groups.setdefault(("o", g.nin[v], g.nout[v]), []).append(v)
    cls = [1 << v for v in range(g.n)]
    for members in groups.values():
        if len(members) > 1:
            m = 0
            for v in members:
                m |= 1 << v
            for v in members:
                cls[v] = m
    tw = [cls[v] & ((1 << v) - 1) for v in range(g.n)]
    return tw, cls
