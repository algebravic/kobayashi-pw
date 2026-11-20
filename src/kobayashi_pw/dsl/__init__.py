"""Embedded DSL for set-determined layout searches (doc/dsl_design.md).

Specifications are written with symbolic set expressions; Problem.solve()
interprets them (mode="eager") or lowers them to C, compiles on demand and
caches the library (mode="c").  See specs.py for vertex separation, cutwidth
and treewidth.
"""
from . import lemma
from .eager import GData
from .ir import (N, Nin, Nout, bigunion, card, cut, deg, exists, filt, forall, imax, imin, member,
                 odd, qset, seq, single, subset, where, isum)
from .problem import Problem, Solution
from .specs import cutwidth, treewidth, vertex_separation

__all__ = ["Problem", "Solution", "GData", "lemma", "N", "Nin", "Nout", "bigunion", "card", "cut", "deg",
           "exists", "filt", "forall", "imax", "imin", "member", "odd", "qset", "seq", "single", "subset",
           "where", "isum", "cutwidth", "treewidth", "vertex_separation"]
