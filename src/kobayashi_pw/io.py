"""Graph input: edge lists, graph6, digraph6."""

from __future__ import annotations

from typing import Hashable, Iterable

from .core import Graph


def from_edges(
    edges: Iterable[tuple[Hashable, Hashable]],
    vertices: Iterable[Hashable] = (),
    directed: bool = False,
) -> Graph:
    """Build a Graph.  Directed: (u, v) is the arc u -> v."""
    labels: list[Hashable] = []
    idx: dict[Hashable, int] = {}

    def vid(x: Hashable) -> int:
        if x not in idx:
            idx[x] = len(labels)
            labels.append(x)
        return idx[x]

    for x in vertices:
        vid(x)
    arcs = [(vid(u), vid(v)) for u, v in edges]
    nin = [0] * len(labels)
    for u, v in arcs:
        if u == v:
            continue                      # loops do not affect vertex separation
        nin[v] |= 1 << u
        if not directed:
            nin[u] |= 1 << v
    return Graph(len(labels), nin, labels)


def read_edge_list(path: str, directed: bool = False) -> Graph:
    """Whitespace-separated 'u v' per line; a lone token is an isolated vertex;
    '#' starts a comment.  Labels are kept as strings (ints if all numeric)."""
    edges, verts = [], []
    with open(path) as f:
        for line in f:
            tok = line.split("#", 1)[0].split()
            if len(tok) == 1:
                verts.append(tok[0])
            elif len(tok) >= 2:
                verts.extend(tok[:2])
                edges.append((tok[0], tok[1]))
    if all(t.lstrip("-").isdigit() for t in verts):
        conv = int
        verts = sorted(set(verts), key=int)
    else:
        conv = str
    return from_edges(
        ((conv(u), conv(v)) for u, v in edges), map(conv, verts), directed
    )


def _decode_n(data: bytes, pos: int) -> tuple[int, int]:
    if data[pos] != 126:
        return data[pos] - 63, pos + 1
    if data[pos + 1] != 126:
        k, pos = 3, pos + 1
    else:
        k, pos = 6, pos + 2
    n = 0
    for b in data[pos:pos + k]:
        n = (n << 6) | (b - 63)
    return n, pos + k


def _bitstream(data: bytes):
    for b in data:
        b -= 63
        for s in range(5, -1, -1):
            yield b >> s & 1


def read_graph6(line: str) -> Graph:
    """Decode one graph6 ('>>graph6<<' header optional) or digraph6 ('&') line."""
    s = line.strip()
    if s.startswith(">>graph6<<"):
        s = s[10:]
    elif s.startswith(">>digraph6<<"):
        s = s[12:]
    data = s.encode("ascii")
    directed = data[:1] == b"&"
    n, pos = _decode_n(data, 1 if directed else 0)
    bits = _bitstream(data[pos:])
    nin = [0] * n
    if directed:
        for i in range(n):
            for j in range(n):
                if next(bits) and i != j:
                    nin[j] |= 1 << i      # arc i -> j
    else:
        for j in range(1, n):
            for i in range(j):
                if next(bits):
                    nin[i] |= 1 << j
                    nin[j] |= 1 << i
    return Graph(n, nin)
