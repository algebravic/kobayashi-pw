"""Exact pathwidth (vertex separation number) via Kobayashi's relevant-set DP.

Graphs are represented by in-neighbour bitmasks: ``nin[v]`` has bit ``u`` set
iff there is an arc u -> v.  For an undirected graph ``nin[v]`` is just the
neighbourhood of v.
"""

from .core import (
    Graph,
    boundary,
    expand,
    decide,
    pathwidth,
    ordering_width,
)
from .io import read_edge_list, read_graph6, from_edges

__all__ = [
    "Graph",
    "boundary",
    "expand",
    "decide",
    "pathwidth",
    "ordering_width",
    "read_edge_list",
    "read_graph6",
    "from_edges",
]
