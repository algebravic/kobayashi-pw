"""Typed, hash-consed IR for set-determined layout specifications.

Nodes are immutable and interned: structurally equal expressions are the same
object, so common subexpressions are shared and maintained quantities can be
recognised by identity.  User code never builds nodes directly; it uses the
symbolic wrappers (SetE, IntE, BoolE, VertE, SeqE) whose operators record
nodes.  Converting a symbolic value to a Python bool raises an error (the
tracing rule of torch.fx): data-dependent choices must use where/min/max.
"""
from __future__ import annotations

import itertools

SET, INT, BOOL, VERT, SEQ = "Set", "Int", "Bool", "Vertex", "Seq"

_table: dict = {}
_fresh = itertools.count()


class Node:
    __slots__ = ("op", "args", "type", "_free", "__weakref__")

    def __new__(cls, op, args, typ):
        key = (op, args, typ)
        n = _table.get(key)
        if n is None:
            n = object.__new__(cls)
            n.op, n.args, n.type, n._free = op, args, typ, None
            _table[key] = n
        return n

    def __repr__(self):
        return pretty(self)

    @property
    def free(self) -> frozenset:
        """Free variables (names) of the expression."""
        if self._free is None:
            if self.op == "var":
                f = frozenset([self.args[0]])
            else:
                f = frozenset()
                for a in self.args:
                    if isinstance(a, Node):
                        f |= a.free
                if self.op in BINDERS:           # (A, var-node, body)
                    f = (self.args[0].free | (self.args[2].free - {self.args[1].args[0]}))
            self._free = f
        return self._free


# binders: args = (domain set, bound var node, body)
BINDERS = {"filter", "seq", "sum", "forall", "exists"}


def var(name, typ):
    return Node("var", (name, typ), typ)


def fresh_vertex(prefix="u"):
    return var(f"{prefix}{next(_fresh)}", VERT)


# ------------------------------------------------------------------ wrappers
class Sym:
    __slots__ = ("node",)

    def __init__(self, node):
        self.node = node

    def __bool__(self):
        raise TypeError("a symbolic value cannot be used as a Python bool; use where/min/max")

    def __repr__(self):
        return pretty(self.node)


def _n(x, want=None):
    """Coerce to a Node."""
    if isinstance(x, Sym):
        return x.node
    if isinstance(x, Node):
        return x
    if isinstance(x, bool):
        return Node("bool", (x,), BOOL)
    if isinstance(x, int):
        return Node("int", (x,), INT)
    raise TypeError(f"cannot use {x!r} in a specification")


def wrap(node):
    return {SET: SetE, INT: IntE, BOOL: BoolE, VERT: VertE, SEQ: SeqE}[node.type](node)


def _chk(node, typ, what):
    if node.type != typ:
        raise TypeError(f"{what}: expected {typ}, got {node.type} ({pretty(node)})")
    return node


class SetE(Sym):
    def __or__(self, o): return SetE(Node("or", (self.node, _chk(_n(o), SET, "|")), SET))
    def __and__(self, o): return SetE(Node("and", (self.node, _chk(_n(o), SET, "&")), SET))
    def __sub__(self, o): return SetE(Node("sub", (self.node, _chk(_n(o), SET, "-")), SET))
    def __invert__(self): return SetE(Node("sub", (FULL, self.node), SET))
    __ror__ = __or__
    __rand__ = __and__


class IntE(Sym):
    def _b(self, op, o, typ=INT):
        return wrap(Node(op, (self.node, _chk(_n(o), INT, op)), typ))
    def _r(self, op, o):
        return wrap(Node(op, (_chk(_n(o), INT, op), self.node), INT))
    def __add__(self, o): return self._b("add", o)
    def __radd__(self, o): return self._r("add", o)
    def __sub__(self, o): return self._b("isub", o)
    def __rsub__(self, o): return self._r("isub", o)
    def __mul__(self, o): return self._b("mul", o)
    def __rmul__(self, o): return self._r("mul", o)
    def __floordiv__(self, o): return self._b("fdiv", o)
    def __neg__(self): return IntE(Node("isub", (_n(0), self.node), INT))
    def __lt__(self, o): return self._b("lt", o, BOOL)
    def __le__(self, o): return self._b("le", o, BOOL)
    def __gt__(self, o): return wrap(Node("lt", (_chk(_n(o), INT, ">"), self.node), BOOL))
    def __ge__(self, o): return wrap(Node("le", (_chk(_n(o), INT, ">="), self.node), BOOL))
    def __eq__(self, o): return self._b("eq", o, BOOL)
    def __ne__(self, o): return wrap(Node("not", (self._b("eq", o, BOOL).node,), BOOL))
    __hash__ = object.__hash__


