"""The lemma library.  Each lemma states its hypothesis and conclusion, a
reference, and (where possible) a syntactic check on the IR and/or a runtime
check on the bound graph data.  Problem.report() lists, for every clause,
whether its hypothesis was checked syntactically, checked at run time, or is an
explicit assumption."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .ir import FULL, Node, subst, var, SET, VERT, walk


@dataclass(frozen=True)
class Lemma:
    name: str
    hypothesis: str
    conclusion: str
    reference: str
    syntactic: Callable | None = None   # (problem, clause) -> str | None (None = holds; str = reason it fails)
    runtime: Callable | None = None     # (problem, clause, gdata) -> None, raises on failure

    def __repr__(self):
        return f"lemma.{self.name}"


# --------------------------------------------------------- syntactic checks
def _is_cut_of_S(p, node):
    return node.op == "cut" and node.args[0] is p.S.node


def _coverage_parts(p, node):
    """Match |bigunion(S, F) ∖ S| ; return F name or None."""
    if node.op == "card" and node.args[0].op == "sub":
        a, b = node.args[0].args
        if b is p.S.node and a.op == "bigunion" and a.args[0] is p.S.node:
            return a.args[1]
    return None


def _chk_submod_cut(p, clause):
    return None if _is_cut_of_S(p, p.f_node) else "cost is not |E(S, V∖S)| (cut(S))"


def _chk_submod_coverage(p, clause):
    return None if _coverage_parts(p, p.f_node) else "cost is not |⋃_{u∈S} F(u) ∖ S|"


def derivative(p):
    """f(S+v) − f(S) as an IR node when f is a library form, with v ∉ S."""
    S, v = p.S.node, p.v.node
    if _is_cut_of_S(p, p.f_node):
        from .ir import N, deg, card, VertE, SetE
        return (deg(VertE(v)) - 2 * card(N(VertE(v)) & SetE(S))).node
    return None


def _strip_le0(pred):
    """pred = (e ≤ 0) → e"""
    if pred.op == "le" and pred.args[1].op == "int" and pred.args[1].args[0] == 0:
        return pred.args[0]
    return None


def _chk_greedy(p, clause):
    """Closure predicate implies f(S+v) ≤ f(S), for the library cost forms."""
    if p.f_node is None:
        return "greedy needs a cost of the form f(S+v)"
    pred, S, v = clause.pred, p.S.node, p.v.node
    d = derivative(p)
    if d is not None:
        e = _strip_le0(pred)
        if e is d:
            return None
        return "predicate is not syntactically Δ(S,v) ≤ 0"
    F = _coverage_parts(p, p.f_node)
    if F is not None:
        nb = Node("bigunion", (S, F), SET)
        Fv = Node(F, (v,), SET) if F in ("N", "Nin", "Nout") else Node("vfun", (F, v), SET)
        closed = Node("or", (S, nb), SET)
        # rule 1: F(v) ⊆ S ∪ nb(S)   (then boundary loses v at most, gains nothing)
        if pred.op == "subset" and pred.args[0] is Fv and pred.args[1] is closed:
            return None
        # rule 2: v ∈ nb(S) ∧ |F(v) ∖ (S ∪ nb(S))| = 1   (gains one, loses v)
        if pred.op == "land":
            l, r = pred.args
            if (l.op == "member" and l.args[0] is v and l.args[1] is nb and r.op == "eq"
                    and r.args[1].op == "int" and r.args[1].args[0] == 1 and r.args[0].op == "card"
                    and r.args[0].args[0] is Node("sub", (Fv, closed), SET)):
                return None
        return "predicate is not one of the coverage rules F(v) ⊆ S∪nb(S), v∈nb(S) ∧ |F(v)∖(S∪nb(S))|=1"
    return "no derivative rule for this cost"


def _chk_choose_trivial(p, clause):
    o = clause.over
    return None if (o.op == "sub" and o.args[0] is FULL and o.args[1] is p.S.node) else "choose is not V ∖ S"


def _chk_key_trivial(p, clause):
    return None if p.key_node is p.S.node else "key is not S"


def _chk_cover_nf(p, clause):
    if not _is_cut_of_S(p, p.f_node):
        return "cover-normal-form is a cutwidth lemma"
    o = clause.over
    if not (o.op == "sub" and o.args[0].op == "cset" and o.args[1] is p.S.node):
        return "choose must range over C ∖ S for a constant set C"
    return None


def _rt_cover(p, clause, g):
    o = clause.over
    C = g.csets[o.args[0].args[0]]
    nb = g.nb
    for v in range(g.n):
        if not C >> v & 1 and nb[v] & ~C:
            raise ValueError(f"{o.args[0].args[0]} is not a vertex cover (vertex {g.labels[v]!r})")


def _rt_twins(p, clause, g):
    cls = g.vfuns["_twclass"]
    for cs in clause.preserves:
        C = g.csets[cs.name]
        for v in range(g.n):
            if C >> v & 1:
                if cls[v] & ~C:
                    raise ValueError(f"{cs.name} is not closed under twins (vertex {g.labels[v]!r})")


def _chk_normal_key(p, clause):
    k = p.key_node
    if k.op == "and" and p.S.node in k.args and any(a.op == "cset" for a in k.args):
        return None
    return "key must be S ∩ K for a constant set K"


# ------------------------------------------------------------------ library
trivial = Lemma("trivial", "choose = V ∖ S (no restriction), or key = S",
                "O2 / O3 hold trivially", "—", None)
greedy = Lemma(
    "greedy", "w(S,v) = f(S+v), f submodular, closure predicate ⇒ f(S+v) ≤ f(S)",
    "if a completion from S has bottleneck ≤ B, so does one starting with v; "
    "the closure never raises the arc cost",
    "move v to the front: f(A+v) ≤ f(A) + f(S+v) − f(S) ≤ f(A) for A ⊇ S (submodularity)",
    _chk_greedy)
submod_cut = Lemma("submod_cut", "f(S) = |E(S, V∖S)|", "f is symmetric submodular", "standard",
                   _chk_submod_cut)
submod_coverage = Lemma("submod_coverage", "f(S) = |⋃_{u∈S} F(u) ∖ S|",
                        "f is submodular (coverage minus modular)", "standard", _chk_submod_coverage)
cover_normal_form = Lemma(
    "cover_normal_form",
    "cutwidth; C a vertex cover; vertices outside C enter only by closure or as the "
    "prefix Y(S,x)[:i], Y = ⟨u ∈ N(x)∖C∖S : deg u odd, Δ(S,u) = 1⟩, i = min(|Y|, max(0, ⌊Δ(S,x)/2⌋))",
    "some optimal ordering is a path of such moves; the arc cost is f(S) + max(i, Δ(S,x) − i)",
    "Cygan, Lokshtanov, Pilipczuk, Pilipczuk, Saurabh, Algorithmica 68 (2014); "
    "doc/other_widths.md for the prefix form", _chk_cover_nf, _rt_cover)
twins = Lemma("twins", "u, v with N[u] = N[v] or N(u) = N(v); every set in `preserves` is twin-closed",
              "(u v) ∈ Aut(G); choosing only the smallest unplaced twin preserves O2",
              "automorphism argument", None, _rt_twins)
normal_key = Lemma("normal_key", "key s = s ∩ K and closure(s ∩ K) = s for every normal state s",
                   "key is injective on normal states and decode = closure",
                   "checked on every reached state by Problem.check()", _chk_normal_key)
simplicial = Lemma("simplicial", "treewidth; v simplicial in the elimination graph G_S",
                   "eliminating v next is safe (tw(G_S) = max(deg v, tw(G_S − v)))", "standard")
components = Lemma("components", "the width is the maximum over connected components",
                   "solve each component separately", "an ordering of a disjoint union can be concatenated")
