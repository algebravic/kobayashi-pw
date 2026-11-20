"""Rewrites used to derive arc costs f(S + x) in terms of the state S.

Each rule is an identity of set functions, valid under the side condition
x ∉ S (guaranteed: moves range over sets disjoint from S):

  bigunion(S ∪ {x}, F)       = bigunion(S, F) ∪ F(x)
  cut(S ∪ {x})               = cut(S) + deg x − 2 |N(x) ∩ S|
  (A ∪ {x}) ∖ B              = (A ∖ B) ∪ ({x} ∖ B)          (only to expose S)
"""
from __future__ import annotations

from .ir import Node, SET, INT, VERT, BINDERS


def _F(name, v):
    if name in ("N", "Nin", "Nout"):
        return Node(name, (v,), SET)
    return Node("vfun", (name, v), SET)


def rewrite(node: Node, S: Node, x: Node) -> Node:
    """Bottom-up application of the rules, with T = S ∪ {x} recognised."""
    T = Node("or", (S, Node("single", (x,), SET)), SET)

    def rw(n):
        if not isinstance(n, Node) or n.op in ("var", "int", "bool"):
            return n
        if n.op in BINDERS:
            a, u, b = n.args
            return Node(n.op, (rw(a), u, rw(b)), n.type)
        args = tuple(rw(a) if isinstance(a, Node) else a for a in n.args)
        n = Node(n.op, args, n.type)
        if n.op == "bigunion" and n.args[0] is T:
            return Node("or", (Node("bigunion", (S, n.args[1]), SET), _F(n.args[1], x)), SET)
        if n.op == "cut" and n.args[0] is T:
            cS = Node("cut", (S,), INT)
            two = Node("mul", (Node("int", (2,), INT), Node("card", (Node("and", (Node("N", (x,), SET), S), SET),), INT)), INT)
            return Node("isub", (Node("add", (cS, Node("deg", (x,), INT)), INT), two), INT)
        return n

    return rw(node)