class BoolE(Sym):
    def __and__(self, o): return BoolE(Node("land", (self.node, _chk(_n(o), BOOL, "&")), BOOL))
    def __or__(self, o): return BoolE(Node("lor", (self.node, _chk(_n(o), BOOL, "|")), BOOL))
    def __invert__(self): return BoolE(Node("not", (self.node,), BOOL))
    __rand__ = __and__
    __ror__ = __or__


class VertE(Sym):
    pass


class SeqE(Sym):
    def __getitem__(self, sl):
        if not isinstance(sl, slice) or sl.start is not None or sl.step is not None:
            raise TypeError("only prefixes seq[:k] are supported")
        return SeqE(Node("take", (self.node, _chk(_n(sl.stop), INT, "seq[:k]")), SEQ))


FULL = Node("full", (), SET)
EMPTY = Node("empty", (), SET)


# ---------------------------------------------------------------- functions
def N(v):    return SetE(Node("N", (_chk(_n(v), VERT, "N"),), SET))
def Nin(v):  return SetE(Node("Nin", (_chk(_n(v), VERT, "Nin"),), SET))
def Nout(v): return SetE(Node("Nout", (_chk(_n(v), VERT, "Nout"),), SET))
def deg(v):  return IntE(Node("deg", (_chk(_n(v), VERT, "deg"),), INT))
def single(v): return SetE(Node("single", (_chk(_n(v), VERT, "single"),), SET))


def card(A):
    a = _n(A)
    if a.type not in (SET, SEQ):
        raise TypeError("card of a non-set")
    return IntE(Node("card", (a,), INT))


def member(v, A): return BoolE(Node("member", (_chk(_n(v), VERT, "member"), _chk(_n(A), SET, "member")), BOOL))
def subset(A, B): return BoolE(Node("subset", (_chk(_n(A), SET, "subset"), _chk(_n(B), SET, "subset")), BOOL))
def cut(A): return IntE(Node("cut", (_chk(_n(A), SET, "cut"),), INT))
def odd(e): return BoolE(Node("odd", (_chk(_n(e), INT, "odd"),), BOOL))


def imin(a, b): return IntE(Node("min", (_chk(_n(a), INT, "min"), _chk(_n(b), INT, "min")), INT))
def imax(a, b): return IntE(Node("max", (_chk(_n(a), INT, "max"), _chk(_n(b), INT, "max")), INT))


def where(c, a, b):
    an, bn = _n(a), _n(b)
    if an.type != bn.type:
        raise TypeError("where: branches differ in type")
    return wrap(Node("where", (_chk(_n(c), BOOL, "where"), an, bn), an.type))


def bigunion(A, fn):
    """U_{u in A} fn(u) for fn in {N, Nin, Nout} or a vertex-set constant."""
    name = {N: "N", Nin: "Nin", Nout: "Nout"}.get(fn)
    if name is None:
        if isinstance(fn, VFun):
            name = fn.name
        else:
            raise TypeError("bigunion: fn must be N, Nin, Nout or a vertex-set constant")
    return SetE(Node("bigunion", (_chk(_n(A), SET, "bigunion"), name), SET))


def _maxbeta(node) -> int:
    m = 0
    for x in walk(node):
        if x.op in BINDERS:
            m = max(m, int(x.args[1].args[0][1:]))
    return m


def _binder(op, A, body, typ, btyp):
    """Build a binder node with a canonical bound-variable name β<k>, k one more
    than any binder index inside the body, so that alpha-equivalent traces of
    the same comprehension are the same (hash-consed) node."""
    a = _chk(_n(A), SET, op)
    u = fresh_vertex()
    b = _chk(_n(body(VertE(u))), btyp, op)
    beta = var(f"β{_maxbeta(b) + 1}", VERT)
    b = subst(b, {u.args[0]: beta})
    return wrap(Node(op, (a, beta, b), typ))


def filt(A, pred):  return _binder("filter", A, pred, SET, BOOL)
def seq(A, pred=lambda u: True):  return _binder("seq", A, pred, SEQ, BOOL)
def isum(A, f):     return _binder("sum", A, f, INT, INT)
def forall(A, p):   return _binder("forall", A, p, BOOL, BOOL)
def exists(A, p):   return _binder("exists", A, p, BOOL, BOOL)


