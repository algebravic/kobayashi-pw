"""Command line: kobayashi-pw FILE [options]."""

from __future__ import annotations

import argparse
import sys
import time

from .core import decide, ordering_width, pathwidth
from .io import read_edge_list, read_graph6


def _graphs(path: str, fmt: str, directed: bool):
    if fmt == "auto":
        fmt = "graph6" if path.endswith((".g6", ".d6", ".graph6", ".digraph6")) else "edges"
    if fmt == "edges":
        yield path, read_edge_list(path, directed)
    else:
        with open(path) as f:
            for i, line in enumerate(f, 1):
                if line.strip():
                    yield f"{path}:{i}", read_graph6(line)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file")
    ap.add_argument("--format", choices=["auto", "edges", "graph6"], default="auto",
                    help="graph6 also accepts digraph6 lines (prefix '&')")
    ap.add_argument("--directed", action="store_true",
                    help="edge list lines 'u v' are arcs u->v")
    ap.add_argument("--upper", type=int, default=None,
                    help="stop if pw > UPPER (decision mode)")
    ap.add_argument("--alg1", type=int, metavar="K", default=None,
                    help="instead run the paper's Algorithm 1 literally for bound K")
    ap.add_argument("--greedy2", action="store_true",
                    help="also use Coudert et al.'s second greedy rule (same pw, fewer sets)")
    ap.add_argument("--reverse", action="store_true",
                    help="print the ordering reversed (frontier-DP / Kinnersley convention)")
    ap.add_argument("--no-order", action="store_true")
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args(argv)

    for name, g in _graphs(a.file, a.format, a.directed):
        t0 = time.perf_counter()
        if a.alg1 is not None:
            ans = decide(g, a.alg1)
            print(f"{name}\tn={g.n}\tpw<={a.alg1}: {'YES' if ans else 'NO'}"
                  f"\t{time.perf_counter() - t0:.3f}s")
            continue
        r = pathwidth(g, upper=a.upper, want_order=not a.no_order, greedy2=a.greedy2)
        dt = time.perf_counter() - t0
        if r.width is None:
            print(f"{name}\tn={g.n}\tpw > {a.upper}\t{dt:.3f}s")
        else:
            print(f"{name}\tn={g.n}\tpw={r.width}\t{dt:.3f}s")
            if r.order is not None:
                w = ordering_width(g, r.order)
                assert w == r.width, (w, r.width)       # independent check
                shown = r.order[::-1] if a.reverse else r.order
                print("order:", " ".join(map(str, shown)))
        if a.stats:
            print(f"  sets={r.sets_expanded} pairs={r.pairs_popped} rescans={r.rescans}"
                  f" per_level={r.per_level}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