def qset(S, v):
    """Q(S, v): vertices outside S+v reachable from v through S (eager only)."""
    return SetE(Node("qset", (_chk(_n(S), SET, "qset"), _chk(_n(v), VERT, "qset")), SET))


class ConstSet:
    """A graph-dependent constant set, computed at solve time by fn(graph)."""
    def __init__(self, name, fn):
        self.name, self.fn = name, fn
        self.sym = SetE(Node("cset", (name,), SET))


class VFun:
    """A graph-dependent vertex -> set constant, fn(graph) -> list of masks."""
    def __init__(self, name, fn):
        self.name, self.fn = name, fn

    def __call__(self, v):
        return SetE(Node("vfun", (self.name, _chk(_n(v), VERT, self.name)), SET))


# ------------------------------------------------------------ substitution
def subst(node, mapping):
    """Replace variables (by name) by nodes; respects binders."""
    if not (node.free & mapping.keys()):
        return node
    if node.op == "var":
        return mapping[node.args[0]]
    if node.op in BINDERS:
        a, u, b = node.args
        inner = {k: v for k, v in mapping.items() if k != u.args[0]}
        return Node(node.op, (subst(a, mapping), u, subst(b, inner)), node.type)
    return Node(node.op, tuple(subst(x, mapping) if isinstance(x, Node) else x for x in node.args), node.type)


def walk(node):
    """All subnodes (pre-order, unique)."""
    seen, out, st = set(), [], [node]
    while st:
        x = st.pop()
        if id(x) in seen:
            continue
        seen.add(id(x))
        out.append(x)
        for a in x.args:
            if isinstance(a, Node):
                st.append(a)
    return out


# ------------------------------------------------------------ pretty printer
_INF = {"or": "∪", "and": "∩", "sub": "∖", "add": "+", "isub": "−", "mul": "·", "fdiv": "//",
        "lt": "<", "le": "≤", "eq": "=", "land": "∧", "lor": "∨"}


def pretty(n) -> str:
    if isinstance(n, Sym):
        n = n.node
    op, a = n.op, n.args
    if op == "var":
        return a[0]
    if op in ("int", "bool"):
        return str(a[0])
    if op == "full":
        return "V"
    if op == "empty":
        return "∅"
    if op == "sub" and a[0] is FULL:
        return f"(V ∖ {pretty(a[1])})"
    if op in _INF:
        return f"({pretty(a[0])} {_INF[op]} {pretty(a[1])})"
    if op == "not":
        if a[0].op == "eq":
            return f"({pretty(a[0].args[0])} ≠ {pretty(a[0].args[1])})"
        return f"¬{pretty(a[0])}"
    if op == "card":
        return f"|{pretty(a[0])}|"
    if op == "single":
        return f"{{{pretty(a[0])}}}"
    if op == "member":
        return f"({pretty(a[0])} ∈ {pretty(a[1])})"
    if op == "subset":
        return f"({pretty(a[0])} ⊆ {pretty(a[1])})"
    if op == "cset":
        return a[0]
    if op == "vfun":
        return f"{a[0]}({pretty(a[1])})"
    if op == "bigunion":
        return f"⋃_{{u∈{pretty(a[0])}}} {a[1]}(u)"
    if op == "filter":
        return f"{{{pretty(a[1])} ∈ {pretty(a[0])} : {pretty(a[2])}}}"
    if op == "seq":
        return f"⟨{pretty(a[1])} ∈ {pretty(a[0])} : {pretty(a[2])}⟩"
    if op == "take":
        return f"{pretty(a[0])}[:{pretty(a[1])}]"
    if op == "sum":
        return f"Σ_{{{pretty(a[1])}∈{pretty(a[0])}}} {pretty(a[2])}"
    if op in ("forall", "exists"):
        q = "∀" if op == "forall" else "∃"
        return f"{q}{pretty(a[1])}∈{pretty(a[0])}. {pretty(a[2])}"
    if op == "where":
        return f"({pretty(a[1])} if {pretty(a[0])} else {pretty(a[2])})"
    if op == "odd":
        return f"odd({pretty(a[0])})"
    if op == "cut":
        return f"|E({pretty(a[0])}, V ∖ {pretty(a[0])})|"
    return f"{op}({', '.join(pretty(x) if isinstance(x, Node) else str(x) for x in a)})"
